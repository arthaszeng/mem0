"""API Key management endpoints."""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_superadmin
from models import ApiKey, User
from schemas import CreateApiKeyRequest, CreateApiKeyResponse

router = APIRouter(prefix="/auth/api-keys", tags=["api-keys"])


@router.post("", response_model=CreateApiKeyResponse)
def create_api_key(
    body: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_random = secrets.token_urlsafe(32)
    raw_key = f"om_{raw_random}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:11]

    api_key = ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return CreateApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        key=raw_key,
        created_at=api_key.created_at.isoformat(),
    )


@router.get("")
def list_api_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")
    api_key.is_active = False
    db.commit()
    return {"message": "API key revoked"}


# ---- Admin endpoints (superadmin only) ----

@router.get("/admin/all")
def list_all_api_keys(
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    keys = (
        db.query(ApiKey, User.username)
        .join(User, ApiKey.user_id == User.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "username": username,
        }
        for k, username in keys
    ]


@router.delete("/admin/{key_id}")
def admin_revoke_api_key(
    key_id: str,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")
    api_key.is_active = False
    db.commit()
    return {"message": "API key revoked"}
