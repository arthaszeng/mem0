"""A: Authentication, login, JWT, API keys, password change."""

import uuid
import httpx
import pytest

from conftest import (
    BASE_URL, ADMIN_USER, ADMIN_PASS, _client,
    api_get, api_post, api_delete, login, get_token, _headers,
    create_auth_user, purge_user,
)


class TestLogin:
    def test_admin_login_happy_path(self, admin_token):
        data = login(ADMIN_USER, ADMIN_PASS)
        assert "access_token" in data
        assert data["user"]["is_superadmin"] is True

    def test_normal_user_login(self, user_a_credentials):
        uname, pwd, _ = user_a_credentials
        data = login(uname, pwd)
        assert "access_token" in data
        assert data["user"]["username"] == uname

    def test_wrong_password(self):
        r = _client.post(f"{BASE_URL}/auth/login",
                         json={"username": ADMIN_USER, "password": "wrongpass"})
        assert r.status_code == 401

    def test_nonexistent_user(self):
        r = _client.post(f"{BASE_URL}/auth/login",
                         json={"username": "no_such_user_xyz", "password": "x"})
        assert r.status_code == 401

    def test_no_auth_header_rejected(self):
        r = _client.get(f"{BASE_URL}/api/v1/memories/")
        assert r.status_code == 401


class TestJWT:
    def test_valid_jwt_accepted(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/")
        assert r.status_code == 200

    def test_malformed_jwt_rejected(self):
        r = _client.get(f"{BASE_URL}/api/v1/memories/",
                        headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_garbage_token_rejected(self):
        r = _client.get(f"{BASE_URL}/api/v1/memories/",
                        headers={"Authorization": "Bearer garbage_token_abc123"})
        assert r.status_code == 401


class TestAuthMe:
    def test_me_returns_user_info(self, admin_token):
        r = api_get(admin_token, "/auth/me")
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == ADMIN_USER
        assert "id" in data


class TestAPIKeys:
    def test_create_and_use_api_key(self, admin_token):
        r = api_post(admin_token, "/auth/api-keys", json={"name": f"e2e-key-{uuid.uuid4().hex[:6]}"})
        assert r.status_code == 200
        key_data = r.json()
        assert key_data["key"].startswith("om_")

        r2 = _client.get(f"{BASE_URL}/api/v1/memories/",
                         headers={"Authorization": f"Bearer {key_data['key']}"})
        assert r2.status_code == 200

    def test_revoke_api_key(self, admin_token):
        r = api_post(admin_token, "/auth/api-keys", json={"name": f"e2e-revoke-{uuid.uuid4().hex[:6]}"})
        key_data = r.json()
        key_id = key_data["id"]
        raw_key = key_data["key"]

        r2 = api_delete(admin_token, f"/auth/api-keys/{key_id}")
        assert r2.status_code == 200

        r3 = _client.get(f"{BASE_URL}/api/v1/memories/",
                         headers={"Authorization": f"Bearer {raw_key}"})
        assert r3.status_code == 401

    def test_list_own_keys(self, admin_token):
        r = api_get(admin_token, "/auth/api-keys")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestChangePassword:
    def test_change_password_flow(self, admin_token):
        uname = f"e2e_chpwd_{uuid.uuid4().hex[:6]}"
        old_pwd = "OldPass1!"
        new_pwd = "NewPass2!"
        create_auth_user(admin_token, uname, old_pwd)
        try:
            tok = get_token(uname, old_pwd)
            r = api_post(tok, "/auth/change-password", json={
                "old_password": old_pwd,
                "new_password": new_pwd,
            })
            assert r.status_code == 200

            tok2 = get_token(uname, new_pwd)
            assert tok2
        finally:
            purge_user(admin_token, uname)
            api_delete(admin_token, f"/auth/users/{uname}")
