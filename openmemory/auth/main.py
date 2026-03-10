import json
import logging

import bcrypt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (
    AUTH_BASE_URL,
    CHATGPT_CLIENT_ID,
    CHATGPT_CLIENT_SECRET,
    CHATGPT_REDIRECT_URI,
    CHROME_EXT_CLIENT_ID,
    INIT_ADMIN_PASSWORD,
    INIT_ADMIN_USER,
)
from database import Base, SessionLocal, engine
from models import OAuthClient, User
from routers.api_keys import router as api_keys_router
from routers.auth import router as auth_router
from routers.oauth import router as oauth_router
from routers.users import router as users_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth-service")

app = FastAPI(title="Auth Service", docs_url="/auth/docs", openapi_url="/auth/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def _init_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == INIT_ADMIN_USER).first()
        if existing:
            return
        pw_hash = bcrypt.hashpw(INIT_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        admin = User(
            username=INIT_ADMIN_USER,
            password_hash=pw_hash,
            is_superadmin=True,
            must_change_password=False,
        )
        db.add(admin)
        db.commit()
        logger.info(f"Created admin user: {INIT_ADMIN_USER}")
    finally:
        db.close()


def _init_oauth_clients():
    db = SessionLocal()
    try:
        if CHATGPT_CLIENT_SECRET and not db.query(OAuthClient).filter(OAuthClient.client_id == CHATGPT_CLIENT_ID).first():
            secret_hash = bcrypt.hashpw(CHATGPT_CLIENT_SECRET.encode(), bcrypt.gensalt()).decode()
            db.add(OAuthClient(
                client_id=CHATGPT_CLIENT_ID,
                client_secret_hash=secret_hash,
                client_name="ChatGPT Custom GPT",
                redirect_uris=json.dumps([CHATGPT_REDIRECT_URI]),
                grant_types=json.dumps(["authorization_code", "refresh_token"]),
                is_dynamic=False,
            ))
            logger.info("Registered ChatGPT OAuth client")

        if not db.query(OAuthClient).filter(OAuthClient.client_id == CHROME_EXT_CLIENT_ID).first():
            db.add(OAuthClient(
                client_id=CHROME_EXT_CLIENT_ID,
                client_name="Chrome Extension",
                redirect_uris=json.dumps([]),
                grant_types=json.dumps(["authorization_code", "refresh_token"]),
                is_dynamic=False,
            ))
            logger.info("Registered Chrome Extension OAuth client")

        db.commit()
    finally:
        db.close()


_init_admin()
_init_oauth_clients()

app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(users_router)
app.include_router(api_keys_router)


@app.get("/auth/health")
def health():
    return {"status": "ok", "service": "auth-service"}
