"""Background task that archives memories per ArchivePolicy rules.

Runs hourly and archives active memories that exceed policy age thresholds.
"""
import asyncio
import datetime
import logging
import uuid as _uuid

from app.database import SessionLocal
from app.models import ArchivePolicy, Memory, MemoryState

logger = logging.getLogger(__name__)

ARCHIVE_CHECK_INTERVAL = 3600


async def archive_policy_loop():
    while True:
        try:
            await asyncio.sleep(ARCHIVE_CHECK_INTERVAL)
            count = apply_archive_policies()
            if count:
                logger.info("Archive policy: archived %d memories", count)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Archive policy loop error")


def apply_archive_policies(session=None) -> int:
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.UTC)
        policies = session.query(ArchivePolicy).all()
        total_archived = 0

        for policy in policies:
            cutoff = now - datetime.timedelta(days=policy.days_to_archive)
            q = session.query(Memory).filter(
                Memory.state == MemoryState.active,
                Memory.created_at <= cutoff,
            )
            if policy.criteria_type == "global":
                pass
            elif policy.criteria_type == "app" and policy.criteria_id:
                try:
                    app_uuid = _uuid.UUID(policy.criteria_id)
                except (ValueError, AttributeError):
                    continue
                q = q.filter(Memory.app_id == app_uuid)
            else:
                continue

            for m in q.all():
                m.state = MemoryState.archived
                m.archived_at = now
                total_archived += 1

        session.commit()
        return total_archived
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
