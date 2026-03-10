"""
In-memory per-user cookie store for Concierge access tokens.

Each user is identified by a user_id derived from the OAuth flow.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Entry:
    access_token: str
    stored_at: float


class CookieStore:
    def __init__(self, ttl_seconds: int = 86400):
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def set(self, user_id: str, access_token: str) -> None:
        with self._lock:
            self._store[user_id] = _Entry(
                access_token=access_token,
                stored_at=time.time(),
            )

    def get(self, user_id: str) -> str | None:
        with self._lock:
            entry = self._store.get(user_id)
            if entry is None:
                return None
            if time.time() - entry.stored_at > self._ttl:
                del self._store[user_id]
                return None
            return entry.access_token

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._store.pop(user_id, None)

    def get_any(self) -> str | None:
        """Return the most recently stored token (for dev mode fallback)."""
        with self._lock:
            now = time.time()
            best: _Entry | None = None
            for entry in self._store.values():
                if now - entry.stored_at > self._ttl:
                    continue
                if best is None or entry.stored_at > best.stored_at:
                    best = entry
            return best.access_token if best else None

    def update_token(self, user_id: str, new_token: str) -> None:
        """Update access token after a successful refresh."""
        with self._lock:
            entry = self._store.get(user_id)
            if entry is not None:
                entry.access_token = new_token
                entry.stored_at = time.time()
            else:
                self._store[user_id] = _Entry(
                    access_token=new_token,
                    stored_at=time.time(),
                )


cookie_store = CookieStore()
