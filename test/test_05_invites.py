"""E: Invite lifecycle, accept, revoke, expiry."""

import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, add_member,
    create_auth_user, get_token, provision_api_user, purge_user,
)


@pytest.fixture()
def invite_project(user_a_token):
    slug = f"e2e-invite-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "InviteTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


def _create_invite(token, slug, role="read_write", expires_in_days=7):
    r = api_post(token, f"/api/v1/projects/{slug}/invites", json={
        "role": role, "expires_in_days": expires_in_days,
    })
    return r


class TestCreateInvite:
    def test_happy_path(self, user_a_token, invite_project):
        r = _create_invite(user_a_token, invite_project)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["role"] == "read_write"
        assert data["status"] == "pending"

    def test_admin_role_invite(self, user_a_token, invite_project):
        r = _create_invite(user_a_token, invite_project, role="admin")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_cannot_create_owner_invite(self, user_a_token, invite_project):
        r = _create_invite(user_a_token, invite_project, role="owner")
        assert r.status_code == 400

    def test_invalid_role(self, user_a_token, invite_project):
        r = _create_invite(user_a_token, invite_project, role="superuser")
        assert r.status_code == 400

    def test_non_admin_cannot_invite(self, user_a_token, user_b_token, user_b_name, invite_project):
        add_member(user_a_token, invite_project, user_b_name, "read_write")
        r = _create_invite(user_b_token, invite_project)
        assert r.status_code == 403


class TestListInvites:
    def test_list_invites(self, user_a_token, invite_project):
        _create_invite(user_a_token, invite_project)
        _create_invite(user_a_token, invite_project, role="read_only")
        r = api_get(user_a_token, f"/api/v1/projects/{invite_project}/invites")
        assert r.status_code == 200
        assert len(r.json()) >= 2


class TestInviteInfo:
    def test_get_info(self, user_a_token, invite_project):
        inv = _create_invite(user_a_token, invite_project).json()
        r = api_get(user_a_token, f"/api/v1/projects/invites/{inv['token']}/info")
        assert r.status_code == 200
        assert r.json()["project_name"] == "InviteTest"

    def test_nonexistent_token(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/projects/invites/fake_token_xyz/info")
        assert r.status_code == 404


class TestAcceptInvite:
    def test_accept_happy_path(self, admin_token, user_b_token, user_b_name):
        slug = f"e2e-accept-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "AcceptTest", slug)
        inv = _create_invite(admin_token, slug).json()

        r = api_post(user_b_token, f"/api/v1/projects/invites/{inv['token']}/accept")
        assert r.status_code == 200

        members = api_get(admin_token, f"/api/v1/projects/{slug}/members").json()
        usernames = [m["username"] for m in members]
        assert user_b_name in usernames
        api_delete(admin_token, f"/api/v1/projects/{slug}")

    def test_accept_revoked(self, admin_token, user_b_token):
        slug = f"e2e-revoked-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "RevokedTest", slug)
        inv = _create_invite(admin_token, slug).json()
        api_post(admin_token, f"/api/v1/projects/{slug}/invites/revoke", json={"token": inv["token"]})

        r = api_post(user_b_token, f"/api/v1/projects/invites/{inv['token']}/accept")
        assert r.status_code == 400
        api_delete(admin_token, f"/api/v1/projects/{slug}")

    def test_accept_already_accepted(self, admin_token, user_b_token):
        slug = f"e2e-double-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "DoubleAccept", slug)
        inv = _create_invite(admin_token, slug).json()
        api_post(user_b_token, f"/api/v1/projects/invites/{inv['token']}/accept")

        r = api_post(user_b_token, f"/api/v1/projects/invites/{inv['token']}/accept")
        assert r.status_code == 400
        api_delete(admin_token, f"/api/v1/projects/{slug}")

    def test_already_member_tries_accept(self, admin_token, user_b_token, user_b_name):
        slug = f"e2e-alrmem-{uuid.uuid4().hex[:6]}"
        create_project(admin_token, "AlreadyMember", slug)
        add_member(admin_token, slug, user_b_name, "read_write")
        inv = _create_invite(admin_token, slug).json()

        r = api_post(user_b_token, f"/api/v1/projects/invites/{inv['token']}/accept")
        assert r.status_code == 409
        api_delete(admin_token, f"/api/v1/projects/{slug}")
