"""E2E tests for config secret masking, text validation, error responses,
and member role update endpoint.

Covers bugs found in exploratory testing round 2:
- GET /config exposed api_key to non-superadmin
- Empty/whitespace text accepted on create & update
- Create memory returned 200 with error body on failure
- No endpoint to update member roles
"""

import time
import uuid

import pytest
from conftest import (
    api_get,
    api_post,
    api_put,
    api_delete,
    create_memory,
    create_project,
    add_member,
    provision_api_user,
    create_auth_user,
    get_token,
    purge_user,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def role_users(admin_token):
    """Create three users for role update tests."""
    users = {}
    for label in ("owner", "member", "outsider"):
        uname = f"e2e_role_{label}_{uuid.uuid4().hex[:6]}"
        pwd = f"Role{label.title()}1!"
        create_auth_user(admin_token, uname, pwd)
        tok = get_token(uname, pwd)
        provision_api_user(tok)
        users[label] = {"name": uname, "pwd": pwd, "token": tok}
    yield users
    for u in users.values():
        purge_user(admin_token, u["name"])
        api_delete(admin_token, f"/auth/users/{u['name']}")


@pytest.fixture(scope="module")
def role_project(role_users):
    slug = f"e2e-role-{uuid.uuid4().hex[:6]}"
    create_project(role_users["owner"]["token"], "Role Test Project", slug)
    return slug


# ===========================================================================
# 1. Config secret masking
# ===========================================================================

class TestConfigSecretMasking:
    def test_non_superadmin_sees_masked_api_key(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/config/")
        assert r.status_code == 200
        data = r.json()
        llm_key = data.get("mem0", {}).get("llm", {}).get("config", {}).get("api_key", "")
        emb_key = data.get("mem0", {}).get("embedder", {}).get("config", {}).get("api_key", "")
        assert llm_key == "***", f"Expected masked api_key, got: {llm_key}"
        assert emb_key == "***", f"Expected masked api_key, got: {emb_key}"

    def test_superadmin_sees_real_api_key(self, admin_token):
        r = api_get(admin_token, "/api/v1/config/")
        assert r.status_code == 200
        data = r.json()
        llm_key = data.get("mem0", {}).get("llm", {}).get("config", {}).get("api_key", "")
        assert llm_key != "***", "Superadmin should see real api_key"

    def test_non_superadmin_llm_endpoint_masked(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/config/mem0/llm")
        assert r.status_code == 200
        assert r.json().get("config", {}).get("api_key") == "***"

    def test_non_superadmin_embedder_endpoint_masked(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/config/mem0/embedder")
        assert r.status_code == 200
        assert r.json().get("config", {}).get("api_key") == "***"

    def test_non_superadmin_cannot_update_config(self, user_a_token):
        r = api_put(user_a_token, "/api/v1/config/", json={})
        assert r.status_code == 403

    def test_non_superadmin_cannot_reset_config(self, user_a_token):
        r = api_post(user_a_token, "/api/v1/config/reset")
        assert r.status_code == 403


# ===========================================================================
# 2. Text validation on create
# ===========================================================================

class TestCreateMemoryTextValidation:
    def _get_slug(self, token):
        r = api_get(token, "/api/v1/projects")
        return r.json()[0]["slug"]

    def test_empty_text_rejected(self, user_a_token):
        slug = self._get_slug(user_a_token)
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": "", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 400

    def test_whitespace_only_rejected(self, user_a_token):
        slug = self._get_slug(user_a_token)
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": "   ", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 400

    def test_newline_tab_rejected(self, user_a_token):
        slug = self._get_slug(user_a_token)
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": "\n\t\r", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 400

    def test_valid_text_accepted(self, user_a_token):
        slug = self._get_slug(user_a_token)
        tag = uuid.uuid4().hex[:8]
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": f"Valid memory content {tag}", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 200

    def test_unicode_text_accepted(self, user_a_token):
        slug = self._get_slug(user_a_token)
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": "测试中文记忆 日本語テスト العربية", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 200


# ===========================================================================
# 3. Text validation on update
# ===========================================================================

class TestUpdateMemoryTextValidation:
    @pytest.fixture(autouse=True)
    def _setup_memory(self, user_a_token):
        slug = api_get(user_a_token, "/api/v1/projects").json()[0]["slug"]
        tag = uuid.uuid4().hex[:8]
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": f"Updatable memory {tag}", "infer": False, "project_slug": slug,
        })
        assert r.status_code == 200
        time.sleep(1)
        mems = api_get(user_a_token, f"/api/v1/memories/?project_slug={slug}").json().get("items", [])
        self.memory_id = str(mems[0]["id"])
        self.token = user_a_token

    def test_update_empty_rejected(self):
        r = api_put(self.token, f"/api/v1/memories/{self.memory_id}", json={"memory_content": ""})
        assert r.status_code == 400

    def test_update_whitespace_rejected(self):
        r = api_put(self.token, f"/api/v1/memories/{self.memory_id}", json={"memory_content": "   "})
        assert r.status_code == 400

    def test_update_valid_content(self):
        r = api_put(self.token, f"/api/v1/memories/{self.memory_id}",
                    json={"memory_content": "Updated content"})
        assert r.status_code == 200


# ===========================================================================
# 4. Member role update endpoint
# ===========================================================================

class TestMemberRoleUpdate:
    def test_add_member_and_update_role(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        member_name = role_users["member"]["name"]

        add_member(owner_tok, role_project, member_name, "read_only")

        members = api_get(owner_tok, f"/api/v1/projects/{role_project}/members").json()
        member_entry = next(m for m in members if m["username"] == member_name)
        assert member_entry["role"] == "read_only"

        r = api_put(owner_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                    json={"role": "read_write"})
        assert r.status_code == 200

        members = api_get(owner_tok, f"/api/v1/projects/{role_project}/members").json()
        member_entry = next(m for m in members if m["username"] == member_name)
        assert member_entry["role"] == "read_write"

    def test_read_write_can_create_after_upgrade(self, role_users, role_project):
        member_tok = role_users["member"]["token"]
        tag = uuid.uuid4().hex[:8]
        r = api_post(member_tok, "/api/v1/memories/", json={
            "text": f"Member writes after upgrade {tag}",
            "infer": False,
            "project_slug": role_project,
        })
        assert r.status_code == 200

    def test_cannot_update_owner_role(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        owner_name = role_users["owner"]["name"]

        r = api_put(owner_tok, f"/api/v1/projects/{role_project}/members/{owner_name}",
                    json={"role": "read_only"})
        assert r.status_code == 400

    def test_cannot_assign_owner_role(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        member_name = role_users["member"]["name"]

        r = api_put(owner_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                    json={"role": "owner"})
        assert r.status_code == 400

    def test_non_member_cannot_update_roles(self, role_users, role_project):
        outsider_tok = role_users["outsider"]["token"]
        member_name = role_users["member"]["name"]

        r = api_put(outsider_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                    json={"role": "admin"})
        assert r.status_code == 403

    def test_self_escalation_blocked(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        member_name = role_users["member"]["name"]
        member_tok = role_users["member"]["token"]

        api_put(owner_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                json={"role": "admin"})

        r = api_put(member_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                    json={"role": "admin"})
        assert r.status_code == 403

    def test_invalid_role_rejected(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        member_name = role_users["member"]["name"]

        r = api_put(owner_tok, f"/api/v1/projects/{role_project}/members/{member_name}",
                    json={"role": "superadmin"})
        assert r.status_code == 400

    def test_update_nonexistent_member(self, role_users, role_project):
        owner_tok = role_users["owner"]["token"]
        r = api_put(owner_tok, f"/api/v1/projects/{role_project}/members/nonexistent_user_xyz",
                    json={"role": "read_write"})
        assert r.status_code == 404


# ===========================================================================
# 5. Invite system edge cases
# ===========================================================================

class TestInviteEdgeCases:
    @pytest.fixture(autouse=True)
    def _setup_project(self, role_users, role_project):
        self.project = role_project
        self.owner_tok = role_users["owner"]["token"]
        self.outsider_tok = role_users["outsider"]["token"]

    def test_invite_create_accept_flow(self):
        r = api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites",
                     json={"role": "read_only"})
        assert r.status_code == 200
        token = r.json()["token"]

        r = api_get(self.outsider_tok, f"/api/v1/projects/invites/{token}/info")
        assert r.status_code == 200

        r = api_post(self.outsider_tok, f"/api/v1/projects/invites/{token}/accept")
        assert r.status_code == 200

    def test_reaccept_same_invite_fails(self):
        r = api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites",
                     json={"role": "read_only"})
        token = r.json()["token"]

        api_post(self.outsider_tok, f"/api/v1/projects/invites/{token}/accept")
        r = api_post(self.outsider_tok, f"/api/v1/projects/invites/{token}/accept")
        assert r.status_code in (400, 409)

    def test_owner_role_invite_rejected(self):
        r = api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites",
                     json={"role": "owner"})
        assert r.status_code == 400

    def test_invalid_role_invite_rejected(self):
        r = api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites",
                     json={"role": "superadmin"})
        assert r.status_code == 400

    def test_revoked_invite_cannot_be_accepted(self, admin_token):
        uname = f"e2e_inv_{uuid.uuid4().hex[:6]}"
        create_auth_user(admin_token, uname, "InvTest1!")
        tok = get_token(uname, "InvTest1!")
        provision_api_user(tok)

        r = api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites",
                     json={"role": "read_only"})
        token = r.json()["token"]

        api_post(self.owner_tok, f"/api/v1/projects/{self.project}/invites/revoke",
                 json={"token": token})

        r = api_post(tok, f"/api/v1/projects/invites/{token}/accept")
        assert r.status_code == 400

        purge_user(admin_token, uname)
        api_delete(admin_token, f"/auth/users/{uname}")

    def test_bogus_token_rejected(self):
        r = api_post(self.outsider_tok, "/api/v1/projects/invites/bogus-fake-token/accept")
        assert r.status_code == 404
