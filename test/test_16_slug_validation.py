"""F: Project slug validation — reserved words, format, and owner self-removal."""

import uuid
import pytest

from conftest import (
    api_get, api_post, api_delete,
    create_project, add_member,
)


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def owner_project(user_a_token):
    slug = f"e2e-slug-{_uid()}"
    create_project(user_a_token, "SlugTest", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestReservedSlugs:
    """Reserved route names must be rejected as project slugs."""

    RESERVED = [
        "login", "settings", "admin", "invite", "change-password",
        "api", "api-keys", "projects", "memory", "memories", "apps",
        "auth", "memory-mcp", "concierge-mcp", "health",
    ]

    @pytest.mark.parametrize("slug", RESERVED)
    def test_reserved_slug_rejected(self, user_a_token, slug):
        r = api_post(user_a_token, "/api/v1/projects", json={
            "name": f"Test {slug}", "slug": slug,
        })
        assert r.status_code == 400, f"Slug '{slug}' should be rejected: {r.text}"
        assert "reserved" in r.json()["detail"].lower()


class TestSlugFormat:
    """Slug format validation — length, characters, traversal."""

    BAD_SLUGS = [
        ("../traversal", "path traversal"),
        ("HAS-UPPER", "uppercase"),
        ("has spaces", "spaces"),
        ("has@special", "special chars"),
        ("<script>x</script>", "XSS attempt"),
        ("-starts-with-dash", "leading dash"),
        ("a" * 100, "too long"),
    ]

    @pytest.mark.parametrize("slug,desc", BAD_SLUGS, ids=[d for _, d in BAD_SLUGS])
    def test_bad_slug_rejected(self, user_a_token, slug, desc):
        r = api_post(user_a_token, "/api/v1/projects", json={
            "name": "Test", "slug": slug,
        })
        assert r.status_code == 400, f"{desc}: slug={slug!r} should be rejected: {r.text}"

    GOOD_SLUGS = [
        "a",
        "abc",
        "my-project",
        "test-123",
        "a1b2c3",
    ]

    @pytest.mark.parametrize("slug", GOOD_SLUGS)
    def test_good_slug_accepted(self, user_a_token, slug):
        actual = f"{slug}-{_uid()}"
        r = api_post(user_a_token, "/api/v1/projects", json={
            "name": "Test", "slug": actual,
        })
        assert r.status_code == 200, f"Valid slug {actual!r} should be accepted: {r.text}"
        api_delete(user_a_token, f"/api/v1/projects/{actual}")

    def test_auto_slug_from_name(self, user_a_token):
        """When slug is omitted, it is derived from the name."""
        name = f"My Cool Project {_uid()}"
        r = api_post(user_a_token, "/api/v1/projects", json={"name": name})
        assert r.status_code == 200
        slug = r.json()["slug"]
        assert slug.startswith("my-cool-project-")
        api_delete(user_a_token, f"/api/v1/projects/{slug}")


class TestOwnerSelfRemoval:
    """Owner should not be able to remove themselves from a project."""

    def test_owner_cannot_remove_self(self, user_a_token, user_a_name, owner_project):
        r = api_delete(user_a_token, f"/api/v1/projects/{owner_project}/members/{user_a_name}")
        assert r.status_code == 400
        assert "owner" in r.json()["detail"].lower()

    def test_admin_can_be_removed(self, user_a_token, user_b_token, user_b_name, owner_project):
        """Non-owner members CAN be removed."""
        add_member(user_a_token, owner_project, user_b_name, "admin")
        r = api_delete(user_a_token, f"/api/v1/projects/{owner_project}/members/{user_b_name}")
        assert r.status_code == 200

    def test_owner_still_functional_after_attempted_self_removal(
        self, user_a_token, user_a_name, owner_project,
    ):
        """After the rejected self-removal, the owner can still access the project."""
        api_delete(user_a_token, f"/api/v1/projects/{owner_project}/members/{user_a_name}")
        r = api_get(user_a_token, f"/api/v1/projects/{owner_project}")
        assert r.status_code == 200
        assert r.json()["slug"] == owner_project
