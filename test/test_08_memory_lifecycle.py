"""H: TTL, archive, pause, restore, delete states."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, create_memory,
)

def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def lifecycle_project(user_a_token):
    slug = f"e2e-life-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "LifecycleTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


def _get_memory_ids(token, slug, keyword):
    items = api_get(token, "/api/v1/memories/", params={
        "project_slug": slug, "page": 1, "size": 100,
    }).json().get("items", [])
    return [i["id"] for i in items if keyword in i.get("content", "")]


class TestArchive:
    def test_archive_and_restore(self, user_a_token, lifecycle_project):
        tag = _uid()
        create_memory(user_a_token, f"Archive me lifecycle {tag}", lifecycle_project)
        time.sleep(2)
        ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert ids

        r = api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": ids})
        assert r.status_code == 200

        active_ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert len(active_ids) == 0

        r2 = api_post(user_a_token, "/api/v1/memories/actions/restore", json={"memory_ids": ids})
        assert r2.status_code == 200

        restored_ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert len(restored_ids) >= 1


class TestPause:
    def test_pause_excludes_from_list(self, user_a_token, lifecycle_project):
        tag = _uid()
        create_memory(user_a_token, f"Pause me lifecycle {tag}", lifecycle_project)
        time.sleep(2)
        ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert ids

        r = api_post(user_a_token, "/api/v1/memories/actions/pause", json={"memory_ids": ids})
        assert r.status_code == 200

        active_ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert len(active_ids) == 0

        r2 = api_post(user_a_token, "/api/v1/memories/actions/restore", json={"memory_ids": ids})
        assert r2.status_code == 200


class TestDelete:
    def test_deleted_memory_excluded(self, user_a_token, lifecycle_project):
        tag = _uid()
        create_memory(user_a_token, f"Delete me lifecycle {tag}", lifecycle_project)
        time.sleep(2)
        ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert ids

        r = api_delete(user_a_token, "/api/v1/memories/", json={"memory_ids": ids})
        assert r.status_code == 200

        remaining = _get_memory_ids(user_a_token, lifecycle_project, tag)
        assert len(remaining) == 0


class TestEdgeCases:
    def test_archive_already_archived(self, user_a_token, lifecycle_project):
        tag = _uid()
        create_memory(user_a_token, f"Double archive lifecycle {tag}", lifecycle_project)
        time.sleep(2)
        ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        if ids:
            api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": ids})
            r = api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": ids})
            assert r.status_code == 200

    def test_restore_non_archived(self, user_a_token, lifecycle_project):
        tag = _uid()
        create_memory(user_a_token, f"Not archived lifecycle {tag}", lifecycle_project)
        time.sleep(2)
        ids = _get_memory_ids(user_a_token, lifecycle_project, tag)
        if ids:
            r = api_post(user_a_token, "/api/v1/memories/actions/restore", json={"memory_ids": ids})
            assert r.status_code == 200


class TestExpiresAt:
    def test_create_with_expires(self, user_a_token, lifecycle_project):
        r = api_post(user_a_token, "/api/v1/memories/", json={
            "text": f"Expiring memory lifecycle {_uid()}",
            "infer": False,
            "expires_at": "2099-12-31T23:59:59Z",
            "project_slug": lifecycle_project,
        })
        assert r.status_code == 200
