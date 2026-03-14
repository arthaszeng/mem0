"""K: Agent instructions CRUD + isolation."""

import uuid
import pytest

from conftest import (
    api_get, api_put, api_delete,
    create_project,
)


@pytest.fixture()
def instr_project(user_a_token):
    slug = f"e2e-instr-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "InstrTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestAgentInstructionsCRUD:
    def test_create_instruction(self, user_a_token, instr_project):
        r = api_put(user_a_token, "/api/v1/memories/agent-instructions/cursor", json={
            "instructions": "Extract coding decisions only",
        }, params={"project_slug": instr_project})
        assert r.status_code == 200

    def test_get_instruction(self, user_a_token, instr_project):
        api_put(user_a_token, "/api/v1/memories/agent-instructions/test-agent", json={
            "instructions": "Test instructions",
        }, params={"project_slug": instr_project})
        r = api_get(user_a_token, "/api/v1/memories/agent-instructions/test-agent",
                    params={"project_slug": instr_project})
        assert r.status_code == 200

    def test_update_instruction(self, user_a_token, instr_project):
        api_put(user_a_token, "/api/v1/memories/agent-instructions/update-agent", json={
            "instructions": "V1",
        }, params={"project_slug": instr_project})
        r = api_put(user_a_token, "/api/v1/memories/agent-instructions/update-agent", json={
            "instructions": "V2 updated",
        }, params={"project_slug": instr_project})
        assert r.status_code == 200

    def test_delete_instruction(self, user_a_token, instr_project):
        api_put(user_a_token, "/api/v1/memories/agent-instructions/del-agent", json={
            "instructions": "Will be deleted",
        }, params={"project_slug": instr_project})
        r = api_delete(user_a_token, "/api/v1/memories/agent-instructions/del-agent",
                       params={"project_slug": instr_project})
        assert r.status_code == 200

    def test_list_instructions(self, user_a_token, instr_project):
        r = api_get(user_a_token, "/api/v1/memories/agent-instructions",
                    params={"project_slug": instr_project})
        assert r.status_code == 200


class TestInstructionIsolation:
    def test_user_b_cannot_see_user_a_instructions(
        self, user_a_token, user_b_token, instr_project
    ):
        api_put(user_a_token, "/api/v1/memories/agent-instructions/private-agent", json={
            "instructions": "Private to A",
        }, params={"project_slug": instr_project})

        r = api_get(user_b_token, "/api/v1/memories/agent-instructions/private-agent",
                    params={"project_slug": instr_project})
        assert r.status_code in (403, 404)

    def test_nonexistent_agent(self, user_a_token, instr_project):
        r = api_get(user_a_token, "/api/v1/memories/agent-instructions/no-such-agent-xyz",
                    params={"project_slug": instr_project})
        assert r.status_code == 404
