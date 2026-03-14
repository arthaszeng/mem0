"""L: Archive policies (superadmin)."""

import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
)


class TestArchivePolicyCRUD:
    def test_create_global_policy(self, admin_token):
        r = api_post(admin_token, "/api/v1/memories/archive-policies", json={
            "criteria_type": "global",
            "days_to_archive": 90,
        })
        assert r.status_code == 200
        pid = r.json()["id"]
        api_delete(admin_token, f"/api/v1/memories/archive-policies/{pid}")

    def test_create_app_policy(self, admin_token):
        apps_r = api_get(admin_token, "/api/v1/apps/")
        apps = apps_r.json().get("apps", [])
        if apps:
            app_id = apps[0]["id"]
            r = api_post(admin_token, "/api/v1/memories/archive-policies", json={
                "criteria_type": "app",
                "criteria_id": app_id,
                "days_to_archive": 30,
            })
            assert r.status_code == 200
            pid = r.json()["id"]
            api_delete(admin_token, f"/api/v1/memories/archive-policies/{pid}")

    def test_list_policies(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/archive-policies")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_policy(self, admin_token):
        r = api_post(admin_token, "/api/v1/memories/archive-policies", json={
            "criteria_type": "global",
            "days_to_archive": 365,
        })
        pid = r.json()["id"]
        r2 = api_delete(admin_token, f"/api/v1/memories/archive-policies/{pid}")
        assert r2.status_code == 200

    def test_apply_policies(self, admin_token):
        r = api_post(admin_token, "/api/v1/memories/archive-policies/apply")
        assert r.status_code == 200


class TestArchivePolicyPermission:
    def test_non_superadmin_forbidden(self, user_a_token):
        r = api_post(user_a_token, "/api/v1/memories/archive-policies", json={
            "criteria_type": "global",
            "days_to_archive": 60,
        })
        assert r.status_code == 403

    def test_non_superadmin_list_forbidden(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/memories/archive-policies")
        assert r.status_code == 403
