# backend/tests/test_ip_trust.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.request_utils import get_client_ip, _is_trusted_proxy


class TestIsTrustedProxy:
    """Tests for _is_trusted_proxy helper function."""

    def test_empty_trusted_proxies_returns_false(self):
        """With no trusted proxies configured, all IPs are untrusted."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = []
            assert _is_trusted_proxy("10.0.0.1") is False
            assert _is_trusted_proxy("192.168.1.1") is False

    def test_ip_in_cidr_range_is_trusted(self):
        """IP within a configured CIDR range is trusted."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            assert _is_trusted_proxy("10.0.0.1") is True
            assert _is_trusted_proxy("10.255.255.255") is True
            assert _is_trusted_proxy("11.0.0.1") is False

    def test_multiple_cidr_ranges(self):
        """Multiple CIDR ranges are all checked."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
            assert _is_trusted_proxy("10.0.0.1") is True
            assert _is_trusted_proxy("172.16.5.10") is True
            assert _is_trusted_proxy("192.168.1.1") is True
            assert _is_trusted_proxy("203.0.113.50") is False

    def test_invalid_ip_returns_false(self):
        """Invalid IP addresses return False."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            assert _is_trusted_proxy("invalid") is False
            assert _is_trusted_proxy("") is False
            assert _is_trusted_proxy("unknown") is False

    def test_single_ip_in_trusted_proxies(self):
        """Single IP (not CIDR) can be used in trusted_proxies."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.1/32"]
            assert _is_trusted_proxy("10.0.0.1") is True
            assert _is_trusted_proxy("10.0.0.2") is False


class TestClientIpExtraction:
    """Tests for get_client_ip function."""

    def test_direct_connection_uses_client_host(self):
        """Without trusted proxies, use direct client IP."""
        request = MagicMock()
        request.client.host = "203.0.113.50"
        request.headers = {"X-Forwarded-For": "10.0.0.1"}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = []
            ip = get_client_ip(request)
            assert ip == "203.0.113.50"

    def test_trusted_proxy_uses_forwarded_header(self):
        """With trusted proxy, use X-Forwarded-For."""
        request = MagicMock()
        request.client.host = "10.0.0.1"  # Proxy IP
        request.headers = {"X-Forwarded-For": "203.0.113.50, 10.0.0.2"}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            ip = get_client_ip(request)
            assert ip == "203.0.113.50"  # First IP in chain

    def test_untrusted_proxy_ignores_header(self):
        """Untrusted proxy's X-Forwarded-For should be ignored."""
        request = MagicMock()
        request.client.host = "203.0.113.100"  # Not in trusted range
        request.headers = {"X-Forwarded-For": "10.0.0.1"}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["192.168.0.0/16"]
            ip = get_client_ip(request)
            assert ip == "203.0.113.100"

    def test_trusted_proxy_no_forwarded_header(self):
        """Trusted proxy but no X-Forwarded-For header returns direct IP."""
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            ip = get_client_ip(request)
            assert ip == "10.0.0.1"

    def test_trusted_proxy_empty_forwarded_header(self):
        """Trusted proxy with empty X-Forwarded-For returns direct IP."""
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": ""}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            ip = get_client_ip(request)
            assert ip == "10.0.0.1"

    def test_none_request_returns_unknown(self):
        """None request returns 'unknown'."""
        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = []
            ip = get_client_ip(None)
            assert ip == "unknown"

    def test_no_client_returns_unknown(self):
        """Request with no client attribute returns 'unknown'."""
        request = MagicMock()
        request.client = None
        request.headers = {}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = []
            ip = get_client_ip(request)
            assert ip == "unknown"

    def test_multiple_ips_in_chain_uses_first(self):
        """Multiple IPs in X-Forwarded-For uses the first (original client)."""
        request = MagicMock()
        request.client.host = "10.0.0.5"  # Final proxy
        request.headers = {"X-Forwarded-For": "203.0.113.50, 10.0.0.1, 10.0.0.2, 10.0.0.3"}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            ip = get_client_ip(request)
            assert ip == "203.0.113.50"  # Original client IP

    def test_whitespace_handling_in_forwarded_header(self):
        """Whitespace around IPs in X-Forwarded-For is stripped."""
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "  203.0.113.50  , 10.0.0.2 "}

        with patch('app.services.request_utils.settings') as mock_settings:
            mock_settings.trusted_proxies = ["10.0.0.0/8"]
            ip = get_client_ip(request)
            assert ip == "203.0.113.50"
