"""N: Graph entities, search entities."""

import pytest

from conftest import api_get


class TestListEntities:
    def test_list_entities(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/")
        assert r.status_code == 200

    def test_list_entities_empty_ok(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/entities/")
        assert r.status_code == 200


class TestSearchEntities:
    def test_search_entities(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/search", params={"query": "OpenMemory"})
        assert r.status_code == 200

    def test_search_entities_no_match(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/search", params={"query": "zzz_nonexistent_xyz"})
        assert r.status_code == 200


class TestGraphData:
    def test_get_graph(self, admin_token):
        r = api_get(admin_token, "/api/v1/entities/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data or "entities" in data or isinstance(data, list)
