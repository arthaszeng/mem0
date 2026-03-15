"""
Taxonomy migration: re-classify all memories with the new domain/category system.

Run inside the MCP container:
    python migrate_taxonomy.py              # dry-run (preview only)
    python migrate_taxonomy.py --commit     # apply changes

What it does:
  1. Registers/updates domains in DB (arthas1/Trading, OSMP keywords, etc.)
  2. Re-classifies every active memory using the updated prompt
  3. Cleans up orphaned categories no longer referenced by any memory
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

from app.database import SessionLocal
from app.models import Category, Memory, MemoryState, memory_categories
from app.utils.categorization import classify_memory
from app.utils.domain_registry import add_domain, get_domains, invalidate_cache, save_domains


def step1_update_domains():
    """Register new domains and update existing ones in the DB."""
    logger.info("=== Step 1: Updating domain registry ===")

    add_domain(
        name="arthas1/Trading",
        display="arthas1量化交易系统",
        aliases=["arthas1", "量化交易", "交易系统", "A股", "量化"],
        keywords=[
            "Tushare", "回测", "backtest", "策略", "stock",
            "trade_calendar", "daily_trade", "信号", "撮合", "T+1",
            "stock_list", "daily_basic", "stock_st", "收盘",
        ],
    )
    logger.info("  Registered arthas1/Trading")

    domains = dict(get_domains())

    if "OSMP/MyEvent" in domains:
        osmp = domains["OSMP/MyEvent"]
        extra_kw = {"Vue3", "v-permission", "ElementPlus", "前端技术栈", "菜单权限", "stringForSign", "SHA1"}
        existing_kw = set(osmp.get("keywords", []))
        new_kw = list(osmp.get("keywords", [])) + sorted(extra_kw - existing_kw)
        osmp["keywords"] = new_kw
        osmp.pop("category", None)
        domains["OSMP/MyEvent"] = osmp

    for name in domains:
        domains[name].pop("category", None)

    save_domains(domains)
    invalidate_cache()
    logger.info("  Cleaned 'category' field from all domain entries")

    final = get_domains()
    logger.info("  Domain registry now has %d domains: %s", len(final), list(final.keys()))


def step2_reclassify(dry_run: bool):
    """Re-classify all active memories."""
    logger.info("=== Step 2: Re-classifying memories (dry_run=%s) ===", dry_run)

    db = SessionLocal()
    try:
        memories = (
            db.query(Memory)
            .filter(Memory.state == MemoryState.active)
            .order_by(Memory.created_at.asc())
            .all()
        )
        total = len(memories)
        logger.info("  Found %d active memories to process", total)

        stats = {
            "domain_changed": 0,
            "categories_changed": 0,
            "errors": 0,
        }

        for i, mem in enumerate(memories, 1):
            content = mem.content or ""
            old_meta = dict(mem.metadata_ or {})
            old_domain = old_meta.get("domain", "")
            old_cats = sorted([c.name for c in mem.categories])

            try:
                new_domain, new_cats, new_tags = classify_memory(content)
            except Exception as e:
                logger.error("  [%d/%d] FAILED %s: %s", i, total, mem.id, e)
                stats["errors"] += 1
                continue

            new_cats_sorted = sorted(new_cats)

            domain_changed = old_domain != new_domain
            cats_changed = old_cats != new_cats_sorted

            if domain_changed:
                stats["domain_changed"] += 1
            if cats_changed:
                stats["categories_changed"] += 1

            if domain_changed or cats_changed:
                prefix = "[DRY]" if dry_run else "[UPD]"
                logger.info(
                    "  %s [%d/%d] %s  domain: %s -> %s  cats: %s -> %s",
                    prefix, i, total, str(mem.id)[:8],
                    old_domain, new_domain,
                    old_cats, new_cats_sorted,
                )

            if not dry_run and (domain_changed or cats_changed):
                new_meta = dict(old_meta)
                new_meta["domain"] = new_domain
                new_meta["tags"] = new_tags
                mem.metadata_ = new_meta

                db.execute(
                    memory_categories.delete().where(
                        memory_categories.c.memory_id == mem.id
                    )
                )

                for cat_name in new_cats:
                    cat = db.query(Category).filter(Category.name == cat_name).first()
                    if not cat:
                        cat = Category(
                            name=cat_name,
                            description=f"Standard knowledge-type category: {cat_name}",
                        )
                        db.add(cat)
                        db.flush()
                    db.execute(
                        memory_categories.insert().values(
                            memory_id=mem.id,
                            category_id=cat.id,
                        )
                    )

            if i % 20 == 0:
                logger.info("  ... processed %d/%d", i, total)
                if not dry_run:
                    db.flush()

            time.sleep(0.3)

        if not dry_run:
            db.commit()
            logger.info("  Committed all changes")

        logger.info(
            "  Stats: %d/%d domain changed, %d/%d categories changed, %d errors",
            stats["domain_changed"], total,
            stats["categories_changed"], total,
            stats["errors"],
        )
        return stats

    finally:
        db.close()


def step3_cleanup_orphans(dry_run: bool):
    """Remove categories no longer referenced by any memory."""
    logger.info("=== Step 3: Cleaning orphaned categories (dry_run=%s) ===", dry_run)

    db = SessionLocal()
    try:
        all_cats = db.query(Category).all()
        orphans = []
        for cat in all_cats:
            count = (
                db.query(memory_categories)
                .filter(memory_categories.c.category_id == cat.id)
                .count()
            )
            if count == 0:
                orphans.append(cat)

        if not orphans:
            logger.info("  No orphaned categories found")
            return

        logger.info("  Found %d orphaned categories:", len(orphans))
        for cat in orphans:
            logger.info("    - %s (id=%s)", cat.name, cat.id)

        if not dry_run:
            for cat in orphans:
                db.delete(cat)
            db.commit()
            logger.info("  Deleted %d orphaned categories", len(orphans))

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Re-classify all memories with new taxonomy")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    dry_run = not args.commit

    if dry_run:
        logger.info("*** DRY RUN MODE — no changes will be written ***")
    else:
        logger.info("*** COMMIT MODE — changes will be applied ***")

    step1_update_domains()
    step2_reclassify(dry_run)
    step3_cleanup_orphans(dry_run)

    logger.info("=== Migration complete ===")


if __name__ == "__main__":
    main()
