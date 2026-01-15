import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import database as db


@pytest.fixture
def temp_db(tmp_path):
    """Use a temporary database for tests."""
    db_path = tmp_path / "test.db"
    with patch.object(db, "get_db_path", return_value=db_path):
        db.init_db()
        yield db_path


class TestDatabase:
    def test_init_db_creates_tables(self, temp_db):
        """init_db should create the uploads table."""
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='uploads'"
            )
            assert cursor.fetchone() is not None

    def test_create_upload(self, temp_db):
        """create_upload should insert a new record."""
        upload = db.create_upload(
            upload_id="test-123",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        assert upload["id"] == "test-123"
        assert upload["filename"] == "test.json"
        assert upload["file_size"] == 1024
        assert upload["file_format"] == "json_array"
        assert upload["status"] == "pending"

    def test_get_upload(self, temp_db):
        """get_upload should retrieve an existing record."""
        db.create_upload(
            upload_id="test-456",
            filename="data.csv",
            file_size=2048,
            file_format="csv",
        )

        upload = db.get_upload("test-456")
        assert upload is not None
        assert upload["filename"] == "data.csv"

    def test_get_upload_not_found(self, temp_db):
        """get_upload should return None for non-existent records."""
        upload = db.get_upload("non-existent")
        assert upload is None

    def test_update_upload(self, temp_db):
        """update_upload should modify existing fields."""
        db.create_upload(
            upload_id="test-789",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        updated = db.update_upload("test-789", status="in_progress", index_name="test-index")

        assert updated["status"] == "in_progress"
        assert updated["index_name"] == "test-index"

    def test_start_ingestion(self, temp_db):
        """start_ingestion should update all ingestion fields."""
        db.create_upload(
            upload_id="test-ingest",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        updated = db.start_ingestion(
            upload_id="test-ingest",
            index_name="shipit-myindex",
            timestamp_field="@timestamp",
            field_mappings={"old": "new"},
            excluded_fields=["ignore"],
            total_records=100,
        )

        assert updated["status"] == "in_progress"
        assert updated["index_name"] == "shipit-myindex"
        assert updated["timestamp_field"] == "@timestamp"
        assert updated["field_mappings"] == {"old": "new"}
        assert updated["excluded_fields"] == ["ignore"]
        assert updated["total_records"] == 100
        assert updated["started_at"] is not None

    def test_update_progress(self, temp_db):
        """update_progress should update counts."""
        db.create_upload(
            upload_id="test-progress",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        db.update_progress("test-progress", success_count=50, failure_count=2)

        upload = db.get_upload("test-progress")
        assert upload["success_count"] == 50
        assert upload["failure_count"] == 2

    def test_complete_ingestion_success(self, temp_db):
        """complete_ingestion should mark as completed."""
        db.create_upload(
            upload_id="test-complete",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        updated = db.complete_ingestion(
            upload_id="test-complete",
            success_count=98,
            failure_count=2,
        )

        assert updated["status"] == "completed"
        assert updated["success_count"] == 98
        assert updated["failure_count"] == 2
        assert updated["completed_at"] is not None
        assert updated["error_message"] is None

    def test_complete_ingestion_failure(self, temp_db):
        """complete_ingestion with error should mark as failed."""
        db.create_upload(
            upload_id="test-failed",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        updated = db.complete_ingestion(
            upload_id="test-failed",
            success_count=10,
            failure_count=90,
            error_message="Connection refused",
        )

        assert updated["status"] == "failed"
        assert updated["error_message"] == "Connection refused"

    def test_list_uploads(self, temp_db):
        """list_uploads should return recent uploads."""
        for i in range(5):
            db.create_upload(
                upload_id=f"list-test-{i}",
                filename=f"file{i}.json",
                file_size=1024,
                file_format="json_array",
            )

        uploads = db.list_uploads(limit=3)
        assert len(uploads) == 3

    def test_list_uploads_filter_by_status(self, temp_db):
        """list_uploads should filter by status."""
        db.create_upload(
            upload_id="pending-1",
            filename="pending.json",
            file_size=1024,
            file_format="json_array",
        )

        db.create_upload(
            upload_id="completed-1",
            filename="completed.json",
            file_size=1024,
            file_format="json_array",
        )
        db.complete_ingestion("completed-1", success_count=100, failure_count=0)

        pending = db.list_uploads(status="pending")
        completed = db.list_uploads(status="completed")

        assert len(pending) == 1
        assert pending[0]["id"] == "pending-1"
        assert len(completed) == 1
        assert completed[0]["id"] == "completed-1"

    def test_create_upload_with_user_id(self, temp_db):
        """create_upload should store user_id when provided."""
        # Create a test user first
        user = db.create_user(
            email="uploader@example.com",
            name="Uploader",
            auth_type="local",
        )

        upload = db.create_upload(
            upload_id="user-upload-1",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
            user_id=user["id"],
        )

        assert upload["id"] == "user-upload-1"
        assert upload["user_id"] == user["id"]

    def test_create_upload_without_user_id(self, temp_db):
        """create_upload should allow None user_id for backward compatibility."""
        upload = db.create_upload(
            upload_id="no-user-upload",
            filename="test.json",
            file_size=1024,
            file_format="json_array",
        )

        assert upload["id"] == "no-user-upload"
        assert upload["user_id"] is None
