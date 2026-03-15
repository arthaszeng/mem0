import os

USER_ID = os.getenv("MEMVERSE_USER") or os.getenv("USER", "default_user")
DEFAULT_APP_ID = "memverse"