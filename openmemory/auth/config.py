import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
KEYS_DIR = DATA_DIR / "keys"
DB_PATH = DATA_DIR / "auth.db"

INIT_ADMIN_USER = os.getenv("INIT_ADMIN_USER", "arthaszeng")
INIT_ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD", "changeme")
AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "http://localhost/auth")

ACCESS_TOKEN_EXPIRE_SECONDS = int(os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS", "3600"))
REFRESH_TOKEN_EXPIRE_SECONDS = int(os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", str(30 * 24 * 3600)))
AUTH_CODE_EXPIRE_SECONDS = 300

CHATGPT_CLIENT_ID = os.getenv("CHATGPT_CLIENT_ID", "chatgpt")
CHATGPT_CLIENT_SECRET = os.getenv("CHATGPT_CLIENT_SECRET", "")
CHATGPT_REDIRECT_URI = os.getenv("CHATGPT_REDIRECT_URI", "https://chat.openai.com/aip/g-callback")

CHROME_EXT_CLIENT_ID = os.getenv("CHROME_EXT_CLIENT_ID", "chrome-ext")
