"""B: User management (superadmin CRUD)."""

import uuid
import pytest

from conftest import (
    BASE_URL, ADMIN_USER,
    api_get, api_post, api_put, api_delete, get_token, _headers,
    create_auth_user, purge_user,
)


class TestCreateUser:
    def test_superadmin_creates_user(self, admin_token):
        uname = f"e2e_create_{uuid.uuid4().hex[:6]}"
        r = api_post(admin_token, "/auth/users", json={
            "username": uname, "password": "Pass123!",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == uname
        api_delete(admin_token, f"/auth/users/{data['id']}")

    def test_duplicate_username(self, admin_token, user_a_name):
        r = api_post(admin_token, "/auth/users", json={
            "username": user_a_name, "password": "x",
        })
        assert r.status_code == 409

    def test_create_user_with_email(self, admin_token):
        uname = f"e2e_email_{uuid.uuid4().hex[:6]}"
        r = api_post(admin_token, "/auth/users", json={
            "username": uname, "password": "Pass123!", "email": f"{uname}@test.com",
        })
        assert r.status_code == 200
        api_delete(admin_token, f"/auth/users/{r.json()['id']}")


class TestListUsers:
    def test_superadmin_lists_users(self, admin_token):
        r = api_get(admin_token, "/auth/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_non_admin_forbidden(self, user_a_token):
        r = api_get(user_a_token, "/auth/users")
        assert r.status_code == 403


class TestDeactivateUser:
    def test_deactivate_then_cannot_login(self, admin_token):
        uname = f"e2e_deact_{uuid.uuid4().hex[:6]}"
        pwd = "Pass123!"
        create_auth_user(admin_token, uname, pwd)
        tok = get_token(uname, pwd)

        users = api_get(admin_token, "/auth/users").json()
        uid = next(u["id"] for u in users if u["username"] == uname)

        r = api_delete(admin_token, f"/auth/users/{uid}")
        assert r.status_code == 200

        from conftest import _client
        r2 = _client.post(f"{BASE_URL}/auth/login",
                          json={"username": uname, "password": pwd})
        assert r2.status_code == 401

    def test_cannot_deactivate_self(self, admin_token):
        me = api_get(admin_token, "/auth/me").json()
        r = api_delete(admin_token, f"/auth/users/{me['id']}")
        assert r.status_code == 400


class TestResetPassword:
    def test_reset_password(self, admin_token):
        uname = f"e2e_reset_{uuid.uuid4().hex[:6]}"
        create_auth_user(admin_token, uname, "OldPass1!")

        users = api_get(admin_token, "/auth/users").json()
        uid = next(u["id"] for u in users if u["username"] == uname)

        r = api_post(admin_token, f"/auth/users/{uid}/reset-password",
                     json={"new_password": "NewPass2!"})
        assert r.status_code == 200

        tok = get_token(uname, "NewPass2!")
        assert tok
        api_delete(admin_token, f"/auth/users/{uid}")
