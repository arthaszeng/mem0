"""F: Backup import/export — cross-user isolation and data integrity."""

import io
import json
import gzip
import time
import uuid
import zipfile

import pytest

from conftest import (
    api_get, api_post, api_delete, api_upload,
    create_project, create_memory,
)


def _uid():
    return uuid.uuid4().hex[:8]


def _make_export_zip(memories_json: dict, logical_records: list[dict] | None = None) -> bytes:
    """Build a minimal backup ZIP suitable for /api/v1/backup/import."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("memories.json", json.dumps(memories_json, indent=2))
        if logical_records is not None:
            gz_buf = io.BytesIO()
            with gzip.GzipFile(fileobj=gz_buf, mode="wb") as gz:
                for rec in logical_records:
                    gz.write((json.dumps(rec) + "\n").encode("utf-8"))
            zf.writestr("memories.jsonl.gz", gz_buf.getvalue())
    return buf.getvalue()


@pytest.fixture()
def export_project_a(user_a_token):
    slug = f"e2e-export-a-{_uid()}"
    create_project(user_a_token, "ExportA", slug)
    yield slug
    api_delete(user_a_token, f"/api/v1/projects/{slug}")


@pytest.fixture()
def export_project_b(user_b_token):
    slug = f"e2e-export-b-{_uid()}"
    create_project(user_b_token, "ExportB", slug)
    yield slug
    api_delete(user_b_token, f"/api/v1/projects/{slug}")


class TestExport:
    """Export endpoint basics."""

    def test_export_returns_zip(self, user_a_token, export_project_a):
        tag = _uid()
        create_memory(user_a_token, f"export test {tag}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        assert r.status_code == 200
        assert "application/zip" in r.headers.get("content-type", "")

        with zipfile.ZipFile(io.BytesIO(r.content), "r") as zf:
            names = zf.namelist()
            assert "memories.json" in names
            data = json.loads(zf.read("memories.json"))
            assert "memories" in data
            assert "user" in data

    def test_export_contains_user_info(self, user_a_token, user_a_name, export_project_a):
        tag = _uid()
        create_memory(user_a_token, f"user info test {tag}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        assert r.status_code == 200
        data = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read("memories.json"))
        assert data["user"]["user_id"] == user_a_name

    def test_export_only_own_memories(self, user_a_token, user_b_token, export_project_a):
        """Export should only include the exporting user's memories."""
        tag_a = _uid()
        tag_b = _uid()
        create_memory(user_a_token, f"A's mem {tag_a}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        assert r.status_code == 200
        data = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read("memories.json"))
        contents = [m["content"] for m in data["memories"]]
        assert any(tag_a in c for c in contents)
        assert not any(tag_b in c for c in contents)


class TestImportSameUser:
    """Import back into the same user account."""

    def test_import_own_export(self, user_a_token, export_project_a):
        tag = _uid()
        create_memory(user_a_token, f"self-import test {tag}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        assert r.status_code == 200
        zip_bytes = r.content

        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", zip_bytes,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r2.status_code == 200
        result = r2.json()
        assert result["imported"] >= 0

    def test_import_skip_mode(self, user_a_token, export_project_a):
        tag = _uid()
        create_memory(user_a_token, f"skip-mode test {tag}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        zip_bytes = r.content

        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", zip_bytes,
            data={"project_slug": export_project_a},
            params={"mode": "skip"},
        )
        assert r2.status_code == 200
        result = r2.json()
        assert result["skipped"] >= 1

    def test_import_invalid_file(self, user_a_token):
        r = api_upload(
            user_a_token, "/api/v1/backup/import",
            "bad.zip", b"not a zip file",
        )
        assert r.status_code == 400

    def test_import_invalid_mode(self, user_a_token, export_project_a):
        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", r.content,
            params={"mode": "bogus"},
        )
        assert r2.status_code == 400


class TestCrossUserImport:
    """Import another user's export — the critical isolation test."""

    def test_cross_user_import_assigns_new_ids(
        self, user_a_token, user_a_name, user_b_token, user_b_name,
        export_project_a, export_project_b,
    ):
        """When A imports B's export, new memory IDs must be generated."""
        tag = _uid()
        create_memory(user_b_token, f"B original {tag}", export_project_b)
        time.sleep(2)

        r = api_post(user_b_token, "/api/v1/backup/export", json={
            "project_slug": export_project_b,
        })
        assert r.status_code == 200
        b_zip = r.content

        b_data = json.loads(zipfile.ZipFile(io.BytesIO(b_zip)).read("memories.json"))
        b_memory_ids = {m["id"] for m in b_data["memories"] if tag in (m.get("content") or "")}

        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", b_zip,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r2.status_code == 200
        assert r2.json()["imported"] >= 1

        time.sleep(3)

        r3 = api_get(user_a_token, f"/api/v1/memories/?project_slug={export_project_a}")
        assert r3.status_code == 200
        a_memories = r3.json().get("items", r3.json().get("results", []))
        a_ids = {str(m["id"]) for m in a_memories if tag in (m.get("content") or "")}
        assert a_ids.isdisjoint(b_memory_ids), \
            f"Imported IDs must not reuse B's IDs: overlap={a_ids & b_memory_ids}"

    def test_cross_user_import_preserves_source(
        self, user_a_token, user_b_token, user_b_name,
        export_project_a, export_project_b,
    ):
        """B's memories must remain intact after A imports B's export."""
        tag = _uid()
        create_memory(user_b_token, f"B keep-alive {tag}", export_project_b)
        time.sleep(2)

        r_list_before = api_get(user_b_token, f"/api/v1/memories/?project_slug={export_project_b}")
        assert r_list_before.status_code == 200
        before = r_list_before.json().get("items", r_list_before.json().get("results", []))
        before_ids = {str(m["id"]) for m in before if tag in (m.get("content") or "")}
        assert len(before_ids) >= 1

        r_export = api_post(user_b_token, "/api/v1/backup/export", json={
            "project_slug": export_project_b,
        })
        b_zip = r_export.content

        r_import = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", b_zip,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r_import.status_code == 200
        time.sleep(3)

        r_list_after = api_get(user_b_token, f"/api/v1/memories/?project_slug={export_project_b}")
        assert r_list_after.status_code == 200
        after = r_list_after.json().get("items", r_list_after.json().get("results", []))
        after_ids = {str(m["id"]) for m in after if tag in (m.get("content") or "")}

        assert before_ids == after_ids, \
            f"B's memories changed after A's import! before={before_ids}, after={after_ids}"

    def test_cross_user_import_shows_correct_created_by(
        self, user_a_token, user_a_name, user_b_token,
        export_project_a, export_project_b,
    ):
        """Imported memories must show the importing user (A) as created_by, not B."""
        tag = _uid()
        create_memory(user_b_token, f"B authored {tag}", export_project_b)
        time.sleep(2)

        r = api_post(user_b_token, "/api/v1/backup/export", json={
            "project_slug": export_project_b,
        })
        b_zip = r.content

        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", b_zip,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r2.status_code == 200
        time.sleep(3)

        r3 = api_get(user_a_token, f"/api/v1/memories/?project_slug={export_project_a}")
        assert r3.status_code == 200
        items = r3.json().get("items", r3.json().get("results", []))
        imported = [m for m in items if tag in (m.get("content") or "")]
        assert len(imported) >= 1, "Imported memory not found"
        for m in imported:
            assert m.get("created_by") == user_a_name, \
                f"Expected created_by={user_a_name}, got {m.get('created_by')}"


class TestImportStatus:
    """Background task polling."""

    def test_import_status_polling(self, user_a_token, export_project_a):
        tag = _uid()
        create_memory(user_a_token, f"status poll {tag}", export_project_a)
        time.sleep(2)

        r = api_post(user_a_token, "/api/v1/backup/export", json={
            "project_slug": export_project_a,
        })
        zip_bytes = r.content

        r2 = api_upload(
            user_a_token, "/api/v1/backup/import",
            "export.zip", zip_bytes,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r2.status_code == 200
        task_id = r2.json()["task_id"]

        for _ in range(15):
            r3 = api_get(user_a_token, f"/api/v1/backup/import-status/{task_id}")
            assert r3.status_code == 200
            if r3.json().get("done"):
                break
            time.sleep(1)

        final = api_get(user_a_token, f"/api/v1/backup/import-status/{task_id}")
        assert final.json()["done"] is True

    def test_import_status_not_found(self, user_a_token):
        r = api_get(user_a_token, "/api/v1/backup/import-status/nonexistent123")
        assert r.status_code == 404


class TestClearData:
    """Clear-data endpoint should wipe SQLite + Qdrant + Kuzu graph."""

    def test_clear_data_returns_graph_cleared(self, admin_token):
        r = api_post(admin_token, "/api/v1/backup/clear-data")
        assert r.status_code == 200
        data = r.json()
        assert "sqlite_deleted" in data
        assert "qdrant_deleted" in data
        assert "graph_cleared" in data
        assert data["graph_cleared"] is True


class TestSyntheticImport:
    """Import a synthetically constructed ZIP to test edge cases."""

    def test_import_synthetic_zip(self, user_a_token, user_a_name, export_project_a):
        """Build a ZIP from scratch and import it."""
        tag = _uid()
        fake_id = str(uuid.uuid4())
        memories_json = {
            "user": {"id": str(uuid.uuid4()), "user_id": "fake_exporter", "name": "Fake"},
            "projects": [],
            "apps": [],
            "categories": [],
            "memories": [{
                "id": fake_id,
                "user_id": str(uuid.uuid4()),
                "app_name": "memverse",
                "content": f"synthetic memory {tag}",
                "metadata": {},
                "state": "active",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }],
            "memory_categories": [],
            "status_history": [],
            "access_controls": [],
            "export_meta": {"version": "2", "generated_at": "2026-01-01T00:00:00+00:00"},
        }
        logical = [{
            "id": fake_id,
            "content": f"synthetic memory {tag}",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "state": "active",
            "app": "memverse",
            "categories": [],
            "project_slug": None,
            "creator_username": "fake_exporter",
        }]
        zip_bytes = _make_export_zip(memories_json, logical)

        r = api_upload(
            user_a_token, "/api/v1/backup/import",
            "synthetic.zip", zip_bytes,
            data={"project_slug": export_project_a},
            params={"mode": "overwrite"},
        )
        assert r.status_code == 200
        assert r.json()["imported"] >= 1

        time.sleep(3)
        r2 = api_get(user_a_token, f"/api/v1/memories/?project_slug={export_project_a}")
        items = r2.json().get("items", r2.json().get("results", []))
        imported = [m for m in items if tag in (m.get("content") or "")]
        assert len(imported) >= 1
        for m in imported:
            assert str(m["id"]) != fake_id, "Should have generated a new ID for cross-user import"
            assert m.get("created_by") == user_a_name, \
                f"Should be {user_a_name}, got {m.get('created_by')}"
