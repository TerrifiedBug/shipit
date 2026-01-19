"""Tests for health endpoint."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_includes_cluster_info(self):
        """Health endpoint should include cluster name and version when connected."""
        with patch("app.routers.health.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.info.return_value = {
                "cluster_name": "test-cluster",
                "version": {"number": "2.11.0"}
            }
            mock_get_client.return_value = mock_client

            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["opensearch"]["connected"] is True
            assert data["opensearch"]["cluster_name"] == "test-cluster"
            assert data["opensearch"]["version"] == "2.11.0"

    def test_health_disconnected_no_cluster_info(self):
        """When disconnected, cluster info should be null."""
        with patch("app.routers.health.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.ping.return_value = False
            mock_get_client.return_value = mock_client

            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["opensearch"]["connected"] is False
            assert data["opensearch"]["cluster_name"] is None
            assert data["opensearch"]["version"] is None

    def test_health_exception_shows_disconnected(self):
        """When an exception occurs, show as disconnected with null cluster info."""
        with patch("app.routers.health.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.ping.side_effect = Exception("Connection refused")
            mock_get_client.return_value = mock_client

            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["opensearch"]["connected"] is False
            assert data["opensearch"]["cluster_name"] is None
            assert data["opensearch"]["version"] is None

    def test_health_partial_info_response(self):
        """Handle partial info response from OpenSearch."""
        with patch("app.routers.health.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            # Missing version info
            mock_client.info.return_value = {
                "cluster_name": "partial-cluster"
            }
            mock_get_client.return_value = mock_client

            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["opensearch"]["connected"] is True
            assert data["opensearch"]["cluster_name"] == "partial-cluster"
            assert data["opensearch"]["version"] is None
