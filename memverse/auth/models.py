import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.datetime.now(datetime.UTC)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    is_superadmin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    api_keys = relationship("ApiKey", back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    key_hash = Column(String, nullable=False, index=True)
    key_prefix = Column(String(11), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="api_keys")


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id = Column(String, primary_key=True, default=_uuid)
    client_id = Column(String, unique=True, nullable=False, index=True)
    client_secret_hash = Column(String, nullable=True)
    redirect_uris = Column(Text, nullable=False, default="[]")
    grant_types = Column(Text, nullable=False, default='["authorization_code"]')
    client_name = Column(String, nullable=False, default="")
    is_dynamic = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    id = Column(String, primary_key=True, default=_uuid)
    code_hash = Column(String, nullable=False, index=True)
    client_id = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    redirect_uri = Column(String, nullable=False)
    code_challenge = Column(String, nullable=True)
    code_challenge_method = Column(String, nullable=True)
    scopes = Column(String, default="")
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=_uuid)
    token_hash = Column(String, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    client_id = Column(String, nullable=False)
    scopes = Column(String, default="")
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
