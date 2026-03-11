import base64
import hashlib
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from config import KEYS_DIR

_PRIVATE_KEY_PATH = KEYS_DIR / "private.pem"
_PUBLIC_KEY_PATH = KEYS_DIR / "public.pem"

_private_key = None
_public_key = None
_kid = None


def _ensure_keys():
    global _private_key, _public_key, _kid
    if _private_key is not None:
        return

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    if _PRIVATE_KEY_PATH.exists():
        _private_key = serialization.load_pem_private_key(
            _PRIVATE_KEY_PATH.read_bytes(), password=None
        )
    else:
        _private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _PRIVATE_KEY_PATH.write_bytes(
            _private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    _public_key = _private_key.public_key()
    if not _PUBLIC_KEY_PATH.exists():
        _PUBLIC_KEY_PATH.write_bytes(
            _public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    pub_der = _public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _kid = hashlib.sha256(pub_der).hexdigest()[:16]


def sign_access_token(
    user_id: str,
    username: str,
    is_superadmin: bool,
    issuer: str,
    expires_in: int = 3600,
) -> str:
    _ensure_keys()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "is_superadmin": is_superadmin,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": _kid})


def verify_access_token(token: str, expected_issuer: str | None = None) -> dict:
    _ensure_keys()
    from config import AUTH_BASE_URL
    issuer = expected_issuer or AUTH_BASE_URL
    return jwt.decode(
        token, _public_key, algorithms=["RS256"],
        issuer=issuer, options={"verify_iss": True},
    )


def get_jwks() -> dict:
    _ensure_keys()
    pub = _public_key.public_numbers()

    def _b64url(num: int, length: int) -> str:
        return base64.urlsafe_b64encode(num.to_bytes(length, "big")).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": _kid,
                "n": _b64url(pub.n, 256),
                "e": _b64url(pub.e, 3),
            }
        ]
    }
