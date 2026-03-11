"""Login, verify (for nginx auth_request), change-password, me."""

import hashlib

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_SECONDS, AUTH_BASE_URL
from database import get_db
from dependencies import get_current_user
from jwt_utils import sign_access_token, verify_access_token
from models import ApiKey, RefreshToken, User
from schemas import ChangePasswordRequest, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid credentials")
    if not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Invalid credentials")

    token = sign_access_token(
        user_id=user.id,
        username=user.username,
        is_superadmin=user.is_superadmin,
        issuer=AUTH_BASE_URL,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return LoginResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS,
        must_change_password=user.must_change_password,
        user={"id": user.id, "username": user.username, "is_superadmin": user.is_superadmin},
    )


@router.get("/verify")
def verify(request: Request, db: Session = Depends(get_db)):
    """Called by nginx auth_request subrequest.
    Returns 200 with X-Auth-* headers on success, 401 on failure."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth[7:]

    user: User | None = None

    if token.startswith("eyJ"):
        try:
            payload = verify_access_token(token)
        except Exception:
            raise HTTPException(401, "Invalid token")
        user = db.query(User).filter(User.id == payload["sub"]).first()
    elif token.startswith("om_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True).first()
        if api_key:
            from datetime import datetime, UTC
            api_key.last_used_at = datetime.now(UTC)
            db.commit()
            user = api_key.user

    if not user or not user.is_active:
        raise HTTPException(401, "Authentication failed")

    return Response(
        status_code=200,
        headers={
            "X-Auth-User-Id": user.id,
            "X-Auth-Username": user.username,
            "X-Auth-Is-Superadmin": str(user.is_superadmin).lower(),
        },
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not bcrypt.checkpw(body.old_password.encode(), user.password_hash.encode()):
        raise HTTPException(400, "Old password incorrect")
    user.password_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    user.must_change_password = False
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()
    return {"message": "Password changed"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_superadmin": user.is_superadmin,
        "must_change_password": user.must_change_password,
    }
