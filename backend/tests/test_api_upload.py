"""Tests for single-shot API upload endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.database import create_user, create_api_key
from app.services.auth import hash_password, generate_api_key


client = TestClient(app)


class TestApiUpload:
    """Tests for /api/v1/upload endpoint."""

    def _create_user_with_api_key(self, db):
        """Helper to create a user and API key."""
        user = create_user("apitest@example.com", "API User", "local", hash_password("password123"), is_admin=False)
        raw_key, key_hash = generate_api_key()
        create_api_key(user["id"], "test-key", key_hash, expires_in_days=30)
        return raw_key

    def test_api_upload_requires_auth(self, db):
        """Test that API upload requires authentication."""
        response = client.post(
            "/api/v1/upload",
            files={"file": ("test.json", b'[{"name":"Alice"}]', "application/json")},
            data={"index_name": "test-index"}
        )
        assert response.status_code == 401

    @patch("app.routers.api_upload.track_index")
    @patch("app.routers.api_upload.validate_index_for_ingestion")
    @patch("app.routers.api_upload.ingest_file")
    @patch("app.routers.api_upload.detect_format")
    def test_api_upload_success(self, mock_detect, mock_ingest, mock_validate, mock_track, db, temp_dir):
        """Test successful API upload."""
        api_key = self._create_user_with_api_key(db)

        # Mock successful validation and ingestion
        mock_validate.return_value = {"exists": False, "tracked": False, "requires_tracking": True}
        mock_detect.return_value = "json_array"

        mock_result = MagicMock()
        mock_result.processed = 1
        mock_result.success = 1
        mock_result.failed = 0
        mock_result.failed_records = []
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.json", b'[{"name":"Alice"}]', "application/json")},
            data={"index_name": "test-index"}
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        result = response.json()
        assert result["status"] == "completed"
        assert result["index_name"] == "shipit-test-index"
        assert result["records_ingested"] == 1
        assert result["records_failed"] == 0

    @patch("app.routers.api_upload.track_index")
    @patch("app.routers.api_upload.validate_index_for_ingestion")
    @patch("app.routers.api_upload.ingest_file")
    @patch("app.routers.api_upload.detect_format")
    @patch("app.routers.api_upload.parse_preview")
    def test_api_upload_with_timestamp_field(self, mock_preview, mock_detect, mock_ingest, mock_validate, mock_track, db, temp_dir):
        """Test API upload with timestamp field specified."""
        api_key = self._create_user_with_api_key(db)

        mock_validate.return_value = {"exists": False, "tracked": False, "requires_tracking": True}
        mock_detect.return_value = "json_array"
        mock_preview.return_value = [{"name": "Alice", "time": "2024-01-01T00:00:00Z"}]

        mock_result = MagicMock()
        mock_result.processed = 1
        mock_result.success = 1
        mock_result.failed = 0
        mock_result.failed_records = []
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.json", b'[{"name":"Alice","time":"2024-01-01T00:00:00Z"}]', "application/json")},
            data={
                "index_name": "test-index",
                "timestamp_field": "time"
            }
        )

        assert response.status_code == 200
        # Verify ingest_file was called with timestamp_field
        call_args = mock_ingest.call_args
        assert call_args.kwargs.get("timestamp_field") == "time"

    @patch("app.routers.api_upload.validate_index_for_ingestion")
    @patch("app.routers.api_upload.detect_format")
    @patch("app.routers.api_upload.parse_preview")
    def test_api_upload_invalid_timestamp_field(self, mock_preview, mock_detect, mock_validate, db, temp_dir):
        """Test API upload with non-existent timestamp field."""
        api_key = self._create_user_with_api_key(db)

        mock_validate.return_value = {"exists": False, "tracked": False, "requires_tracking": True}
        mock_detect.return_value = "json_array"
        mock_preview.return_value = [{"name": "Alice"}]  # No 'nonexistent' field

        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.json", b'[{"name":"Alice"}]', "application/json")},
            data={
                "index_name": "test-index",
                "timestamp_field": "nonexistent"
            }
        )

        assert response.status_code == 400
        result = response.json()
        # Response is {"detail": {"detail": "...", "available_fields": [...]}}
        assert "timestamp" in result["detail"]["detail"].lower()
        assert "available_fields" in result["detail"]

    @patch("app.routers.api_upload.validate_index_for_ingestion")
    def test_api_upload_blocked_by_strict_mode(self, mock_validate, db):
        """Test API upload blocked by strict index mode."""
        api_key = self._create_user_with_api_key(db)

        mock_validate.side_effect = ValueError("Index exists but was not created by ShipIt")

        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.json", b'[{"name":"Alice"}]', "application/json")},
            data={"index_name": "test-index"}
        )

        assert response.status_code == 400
        assert "not created by ShipIt" in response.json()["detail"]

    @patch("app.routers.api_upload.track_index")
    @patch("app.routers.api_upload.validate_index_for_ingestion")
    @patch("app.routers.api_upload.ingest_file")
    def test_api_upload_with_format_override(self, mock_ingest, mock_validate, mock_track, db, temp_dir):
        """Test API upload with explicit format override."""
        api_key = self._create_user_with_api_key(db)

        mock_validate.return_value = {"exists": False, "tracked": False, "requires_tracking": True}

        mock_result = MagicMock()
        mock_result.processed = 2
        mock_result.success = 2
        mock_result.failed = 0
        mock_result.failed_records = []
        mock_ingest.return_value = mock_result

        # Send file with .txt extension but specify ndjson format
        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("data.txt", b'{"name":"Alice"}\n{"name":"Bob"}', "text/plain")},
            data={
                "index_name": "test-index",
                "format": "ndjson"
            }
        )

        assert response.status_code == 200
        # Verify ingest_file was called with ndjson format
        call_args = mock_ingest.call_args
        assert call_args.kwargs.get("file_format") == "ndjson"

    @patch("app.routers.api_upload.track_index")
    @patch("app.routers.api_upload.validate_index_for_ingestion")
    @patch("app.routers.api_upload.ingest_file")
    @patch("app.routers.api_upload.detect_format")
    def test_api_upload_with_errors(self, mock_detect, mock_ingest, mock_validate, mock_track, db, temp_dir):
        """Test API upload with some failed records."""
        api_key = self._create_user_with_api_key(db)

        mock_validate.return_value = {"exists": False, "tracked": False, "requires_tracking": True}
        mock_detect.return_value = "json_array"

        mock_result = MagicMock()
        mock_result.processed = 10
        mock_result.success = 8
        mock_result.failed = 2
        mock_result.failed_records = [
            {"record": {"name": "bad1"}, "error": "mapping error"},
            {"record": {"name": "bad2"}, "error": "mapping error"},
        ]
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.json", b'[{"name":"Alice"}]', "application/json")},
            data={"index_name": "test-index"}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "completed_with_errors"
        assert result["records_ingested"] == 8
        assert result["records_failed"] == 2
        assert "errors" in result
        assert len(result["errors"]) == 2
