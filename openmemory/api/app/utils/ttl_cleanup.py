"""Background task that expires memories past their TTL.

Runs periodically and marks active memories with expires_at <= now as expired.
"""
import asyncio
import datetime
import logging

from app.database import SessionLocal
from app.models import Memory, MemoryState

logger = logging.getLogger(__name__)

TTL_CHECK_INTERVAL = 300  # seconds


async def ttl_cleanup_loop():
    """Periodically expire memories that have passed their expires_at timestamp."""
    while True:
        try:
            await asyncio.sleep(TTL_CHECK_INTERVAL)
            count = _expire_stale_memories()
            if count:
                logger.info("TTL cleanup: expired %d memories", count)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("TTL cleanup error")


def _expire_stale_memories(session=None) -> int:
    """Mark memories whose expires_at has passed as expired. Returns count.

    Args:
        session: Optional SQLAlchemy session for testing. If None, creates one from SessionLocal.
    """
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.UTC)
        stale = (
            session.query(Memory)
            .filter(
                Memory.state == MemoryState.active,
                Memory.expires_at.isnot(None),
                Memory.expires_at <= now,
            )
            .all()
        )
        for m in stale:
            m.state = MemoryState.expired
            m.deleted_at = now
        session.commit()
        return len(stale)
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
