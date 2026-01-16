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
            filenames=["test.json"],
            file_sizes=[1024],
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
            filenames=["data.csv"],
            file_sizes=[2048],
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
            filenames=["test.json"],
            file_sizes=[1024],
            file_format="json_array",
        )

        updated = db.update_upload("test-789", status="in_progress", index_name="test-index")

        assert updated["status"] == "in_progress"
        assert updated["index_name"] == "test-index"

    def test_start_ingestion(self, temp_db):
        """start_ingestion should update all ingestion fields."""
        db.create_upload(
            upload_id="test-ingest",
            filenames=["test.json"],
            file_sizes=[1024],
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
            filenames=["test.json"],
            file_sizes=[1024],
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
            filenames=["test.json"],
            file_sizes=[1024],
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
            filenames=["test.json"],
            file_sizes=[1024],
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
                filenames=[f"file{i}.json"],
                file_sizes=[1024],
                file_format="json_array",
            )

        uploads = db.list_uploads(limit=3)
        assert len(uploads) == 3

    def test_list_uploads_filter_by_status(self, temp_db):
        """list_uploads should filter by status."""
        db.create_upload(
            upload_id="pending-1",
            filenames=["pending.json"],
            file_sizes=[1024],
            file_format="json_array",
        )

        db.create_upload(
            upload_id="completed-1",
            filenames=["completed.json"],
            file_sizes=[1024],
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
            filenames=["test.json"],
            file_sizes=[1024],
            file_format="json_array",
            user_id=user["id"],
        )

        assert upload["id"] == "user-upload-1"
        assert upload["user_id"] == user["id"]

    def test_create_upload_without_user_id(self, temp_db):
        """create_upload should allow None user_id for backward compatibility."""
        upload = db.create_upload(
            upload_id="no-user-upload",
            filenames=["test.json"],
            file_sizes=[1024],
            file_format="json_array",
        )

        assert upload["id"] == "no-user-upload"
        assert upload["user_id"] is None

    def test_deactivate_user(self, temp_db):
        """Test deactivating a user."""
        from app.services.database import create_user, deactivate_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("test@example.com", "Test User", "local", hash_password("password123"), is_admin=False)
        user_id = user["id"]

        deactivate_user(user_id)

        user = get_user_by_email("test@example.com")
        assert user["is_active"] == 0  # SQLite returns 0/1 for boolean

    def test_reactivate_user(self, temp_db):
        """Test reactivating a deactivated user."""
        from app.services.database import create_user, deactivate_user, reactivate_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("test@example.com", "Test User", "local", hash_password("password123"), is_admin=False)
        user_id = user["id"]

        deactivate_user(user_id)
        reactivate_user(user_id)

        user = get_user_by_email("test@example.com")
        assert user["is_active"] == 1

    def test_deactivate_nonexistent_user(self, temp_db):
        """Deactivating non-existent user should not raise error."""
        from app.services.database import deactivate_user
        # Should not raise exception
        deactivate_user("nonexistent-id")

    def test_deactivate_already_deactivated(self, temp_db):
        """Deactivating an already deactivated user should be idempotent."""
        from app.services.database import create_user, deactivate_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("test@example.com", "Test", "local", hash_password("pass"), False)
        deactivate_user(user["id"])
        deactivate_user(user["id"])  # Second deactivation

        user = get_user_by_email("test@example.com")
        assert user["is_active"] == 0

    def test_reactivate_already_active(self, temp_db):
        """Reactivating an already active user should be idempotent."""
        from app.services.database import create_user, reactivate_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("test@example.com", "Test", "local", hash_password("pass"), False)
        reactivate_user(user["id"])  # Already active

        user = get_user_by_email("test@example.com")
        assert user["is_active"] == 1

    def test_soft_delete_user(self, temp_db):
        """Test soft deleting a user."""
        from app.services.database import create_user, delete_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("delete@example.com", "Delete User", "local", hash_password("password123"), is_admin=False)
        user_id = user["id"]

        delete_user(user_id)

        # User should still exist but be marked as deleted
        user = get_user_by_email("delete@example.com", include_deleted=True)
        assert user is not None
        assert user["deleted_at"] is not None

    def test_deleted_user_not_returned_by_default(self, temp_db):
        """Test that deleted users are not returned by default."""
        from app.services.database import create_user, delete_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("delete@example.com", "Delete User", "local", hash_password("password123"), is_admin=False)
        delete_user(user["id"])

        # Default should not return deleted user
        user = get_user_by_email("delete@example.com")
        assert user is None

    def test_reregister_deleted_user(self, temp_db):
        """Test that deleted user can re-register with same email."""
        from app.services.database import create_user, delete_user, get_user_by_email
        from app.services.auth import hash_password

        user = create_user("rereg@example.com", "First", "local", hash_password("password123"), is_admin=False)
        original_id = user["id"]
        delete_user(original_id)

        # Re-register with same email - should reactivate
        new_user = create_user("rereg@example.com", "Second", "local", hash_password("newpass456"), is_admin=False)

        # Should be the same user ID (reactivated)
        assert new_user["id"] == original_id
        # Updated name
        assert new_user["name"] == "Second"
        # No longer deleted
        assert new_user["deleted_at"] is None
        # Should be active
        assert new_user["is_active"] == 1


class TestIndexTracking:
    def test_track_index(self, temp_db):
        """Test tracking a ShipIt-created index."""
        from app.services.database import track_index, is_index_tracked

        track_index("shipit-test", user_id="user123")

        is_tracked = is_index_tracked("shipit-test")
        assert is_tracked == True

    def test_untrack_index(self, temp_db):
        """Test untracking an index after deletion."""
        from app.services.database import track_index, untrack_index, is_index_tracked

        track_index("shipit-test", user_id="user123")
        untrack_index("shipit-test")

        is_tracked = is_index_tracked("shipit-test")
        assert is_tracked == False

    def test_index_not_tracked(self, temp_db):
        """Test checking if an index is not tracked."""
        from app.services.database import is_index_tracked

        is_tracked = is_index_tracked("external-index")
        assert is_tracked == False

    def test_track_index_idempotent(self, temp_db):
        """Tracking the same index twice should be idempotent."""
        from app.services.database import track_index, is_index_tracked

        track_index("shipit-test", user_id="user123")
        track_index("shipit-test", user_id="user456")  # Second track with different user

        is_tracked = is_index_tracked("shipit-test")
        assert is_tracked == True

    def test_untrack_nonexistent_index(self, temp_db):
        """Untracking a non-existent index should not raise error."""
        from app.services.database import untrack_index

        # Should not raise exception
        untrack_index("nonexistent-index")
