import os

USER_ID = os.getenv("MEM0_USER") or os.getenv("USER", "default_user")
DEFAULT_APP_ID = "openmemory"