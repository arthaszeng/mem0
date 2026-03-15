"""User management endpoints (superadmin only)."""

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_superadmin
from models import User
from schemas import CreateUserRequest, ResetPasswordRequest, UpdateUserRequest

router = APIRouter(prefix="/auth/users", tags=["users"])


@router.post("")
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Username already exists")
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(
        username=body.username,
        email=body.email,
        password_hash=pw_hash,
        is_superadmin=body.is_superadmin,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.get("")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_superadmin)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [_user_dict(u) for u in users]


@router.put("/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if body.email is not None:
        user.email = body.email
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_superadmin is not None:
        user.is_superadmin = body.is_superadmin
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.delete("/{user_id}")
def deactivate_user(
    user_id: str,
    permanent: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "Cannot delete yourself")

    if permanent:
        from models import ApiKey
        db.query(ApiKey).filter(ApiKey.user_id == user.id).delete()
        db.delete(user)
        db.commit()
        return {"message": f"User {user.username} permanently deleted"}

    user.is_active = False
    db.commit()
    return {"message": f"User {user.username} deactivated"}


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    from models import RefreshToken
    user.password_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    user.must_change_password = True
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()
    return {"message": f"Password reset for {user.username}"}


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_superadmin": user.is_superadmin,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
