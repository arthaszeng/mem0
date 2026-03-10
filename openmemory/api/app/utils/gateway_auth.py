"""Read authenticated user info from nginx gateway-injected headers.

This is the ONLY auth code downstream services need. The nginx gateway
has already verified the token (JWT or API Key) via auth_request and
injected X-Auth-* headers into the request."""

import datetime
import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import App, User

logger = logging.getLogger(__name__)


class AuthenticatedUser:
    """Lightweight wrapper for the gateway-authenticated user identity."""

    def __init__(self, user_id: str, username: str, is_superadmin: bool, db_user: "User"):
        self.user_id = user_id
        self.username = username
        self.is_superadmin = is_superadmin
        self.db_user = db_user

    @property
    def id(self):
        return self.db_user.id


def get_authenticated_user(request: Request, db: Session = Depends(get_db)) -> AuthenticatedUser:
    """FastAPI dependency that reads user info from nginx-injected headers.
    Auto-provisions the OpenMemory User row on first access."""
    auth_user_id = request.headers.get("X-Auth-User-Id")
    auth_username = request.headers.get("X-Auth-Username", "")
    auth_is_superadmin = request.headers.get("X-Auth-Is-Superadmin", "false") == "true"

    if not auth_user_id:
        raise HTTPException(401, "Not authenticated via gateway")

    db_user = db.query(User).filter(User.user_id == auth_username).first()
    if not db_user:
        db_user = User(
            user_id=auth_username,
            name=auth_username,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        db.add(db_user)
        db.flush()

        default_app = App(name="openmemory", owner_id=db_user.id)
        db.add(default_app)
        db.commit()
        db.refresh(db_user)
        logger.info("Auto-provisioned OpenMemory user: %s", auth_username)

    return AuthenticatedUser(
        user_id=auth_user_id,
        username=auth_username,
        is_superadmin=auth_is_superadmin,
        db_user=db_user,
    )
