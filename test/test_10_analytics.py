"""J: Analytics, insights, stats endpoints."""

import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, create_memory,
)


class TestAnalytics:
    def test_analytics_returns_structure(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/stats/analytics")
        assert r.status_code == 200
        data = r.json()
        assert "memory_growth" in data
        assert "category_distribution" in data
        assert "agent_activity" in data
        assert "recent_activity" in data

    def test_analytics_scoped_to_project(self, user_a_token):
        slug = f"e2e-analy-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "AnalyticsTest", slug)
        create_memory(user_a_token, "Analytics scoped memory", slug)
        r = api_get(user_a_token, "/api/v1/memories/stats/analytics", params={
            "project_slug": slug,
        })
        assert r.status_code == 200
        api_delete(user_a_token, f"/api/v1/projects/{slug}")

    def test_analytics_empty_project(self, user_a_token):
        slug = f"e2e-emptystat-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "EmptyStat", slug)
        r = api_get(user_a_token, "/api/v1/memories/stats/analytics", params={
            "project_slug": slug,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["recent_activity"]["total_active"] == 0
        api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestInsights:
    def test_insights_returns_structure(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/stats/insights")
        assert r.status_code == 200
        data = r.json()
        assert "topic_trends" in data
        assert "knowledge_coverage" in data

    def test_insights_refresh(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/stats/insights", params={"refresh": "true"})
        assert r.status_code == 200

    def test_insights_empty_project(self, user_a_token):
        slug = f"e2e-emptyins-{uuid.uuid4().hex[:6]}"
        create_project(user_a_token, "EmptyInsights", slug)
        r = api_get(user_a_token, "/api/v1/memories/stats/insights", params={
            "project_slug": slug,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["knowledge_coverage"]["total_categories"] == 0
        api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestStatsEndpoints:
    def test_types_endpoint(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/stats/types")
        assert r.status_code == 200

    def test_agents_endpoint(self, admin_token):
        r = api_get(admin_token, "/api/v1/memories/stats/agents")
        assert r.status_code == 200
