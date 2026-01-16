from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.database import create_user


client = TestClient(app)


class TestIndexProtection:
    """Tests for index protection validation."""

    def test_new_index_allowed(self, db):
        """Test that new indices (not existing in OpenSearch) are allowed."""
        from app.services.opensearch import validate_index_for_ingestion

        with patch("app.services.opensearch.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = False
            mock_get_client.return_value = mock_client

            result = validate_index_for_ingestion("shipit-new-index")

            assert result["exists"] is False
            assert result["tracked"] is False
            assert result["requires_tracking"] is True

    def test_tracked_index_allowed(self, db):
        """Test that tracked indices are always allowed."""
        from app.services.opensearch import validate_index_for_ingestion
        from app.services.database import track_index

        # Track the index first
        track_index("shipit-tracked", user_id="user123")

        with patch("app.services.opensearch.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            mock_get_client.return_value = mock_client

            result = validate_index_for_ingestion("shipit-tracked")

            assert result["exists"] is True
            assert result["tracked"] is True
            assert result["requires_tracking"] is False

    def test_external_index_blocked_in_strict_mode(self, db):
        """Test that external indices are blocked in strict mode."""
        from app.services.opensearch import validate_index_for_ingestion

        with patch("app.services.opensearch.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            mock_get_client.return_value = mock_client

            # Default is strict_index_mode=True
            with pytest.raises(ValueError, match="not created by ShipIt"):
                validate_index_for_ingestion("shipit-external")

    def test_external_index_allowed_when_not_strict(self, db):
        """Test that external indices are allowed when strict mode is off."""
        from app.services.opensearch import validate_index_for_ingestion

        with patch("app.services.opensearch.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            mock_get_client.return_value = mock_client

            with patch("app.services.opensearch.settings") as mock_settings:
                mock_settings.strict_index_mode = False

                result = validate_index_for_ingestion("shipit-external")

                assert result["exists"] is True
                assert result["tracked"] is False
                assert result["requires_tracking"] is True


class TestDeleteIndexEndpoint:
    def _login(self, db):
        """Helper to setup and login, returns cookies."""
        client.post("/api/auth/setup", json={
            "email": "indextest@example.com",
            "password": "password",
            "name": "Index Test User",
        })
        response = client.post("/api/auth/login", json={
            "email": "indextest@example.com",
            "password": "password",
        })
        return response.cookies

    def test_delete_index_success(self, db):
        """Test successful index deletion."""
        cookies = self._login(db)

        with patch("app.routers.indexes.delete_index") as mock_delete:
            mock_delete.return_value = True

            response = client.delete("/api/indexes/shipit-test-index", cookies=cookies)

            assert response.status_code == 200
            assert response.json()["message"] == "Index shipit-test-index deleted"
            mock_delete.assert_called_once_with("shipit-test-index")

    def test_delete_index_not_found(self, db):
        """Test deleting non-existent index returns 404."""
        cookies = self._login(db)

        with patch("app.routers.indexes.delete_index") as mock_delete:
            mock_delete.return_value = False

            response = client.delete("/api/indexes/shipit-nonexistent", cookies=cookies)

            assert response.status_code == 404
            assert response.json()["detail"] == "Index not found"

    def test_delete_index_without_prefix(self, db):
        """Test deleting index without required prefix returns 400."""
        cookies = self._login(db)

        response = client.delete("/api/indexes/not-shipit-index", cookies=cookies)

        assert response.status_code == 400
        assert "prefix" in response.json()["detail"].lower()

    def test_delete_index_requires_auth(self, db):
        """Test that delete endpoint requires authentication."""
        response = client.delete("/api/indexes/shipit-test-index")

        assert response.status_code == 401

    def test_delete_index_creates_audit_log(self, db):
        """Test that successful deletion creates an audit log entry."""
        cookies = self._login(db)

        with patch("app.routers.indexes.delete_index") as mock_delete:
            mock_delete.return_value = True

            response = client.delete("/api/indexes/shipit-audit-test", cookies=cookies)

            assert response.status_code == 200

        # Verify audit log was created
        from app.services.database import list_audit_logs
        logs = list_audit_logs(action="delete_index")
        assert len(logs) >= 1
        assert any(log["target"] == "shipit-audit-test" for log in logs)

    def test_delete_index_untracks_index(self, db):
        """Test that deleting an index removes it from tracking."""
        from app.services.database import track_index, is_index_tracked

        cookies = self._login(db)

        # Track the index first
        track_index("shipit-tracked-delete", user_id="user123")
        assert is_index_tracked("shipit-tracked-delete") is True

        with patch("app.routers.indexes.delete_index") as mock_delete:
            mock_delete.return_value = True

            response = client.delete("/api/indexes/shipit-tracked-delete", cookies=cookies)

            assert response.status_code == 200

        # Verify index is no longer tracked
        assert is_index_tracked("shipit-tracked-delete") is False
