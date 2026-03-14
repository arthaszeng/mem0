"""M: Batch archive/pause/delete/restore + cross-user edge cases."""

import time
import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, create_memory, add_member,
)

def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def batch_project(user_a_token):
    slug = f"e2e-batch-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "BatchTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


def _get_ids(token, slug, keyword):
    items = api_get(token, "/api/v1/memories/", params={
        "project_slug": slug, "page": 1, "size": 100,
    }).json().get("items", [])
    return [i["id"] for i in items if keyword in i.get("content", "")]


class TestBatchArchive:
    def test_batch_archive(self, user_a_token, batch_project):
        tag = _uid()
        create_memory(user_a_token, f"Batch arch 1 {tag}", batch_project)
        create_memory(user_a_token, f"Batch arch 2 {tag}", batch_project)
        time.sleep(2)
        ids = _get_ids(user_a_token, batch_project, tag)
        assert len(ids) >= 1
        r = api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": ids})
        assert r.status_code == 200

        remaining = _get_ids(user_a_token, batch_project, tag)
        assert len(remaining) == 0


class TestBatchPause:
    def test_batch_pause(self, user_a_token, batch_project):
        tag = _uid()
        create_memory(user_a_token, f"Batch pause {tag}", batch_project)
        time.sleep(2)
        ids = _get_ids(user_a_token, batch_project, tag)
        r = api_post(user_a_token, "/api/v1/memories/actions/pause", json={"memory_ids": ids})
        assert r.status_code == 200


class TestBatchRestore:
    def test_batch_restore_archived(self, user_a_token, batch_project):
        tag = _uid()
        create_memory(user_a_token, f"Batch restore me {tag}", batch_project)
        time.sleep(2)
        ids = _get_ids(user_a_token, batch_project, tag)
        assert ids
        api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": ids})
        r = api_post(user_a_token, "/api/v1/memories/actions/restore", json={"memory_ids": ids})
        assert r.status_code == 200
        restored = _get_ids(user_a_token, batch_project, tag)
        assert len(restored) >= 1


class TestBatchDelete:
    def test_batch_delete(self, user_a_token, batch_project):
        tag = _uid()
        create_memory(user_a_token, f"Batch del x1 {tag}", batch_project)
        create_memory(user_a_token, f"Batch del x2 {tag}", batch_project)
        time.sleep(2)
        ids = _get_ids(user_a_token, batch_project, tag)
        r = api_delete(user_a_token, "/api/v1/memories/", json={"memory_ids": ids})
        assert r.status_code == 200


class TestBatchCrossUser:
    def test_batch_with_other_users_ids(
        self, user_a_token, user_b_token, user_b_name, batch_project
    ):
        add_member(user_a_token, batch_project, user_b_name, "read_write")
        tag_a = _uid()
        tag_b = _uid()
        create_memory(user_a_token, f"A owns this batch {tag_a}", batch_project)
        create_memory(user_b_token, f"B owns this batch {tag_b}", batch_project)
        time.sleep(2)

        a_ids = _get_ids(user_a_token, batch_project, tag_a)
        b_ids = _get_ids(user_a_token, batch_project, tag_b)
        all_ids = a_ids + b_ids

        if all_ids:
            api_post(user_b_token, "/api/v1/memories/actions/archive", json={"memory_ids": all_ids})
            remaining_a = _get_ids(user_a_token, batch_project, tag_a)
            assert len(remaining_a) >= 1


class TestBatchEmptyList:
    def test_empty_list(self, user_a_token):
        r = api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": []})
        assert r.status_code in (200, 400, 422)

    def test_nonexistent_ids(self, user_a_token):
        fake_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        r = api_post(user_a_token, "/api/v1/memories/actions/archive", json={"memory_ids": fake_ids})
        assert r.status_code in (200, 404)
