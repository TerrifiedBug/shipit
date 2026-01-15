from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.database import create_user


client = TestClient(app)


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
