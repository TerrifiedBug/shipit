"""Tests for SQL injection prevention in database operations."""
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


class TestSqlInjectionPrevention:
    """Tests for column allowlist validation to prevent SQL injection."""

    def test_update_upload_rejects_invalid_column(self, temp_db):
        """update_upload should reject columns not in allowlist."""
        # Create a test upload first
        upload = db.create_upload(
            upload_id="test-security-1",
            filenames=["test.json"],
            file_sizes=[100],
            file_format="json_array",
        )

        with pytest.raises(ValueError, match="Invalid column"):
            db.update_upload(upload["id"], malicious_column="DROP TABLE users")

    def test_update_upload_accepts_valid_columns(self, temp_db):
        """update_upload should accept valid columns."""
        upload = db.create_upload(
            upload_id="test-security-2",
            filenames=["test.json"],
            file_sizes=[100],
            file_format="json_array",
        )

        result = db.update_upload(
            upload["id"], status="processing", index_name="test-index"
        )
        assert result["status"] == "processing"
        assert result["index_name"] == "test-index"

    def test_update_upload_rejects_sql_injection_in_column_name(self, temp_db):
        """update_upload should reject SQL injection attempts via column names."""
        upload = db.create_upload(
            upload_id="test-security-3",
            filenames=["test.json"],
            file_sizes=[100],
            file_format="json_array",
        )

        # Attempt SQL injection via column name
        with pytest.raises(ValueError, match="Invalid column"):
            db.update_upload(upload["id"], **{"status = 'hacked' --": "value"})

    def test_update_user_rejects_invalid_column(self, temp_db):
        """update_user should reject columns not in allowlist."""
        user = db.create_user(
            email="test@example.com",
            name="Test User",
            auth_type="local",
        )

        with pytest.raises(ValueError, match="Invalid column"):
            db.update_user(user["id"], malicious_column="DROP TABLE users")

    def test_update_user_accepts_valid_columns(self, temp_db):
        """update_user should accept valid columns."""
        user = db.create_user(
            email="test2@example.com",
            name="Test User",
            auth_type="local",
        )

        result = db.update_user(user["id"], name="Updated Name", is_admin=1)
        assert result["name"] == "Updated Name"
        assert result["is_admin"] == 1

    def test_update_user_rejects_sql_injection_in_column_name(self, temp_db):
        """update_user should reject SQL injection attempts via column names."""
        user = db.create_user(
            email="test3@example.com",
            name="Test User",
            auth_type="local",
        )

        # Attempt SQL injection via column name
        with pytest.raises(ValueError, match="Invalid column"):
            db.update_user(user["id"], **{"is_admin = 1 --": "value"})

    def test_update_upload_all_valid_columns_accepted(self, temp_db):
        """update_upload should accept all columns in the allowlist."""
        upload = db.create_upload(
            upload_id="test-security-4",
            filenames=["test.json"],
            file_sizes=[100],
            file_format="json_array",
        )

        # Test several valid columns
        result = db.update_upload(
            upload["id"],
            status="in_progress",
            error_message="Test error",
            total_records=100,
            success_count=50,
            failure_count=10,
        )
        assert result["status"] == "in_progress"
        assert result["error_message"] == "Test error"
        assert result["total_records"] == 100
        assert result["success_count"] == 50
        assert result["failure_count"] == 10

    def test_update_user_all_valid_columns_accepted(self, temp_db):
        """update_user should accept all columns in the allowlist."""
        user = db.create_user(
            email="test4@example.com",
            name="Test User",
            auth_type="local",
        )

        # Test several valid columns
        result = db.update_user(
            user["id"],
            name="New Name",
            is_active=0,
            password_change_required=1,
        )
        assert result["name"] == "New Name"
        assert result["is_active"] == 0
        assert result["password_change_required"] == 1
