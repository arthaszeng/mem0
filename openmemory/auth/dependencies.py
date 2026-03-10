import hashlib

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from jwt_utils import verify_access_token
from models import ApiKey, User


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(401, "Missing authorization token")

    if token.startswith("eyJ"):
        try:
            payload = verify_access_token(token)
        except Exception:
            raise HTTPException(401, "Invalid or expired token")
        user = db.query(User).filter(User.id == payload["sub"]).first()
    elif token.startswith("om_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True).first()
        if not api_key:
            raise HTTPException(401, "Invalid API key")
        from datetime import datetime, UTC
        api_key.last_used_at = datetime.now(UTC)
        db.commit()
        user = api_key.user
    else:
        raise HTTPException(401, "Unrecognized token format")

    if not user or not user.is_active:
        raise HTTPException(401, "User inactive or not found")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superadmin:
        raise HTTPException(403, "Superadmin required")
    return user
