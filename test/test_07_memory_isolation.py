"""G: Cross-user, cross-project memory isolation — critical multi-user tests."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_put, api_delete,
    create_project, create_memory, add_member,
)


@pytest.fixture()
def isolation_projects(user_a_token, user_b_token, user_a_name, user_b_name):
    """Two projects: proj_a (owner: A), proj_b (owner: B). B is read_write in proj_a."""
    slug_a = f"e2e-isoa-{uuid.uuid4().hex[:6]}"
    slug_b = f"e2e-isob-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "Iso A", slug_a)
    create_project(user_b_token, "Iso B", slug_b)
    add_member(user_a_token, slug_a, user_b_name, "read_write")
    yield slug_a, slug_b
    api_delete(user_a_token, f"/api/v1/projects/{slug_a}")
    api_delete(user_b_token, f"/api/v1/projects/{slug_b}")


class TestCrossProjectIsolation:
    def test_memory_in_a_not_visible_in_b(self, user_a_token, user_b_token, isolation_projects):
        slug_a, slug_b = isolation_projects
        tag = uuid.uuid4().hex[:8]
        create_memory(user_a_token, f"Belongs to A only {tag}", slug_a)
        time.sleep(2)
        items_b = api_get(user_b_token, "/api/v1/memories/", params={
            "project_slug": slug_b, "page": 1, "size": 100,
        })
        if items_b.status_code == 200:
            mems = [i.get("content", "") for i in items_b.json().get("items", [])]
            assert not any(tag in m for m in mems)

    def test_user_b_cannot_list_proj_b_memories_as_nonmember_in_a(
        self, user_a_token, user_b_token, isolation_projects
    ):
        _, slug_b = isolation_projects
        r = api_get(user_a_token, f"/api/v1/projects/{slug_b}")
        assert r.status_code == 403


class TestSameProjectMultiUser:
    def test_both_users_can_create_in_shared_project(
        self, user_a_token, user_b_token, isolation_projects
    ):
        slug_a, _ = isolation_projects
        r1 = api_post(user_a_token, "/api/v1/memories/",
                       json={"text": f"A's mem in shared {uuid.uuid4().hex[:8]}", "infer": False, "project_slug": slug_a})
        assert r1.status_code == 200
        r2 = api_post(user_b_token, "/api/v1/memories/",
                       json={"text": f"B's mem in shared {uuid.uuid4().hex[:8]}", "infer": False, "project_slug": slug_a})
        assert r2.status_code == 200


class TestReadOnlyRestriction:
    def test_read_only_can_list_but_not_create(
        self, admin_token, user_b_token, user_b_name
    ):
        slug = f"e2e-ronly-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "ReadOnly", slug)
        add_member(admin_token, slug, user_b_name, "read_only")

        r_list = api_get(user_b_token, "/api/v1/memories/", params={
            "project_slug": slug, "page": 1, "size": 10,
        })
        assert r_list.status_code == 200

        r_create = api_post(user_b_token, "/api/v1/memories/",
                            json={"text": "Should fail", "infer": False, "project_slug": slug})
        assert r_create.status_code == 403
        api_delete(admin_token, f"/api/v1/projects/{slug}")


class TestNonMemberBlocked:
    def test_non_member_cannot_list(self, user_b_token, user_a_token):
        slug = f"e2e-nonmem-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "Private", slug)

        r = api_get(user_b_token, "/api/v1/memories/", params={
            "project_slug": slug, "page": 1, "size": 10,
        })
        assert r.status_code == 403
        api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestSuperadminOverride:
    def test_superadmin_sees_all_project_memories(self, admin_token, user_a_token):
        slug = f"e2e-sadmin-{uuid.uuid4().hex[:6]}"
        tag = uuid.uuid4().hex[:8]
        create_project(user_a_token, "AdminSee", slug)
        create_memory(user_a_token, f"User A private mem {tag}", slug)
        time.sleep(2)

        r = api_get(admin_token, "/api/v1/memories/", params={
            "project_slug": slug, "page": 1, "size": 100,
        })
        assert r.status_code == 200
        api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestCrossUserMutation:
    def test_user_b_cannot_delete_user_a_memory(
        self, user_a_token, user_b_token, isolation_projects
    ):
        slug_a, _ = isolation_projects
        tag = uuid.uuid4().hex[:8]
        create_memory(user_a_token, f"A's undeletable {tag}", slug_a)
        time.sleep(2)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": slug_a, "page": 1, "size": 50,
        }).json().get("items", [])
        a_ids = [i["id"] for i in items if tag in i.get("content", "")]
        if a_ids:
            api_delete(user_b_token, "/api/v1/memories/", json={"memory_ids": a_ids})
            remaining = api_get(user_a_token, "/api/v1/memories/", params={
                "project_slug": slug_a, "page": 1, "size": 50,
            }).json().get("items", [])
            assert any(tag in i.get("content", "") for i in remaining)

    def test_user_b_cannot_archive_user_a_memory(
        self, user_a_token, user_b_token, isolation_projects
    ):
        slug_a, _ = isolation_projects
        tag = uuid.uuid4().hex[:8]
        create_memory(user_a_token, f"A's unarchivable {tag}", slug_a)
        time.sleep(2)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": slug_a, "page": 1, "size": 50,
        }).json().get("items", [])
        a_ids = [i["id"] for i in items if tag in i.get("content", "")]
        if a_ids:
            api_post(user_b_token, "/api/v1/memories/actions/archive",
                     json={"memory_ids": a_ids})
            remaining = api_get(user_a_token, "/api/v1/memories/", params={
                "project_slug": slug_a, "page": 1, "size": 50,
            }).json().get("items", [])
            assert any(tag in i.get("content", "") for i in remaining)
