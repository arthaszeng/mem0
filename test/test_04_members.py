"""D: Member CRUD, role enforcement, removal."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, add_member, create_memory,
    create_auth_user, get_token, provision_api_user, purge_user,
)


@pytest.fixture()
def member_project(user_a_token):
    slug = f"e2e-member-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "MemberTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestListMembers:
    def test_list_members_includes_owner(self, user_a_token, member_project, user_a_name):
        r = api_get(user_a_token, f"/api/v1/projects/{member_project}/members")
        assert r.status_code == 200
        usernames = [m["username"] for m in r.json()]
        assert user_a_name in usernames


class TestAddMember:
    def test_add_member_with_role(self, user_a_token, member_project, user_b_name):
        r = api_post(user_a_token, f"/api/v1/projects/{member_project}/members", json={
            "username": user_b_name, "role": "read_write",
        })
        assert r.status_code == 200

    def test_add_duplicate_member(self, user_a_token, member_project, user_a_name):
        r = api_post(user_a_token, f"/api/v1/projects/{member_project}/members", json={
            "username": user_a_name, "role": "read_write",
        })
        assert r.status_code == 409

    def test_add_nonexistent_user(self, user_a_token, member_project):
        r = api_post(user_a_token, f"/api/v1/projects/{member_project}/members", json={
            "username": "no_such_user_xyz_999", "role": "read_write",
        })
        assert r.status_code == 404

    def test_non_admin_cannot_add(self, admin_token, user_b_token, user_b_name, user_a_name):
        slug = f"e2e-noadd-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "NoAdd", slug)
        add_member(admin_token, slug, user_b_name, "read_write")

        r = api_post(user_b_token, f"/api/v1/projects/{slug}/members", json={
            "username": user_a_name, "role": "read_only",
        })
        assert r.status_code == 403
        api_delete(admin_token, f"/api/v1/projects/{slug}")


class TestRemoveMember:
    def test_remove_member(self, user_a_token, user_b_name):
        slug = f"e2e-rem-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "RemTest", slug)
        add_member(user_a_token, slug, user_b_name, "read_write")

        r = api_delete(user_a_token, f"/api/v1/projects/{slug}/members/{user_b_name}")
        assert r.status_code == 200
        api_delete(user_a_token, f"/api/v1/projects/{slug}")

    def test_remove_nonmember(self, user_a_token, member_project):
        r = api_delete(user_a_token, f"/api/v1/projects/{member_project}/members/ghost_user")
        assert r.status_code == 404


class TestRemovedUserLosesAccess:
    def test_removed_user_cannot_access_project(self, user_a_token, user_b_token, user_b_name):
        slug = f"e2e-kickout-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "KickOut", slug)
        add_member(user_a_token, slug, user_b_name, "read_write")

        r = api_get(user_b_token, f"/api/v1/projects/{slug}")
        assert r.status_code == 200

        api_delete(user_a_token, f"/api/v1/projects/{slug}/members/{user_b_name}")
        time.sleep(1)

        r2 = api_get(user_b_token, f"/api/v1/projects/{slug}")
        assert r2.status_code == 403
        api_delete(user_a_token, f"/api/v1/projects/{slug}")
