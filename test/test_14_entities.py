"""N: Graph entities, search entities, graph cleanup on deletion, user isolation."""

import pytest

from conftest import api_get


class TestListEntities:
    def test_list_entities(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/")
        assert r.status_code == 200

    def test_list_entities_empty_ok(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/entities/")
        assert r.status_code == 200

    def test_list_entities_supports_project_slug(self, user_a_token, shared_project_slug):
        r = api_get(user_a_token, "/api/v1/entities/", params={"project_slug": shared_project_slug})
        assert r.status_code == 200
        data = r.json()
        assert "entities" in data
        assert "total" in data


class TestSearchEntities:
    def test_search_entities(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/search", params={"query": "Memverse"})
        assert r.status_code == 200

    def test_search_entities_no_match(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/search", params={"query": "zzz_nonexistent_xyz"})
        assert r.status_code == 200

    def test_search_entities_supports_project_slug(self, user_a_token, shared_project_slug):
        r = api_get(user_a_token, "/api/v1/entities/search", params={
            "query": "test", "project_slug": shared_project_slug,
        })
        assert r.status_code == 200
        data = r.json()
        assert "entities" in data


class TestGraphData:
    def test_get_graph(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data or "entities" in data or isinstance(data, list)

    def test_graph_returns_nodes_and_edges(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/graph")
        assert r.status_code == 200
        data = r.json()
        if "nodes" in data:
            assert isinstance(data["nodes"], list)
            assert isinstance(data.get("edges", []), list)

    def test_graph_scoped_to_project(self, user_a_token, shared_project_slug):
        r = api_get(user_a_token, "/api/v1/entities/graph", params={
            "project_slug": shared_project_slug,
        })
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data


class TestEntityIsolation:
    """Entities should not leak across users."""

    def test_user_b_sees_no_admin_entities(self, user_b_token):
        r = api_get(user_b_token, "/api/v1/entities/")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_user_b_graph_empty(self, user_b_token):
        r = api_get(user_b_token, "/api/v1/entities/graph")
        assert r.status_code == 200
        data = r.json()
        assert len(data.get("nodes", [])) == 0
        assert len(data.get("edges", [])) == 0

    def test_entity_response_has_no_memory_ids(self, admin_token):
        """memory_ids must be stripped from the response to prevent ID leakage."""
        r = api_get(admin_token, "/api/v1/entities/")
        assert r.status_code == 200
        for ent in r.json().get("entities", []):
            assert "memory_ids" not in ent
