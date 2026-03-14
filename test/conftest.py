"""Shared fixtures for E2E regression tests.

Tests run against the live Docker deployment via http://localhost (nginx:80).
All test users are prefixed with ``e2e_`` and cleaned up at session end.
"""

import os
import uuid

os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + ",localhost,127.0.0.1"

import httpx
import pytest

BASE_URL = "http://localhost"
ADMIN_USER = "arthaszeng"
ADMIN_PASS = "changeme123"

_client = httpx.Client(timeout=30)

# ---- retry helper ------------------------------------------------------------

def _retry(fn, retries=3, backoff=1.0):
    """Retry a callable on 503/502 with exponential backoff."""
    import time as _time
    for attempt in range(retries):
        r = fn()
        if r.status_code not in (502, 503):
            return r
        if attempt < retries - 1:
            _time.sleep(backoff * (attempt + 1))
    return r

# ---- low-level helpers -------------------------------------------------------

def _headers(token: str) -> dict:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def login(username: str, password: str) -> dict:
    r = _client.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    r.raise_for_status()
    return r.json()


def get_token(username: str, password: str) -> str:
    return login(username, password)["access_token"]


def api_get(token: str, path: str, **kwargs) -> httpx.Response:
    return _retry(lambda: _client.get(f"{BASE_URL}{path}", headers=_headers(token), **kwargs))


def api_post(token: str, path: str, **kwargs) -> httpx.Response:
    return _retry(lambda: _client.post(f"{BASE_URL}{path}", headers=_headers(token), **kwargs))


def api_put(token: str, path: str, **kwargs) -> httpx.Response:
    return _retry(lambda: _client.put(f"{BASE_URL}{path}", headers=_headers(token), **kwargs))


def api_delete(token: str, path: str, **kwargs) -> httpx.Response:
    if "json" in kwargs:
        return _retry(lambda: _client.request("DELETE", f"{BASE_URL}{path}", headers=_headers(token), **kwargs))
    return _retry(lambda: _client.delete(f"{BASE_URL}{path}", headers=_headers(token), **kwargs))

# ---- factories ---------------------------------------------------------------

def create_auth_user(admin_token: str, username: str, password: str = "Test1234!") -> dict:
    """Create a user in the auth service. Returns the auth user dict."""
    r = api_post(admin_token, "/auth/users", json={
        "username": username,
        "password": password,
    })
    r.raise_for_status()
    return r.json()


def provision_api_user(token: str):
    """Trigger auto-provisioning by hitting any API endpoint."""
    api_get(token, "/api/v1/projects")


def create_project(token: str, name: str, slug: str | None = None) -> dict:
    body: dict = {"name": name}
    if slug:
        body["slug"] = slug
    r = api_post(token, "/api/v1/projects", json=body)
    r.raise_for_status()
    return r.json()


def add_member(token: str, slug: str, username: str, role: str = "read_write") -> dict:
    r = api_post(token, f"/api/v1/projects/{slug}/members", json={
        "username": username,
        "role": role,
    })
    r.raise_for_status()
    return r.json()


def create_memory(token: str, content: str, project_slug: str | None = None, **extra) -> httpx.Response:
    """Create a memory and return the raw httpx.Response.

    Uses infer=False by default to bypass LLM deduplication for reliable tests.
    project_slug must go in the JSON body per the CreateMemoryRequest schema.
    """
    body: dict = {"text": content, "infer": False, **extra}
    if project_slug:
        body["project_slug"] = project_slug
    r = api_post(token, "/api/v1/memories/", json=body)
    r.raise_for_status()
    return r


def api_upload(token: str, path: str, filename: str, content: bytes, **kwargs) -> httpx.Response:
    """Upload a file via multipart/form-data."""
    return _retry(lambda: _client.post(
        f"{BASE_URL}{path}",
        headers=_headers(token),
        files={"file": (filename, content, "application/zip")},
        **kwargs,
    ))


def purge_user(admin_token: str, username: str):
    """Best-effort cleanup of a test user and all associated data."""
    api_delete(admin_token, f"/api/v1/projects/admin/users/{username}/purge")

# ---- session-scoped fixtures ------------------------------------------------

@pytest.fixture(scope="session")
def admin_token() -> str:
    return get_token(ADMIN_USER, ADMIN_PASS)


@pytest.fixture(scope="session")
def user_a_credentials(admin_token):
    """Create test user A. Returns (username, password, token)."""
    uname = f"e2e_user_a_{uuid.uuid4().hex[:6]}"
    pwd = "UserA_pass1!"
    create_auth_user(admin_token, uname, pwd)
    tok = get_token(uname, pwd)
    provision_api_user(tok)
    yield uname, pwd, tok
    purge_user(admin_token, uname)
    _client.delete(f"{BASE_URL}/auth/users/{uname}", headers=_headers(admin_token))


@pytest.fixture(scope="session")
def user_b_credentials(admin_token):
    """Create test user B. Returns (username, password, token)."""
    uname = f"e2e_user_b_{uuid.uuid4().hex[:6]}"
    pwd = "UserB_pass1!"
    create_auth_user(admin_token, uname, pwd)
    tok = get_token(uname, pwd)
    provision_api_user(tok)
    yield uname, pwd, tok
    purge_user(admin_token, uname)
    _client.delete(f"{BASE_URL}/auth/users/{uname}", headers=_headers(admin_token))


@pytest.fixture(scope="session")
def user_a_token(user_a_credentials) -> str:
    return user_a_credentials[2]


@pytest.fixture(scope="session")
def user_b_token(user_b_credentials) -> str:
    return user_b_credentials[2]


@pytest.fixture(scope="session")
def user_a_name(user_a_credentials) -> str:
    return user_a_credentials[0]


@pytest.fixture(scope="session")
def user_b_name(user_b_credentials) -> str:
    return user_b_credentials[0]


@pytest.fixture(scope="session")
def shared_project_slug(user_a_token, user_a_name):
    """A project owned by user_a, used across multiple test files."""
    slug = f"e2e-shared-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "E2E Shared Project", slug)
    return slug
