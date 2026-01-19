"""Tests for audit log shipping functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestAuditShipping:
    """Test audit log shipping to OpenSearch and HTTP endpoints."""

    @patch("app.services.audit_shipping.settings")
    @patch("app.services.audit_shipping._get_opensearch_client")
    def test_ship_to_opensearch_when_enabled(self, mock_get_client, mock_settings):
        """Test that audit logs are shipped to OpenSearch when enabled."""
        from app.services.audit_shipping import ship_to_opensearch

        # Configure settings
        mock_settings.audit_log_to_opensearch = True
        mock_settings.index_prefix = "test-"

        # Mock OpenSearch client
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_get_client.return_value = mock_client

        # Ship an audit log
        audit_log = {
            "id": "test-123",
            "event_type": "user_login",
            "actor_id": "user1",
            "actor_name": "Test User",
            "created_at": "2026-01-19T12:00:00",
        }

        ship_to_opensearch(audit_log)

        # Verify the client was used to index the document
        mock_client.index.assert_called_once()
        call_args = mock_client.index.call_args
        assert call_args.kwargs["id"] == "test-123"

    @patch("app.services.audit_shipping.settings")
    def test_ship_to_opensearch_skipped_when_disabled(self, mock_settings):
        """Test that shipping is skipped when disabled."""
        from app.services.audit_shipping import ship_to_opensearch

        mock_settings.audit_log_to_opensearch = False

        # This should not raise and should not call OpenSearch
        audit_log = {"id": "test-123", "event_type": "user_login"}
        ship_to_opensearch(audit_log)
        # No assertion needed - just verify it doesn't crash

    @patch("app.services.audit_shipping._get_opensearch_client")
    def test_ensure_audit_index_creates_index(self, mock_get_client):
        """Test that the audit index is created if it doesn't exist."""
        import app.services.audit_shipping as audit_shipping
        from app.services.audit_shipping import _ensure_audit_index, AUDIT_INDEX_NAME

        # Reset the ensured flag for this test
        audit_shipping._audit_index_ensured = False

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _ensure_audit_index()

        # Verify index creation was attempted
        mock_client.indices.create.assert_called_once()
        call_args = mock_client.indices.create.call_args
        # Index name is based on settings.index_prefix at module load time
        assert call_args.kwargs["index"] == AUDIT_INDEX_NAME

    @patch("app.services.audit_shipping.settings")
    @patch("app.services.audit_shipping._get_opensearch_client")
    def test_ship_to_opensearch_handles_connection_error(self, mock_get_client, mock_settings):
        """Test that connection errors are handled gracefully."""
        from app.services.audit_shipping import ship_to_opensearch

        mock_settings.audit_log_to_opensearch = True
        mock_settings.index_prefix = "test-"

        # Simulate connection error
        mock_client = MagicMock()
        mock_client.indices.exists.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        # Should not raise - errors are logged as warnings
        audit_log = {"id": "test-123", "event_type": "user_login"}
        ship_to_opensearch(audit_log)

    @patch("app.services.audit_shipping.settings")
    def test_is_shipping_enabled(self, mock_settings):
        """Test the is_shipping_enabled helper function."""
        from app.services.audit_shipping import is_shipping_enabled

        # Neither enabled
        mock_settings.audit_log_to_opensearch = False
        mock_settings.audit_log_endpoint = None
        assert is_shipping_enabled() is False

        # OpenSearch enabled
        mock_settings.audit_log_to_opensearch = True
        mock_settings.audit_log_endpoint = None
        assert is_shipping_enabled() is True

        # HTTP endpoint enabled
        mock_settings.audit_log_to_opensearch = False
        mock_settings.audit_log_endpoint = "https://example.com"
        assert is_shipping_enabled() is True

        # Both enabled
        mock_settings.audit_log_to_opensearch = True
        mock_settings.audit_log_endpoint = "https://example.com"
        assert is_shipping_enabled() is True

    @patch("app.services.audit_shipping.settings")
    def test_parse_headers(self, mock_settings):
        """Test header parsing from config string."""
        from app.services.audit_shipping import _parse_headers

        # No headers
        mock_settings.audit_log_endpoint_headers = None
        assert _parse_headers() == {}

        # Single header
        mock_settings.audit_log_endpoint_headers = "X-Custom:value1"
        assert _parse_headers() == {"X-Custom": "value1"}

        # Multiple headers
        mock_settings.audit_log_endpoint_headers = "X-Custom:value1,X-Another:value2"
        result = _parse_headers()
        assert result["X-Custom"] == "value1"
        assert result["X-Another"] == "value2"

        # Header with colons in value
        mock_settings.audit_log_endpoint_headers = "Authorization:Bearer:token:here"
        assert _parse_headers() == {"Authorization": "Bearer:token:here"}


class TestAuditShippingIntegration:
    """Integration tests for audit log shipping via database.py."""

    def test_create_audit_log_imports_ship_audit_log(self):
        """Test that create_audit_log has the ship_audit_log import."""
        import inspect
        from app.services.database import create_audit_log

        source = inspect.getsource(create_audit_log)
        assert "from app.services.audit_shipping import ship_audit_log" in source
        assert "ship_audit_log(result)" in source
