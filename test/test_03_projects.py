"""C: Project CRUD, slug, auto-default."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_put, api_delete,
    create_project, create_memory, add_member,
    create_auth_user, get_token, provision_api_user, purge_user,
)


class TestAutoDefault:
    def test_first_api_access_creates_default_project(self, admin_token):
        uname = f"e2e_autodef_{uuid.uuid4().hex[:6]}"
        create_auth_user(admin_token, uname, "Pass1!")
        tok = get_token(uname, "Pass1!")

        r = api_get(tok, "/api/v1/projects")
        assert r.status_code == 200
        projects = r.json()
        assert len(projects) >= 1
        purge_user(admin_token, uname)
        api_delete(admin_token, f"/auth/users/{api_get(admin_token, '/auth/users').json()[-1]['id']}")


class TestProjectCRUD:
    def test_create_with_custom_slug(self, user_a_token):
        slug = f"e2e-custom-{uuid.uuid4().hex[:6]}"
        p = create_project(user_a_token, "Custom Slug", slug)
        assert p["slug"] == slug
        api_delete(user_a_token, f"/api/v1/projects/{slug}")

    def test_create_with_auto_slug(self, user_a_token):
        name = f"Auto Slug {uuid.uuid4().hex[:6]}"
        p = create_project(user_a_token, name)
        assert p["slug"]
        api_delete(user_a_token, f"/api/v1/projects/{p['slug']}")

    def test_duplicate_slug(self, user_a_token, shared_project_slug):
        r = api_post(user_a_token, "/api/v1/projects", json={
            "name": "dup", "slug": shared_project_slug,
        })
        assert r.status_code == 409

    def test_get_project_detail(self, user_a_token, shared_project_slug):
        r = api_get(user_a_token, f"/api/v1/projects/{shared_project_slug}")
        assert r.status_code == 200
        assert r.json()["slug"] == shared_project_slug

    def test_update_project_name(self, user_a_token):
        slug = f"e2e-upd-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "Before", slug)
        r = api_put(user_a_token, f"/api/v1/projects/{slug}", json={"name": "After"})
        assert r.status_code == 200
        assert r.json()["name"] == "After"
        api_delete(user_a_token, f"/api/v1/projects/{slug}")

    def test_deleted_project_404(self, user_a_token):
        slug = f"e2e-del404-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "ToDelete", slug)
        api_delete(user_a_token, f"/api/v1/projects/{slug}")
        r = api_get(user_a_token, f"/api/v1/projects/{slug}")
        assert r.status_code == 404


class TestProjectListing:
    def test_normal_user_sees_own_projects(self, user_a_token, shared_project_slug):
        r = api_get(user_a_token, "/api/v1/projects")
        slugs = [p["slug"] for p in r.json()]
        assert shared_project_slug in slugs

    def test_superadmin_sees_all(self, admin_token, shared_project_slug):
        r = api_get(admin_token, "/api/v1/projects")
        slugs = [p["slug"] for p in r.json()]
        assert shared_project_slug in slugs


class TestProjectPermissions:
    def test_read_only_cannot_update(self, admin_token, user_b_token, user_b_name):
        slug = f"e2e-roperm-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "RO Test", slug)
        add_member(admin_token, slug, user_b_name, "read_only")

        r = api_put(user_b_token, f"/api/v1/projects/{slug}", json={"name": "Hacked"})
        assert r.status_code == 403
        api_delete(admin_token, f"/api/v1/projects/{slug}")

    def test_non_member_cannot_delete(self, user_b_token, shared_project_slug):
        r = api_delete(user_b_token, f"/api/v1/projects/{shared_project_slug}")
        assert r.status_code == 403


class TestProjectCascadeDelete:
    def test_delete_cascades_memories(self, user_a_token):
        slug = f"e2e-cascade-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "Cascade", slug)
        create_memory(user_a_token, "mem in cascade project", slug)
        time.sleep(3)
        r = api_delete(user_a_token, f"/api/v1/projects/{slug}")
        assert r.status_code == 200
        assert r.json()["deleted_memories"] >= 0
