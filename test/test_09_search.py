"""I: Search, filter, categories, domains."""

import uuid
import time
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, create_memory,
)


@pytest.fixture(scope="module")
def search_project(user_a_token):
    slug = f"e2e-search-{uuid.uuid4().hex[:6]}"
    create_project(user_a_token, "SearchTest", slug)
    create_memory(user_a_token, "Python is a great programming language for data science", slug)
    create_memory(user_a_token, "Docker containers simplify deployment workflows", slug)
    create_memory(user_a_token, "React is a frontend JavaScript framework", slug)
    time.sleep(2)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestSearch:
    def test_search_by_query(self, user_a_token, search_project):
        r = api_post(user_a_token, "/api/v1/memories/search", json={
            "query": "programming language",
            "project_slug": search_project,
        })
        assert r.status_code == 200

    def test_search_with_limit(self, user_a_token, search_project):
        r = api_post(user_a_token, "/api/v1/memories/search", json={
            "query": "technology",
            "project_slug": search_project,
            "limit": 1,
        })
        assert r.status_code == 200

    def test_search_returns_score(self, user_a_token, search_project):
        r = api_post(user_a_token, "/api/v1/memories/search", json={
            "query": "Docker deployment",
            "project_slug": search_project,
        })
        assert r.status_code == 200
        results = r.json().get("results", r.json().get("memories", []))
        if results:
            assert "score" in results[0] or "dist" in results[0]


class TestSearchIsolation:
    def test_search_respects_project(self, user_a_token, search_project):
        other_slug = f"e2e-searchiso-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "SearchIso", other_slug)
        create_memory(user_a_token, "Unique xylophone memory for isolation test", other_slug)
        time.sleep(1)

        r = api_post(user_a_token, "/api/v1/memories/search", json={
            "query": "xylophone",
            "project_slug": search_project,
        })
        results = r.json().get("results", r.json().get("memories", []))
        texts = [m.get("memory", m.get("content", "")) for m in results]
        assert not any("xylophone" in t for t in texts)
        api_delete(user_a_token, f"/api/v1/projects/{other_slug}")


class TestSearchFilters:
    def test_search_with_categories(self, user_a_token, search_project):
        r = api_post(user_a_token, "/api/v1/memories/search", json={
            "query": "anything",
            "project_slug": search_project,
            "categories": [],
        })
        assert r.status_code == 200
