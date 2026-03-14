"""F: Memory create/read/update/delete."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_put, api_delete,
    create_project, create_memory,
)

def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def crud_project(user_a_token):
    slug = f"e2e-crud-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "CRUDTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestCreateMemory:
    def test_create_in_project(self, user_a_token, crud_project):
        r = create_memory(user_a_token, "E2E create test in project", crud_project)
        assert r.status_code == 200

    def test_create_without_project(self, user_a_token):
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": f"No project memory e2e {_uid()}", "infer": False})
        assert r.status_code == 200

    def test_create_with_metadata(self, user_a_token, crud_project):
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": f"Typed memory e2e {_uid()}",
            "infer": False,
            "memory_type": "fact",
            "agent_id": "cursor",
            "run_id": "test-run-001",
            "project_slug": crud_project,
        })
        assert r.status_code == 200


class TestListMemories:
    def test_list_paginated(self, user_a_token, crud_project):
        create_memory(user_a_token, f"List test mem A {_uid()}", crud_project)
        create_memory(user_a_token, f"List test mem B {_uid()}", crud_project)
        time.sleep(3)
        r = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project, "page": 1, "size": 10,
        })
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1


class TestGetMemory:
    def test_get_single_memory(self, user_a_token, crud_project):
        create_memory(user_a_token, f"Single get test {_uid()}", crud_project)
        time.sleep(3)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project, "page": 1, "size": 1,
        }).json()["items"]
        if items:
            mid = items[0]["id"]
            r = api_get(user_a_token, f"/api/v1/memories/{mid}")
            assert r.status_code == 200

    def test_nonexistent_memory(self, user_a_token):
        fake_id = uuid.uuid4()
        r = api_get(user_a_token, f"/api/v1/memories/{fake_id}")
        assert r.status_code == 404


class TestUpdateMemory:
    def test_update_content(self, user_a_token, crud_project):
        tag = _uid()
        create_memory(user_a_token, f"Before update {tag}", crud_project)
        time.sleep(3)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project, "page": 1, "size": 50,
        }).json()["items"]
        target = next((i for i in items if tag in i.get("content", "")), None)
        if target:
            r = api_put(user_a_token, f"/api/v1/memories/{target['id']}", json={
                "memory_content": f"After update {tag}",
            })
            assert r.status_code == 200


class TestDeleteMemory:
    def test_delete_single(self, user_a_token, crud_project):
        tag = _uid()
        create_memory(user_a_token, f"To be deleted {tag}", crud_project)
        time.sleep(3)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project, "page": 1, "size": 50,
        }).json()["items"]
        target = next((i for i in items if tag in i.get("content", "")), None)
        if target:
            r = api_delete(user_a_token, "/api/v1/memories/", json={
                "memory_ids": [target["id"]],
                "project_slug": crud_project,
            })
            assert r.status_code == 200

    def test_bulk_delete(self, user_a_token, crud_project):
        tag = _uid()
        create_memory(user_a_token, f"Bulk del A {tag}", crud_project)
        create_memory(user_a_token, f"Bulk del B {tag}", crud_project)
        time.sleep(3)
        items = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project, "page": 1, "size": 50,
        }).json()["items"]
        ids = [i["id"] for i in items if tag in i.get("content", "")][:2]
        if ids:
            r = api_delete(user_a_token, "/api/v1/memories/", json={"memory_ids": ids})
            assert r.status_code == 200


class TestCategoriesAndDomains:
    def test_get_categories(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/memories/categories")
        assert r.status_code == 200

    def test_get_domains(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/memories/domains")
        assert r.status_code == 200


class TestFilterMemories:
    def test_filter_by_memory_type(self, user_a_token, crud_project):
        r = api_get(user_a_token, "/api/v1/memories/", params={
            "project_slug": crud_project,
            "memory_type": "fact",
            "page": 1, "size": 10,
        })
        assert r.status_code == 200
