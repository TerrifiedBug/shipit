# backend/tests/test_geoip.py
import pytest
from unittest.mock import patch, MagicMock


class TestGeoIPEnrichment:
    def test_public_ip_returns_location(self):
        """Public IP should return geographic data."""
        from app.services.geoip import enrich_ip

        # Mock the maxmind reader
        # Note: MagicMock(name=...) sets the mock's name, not an attribute
        # We need to configure the 'name' attribute separately
        mock_country = MagicMock()
        mock_country.name = "United States"
        mock_city = MagicMock()
        mock_city.name = "San Francisco"
        mock_location = MagicMock(latitude=37.7749, longitude=-122.4194)

        with patch('app.services.geoip._reader') as mock_reader:
            mock_reader.city.return_value = MagicMock(
                country=mock_country,
                city=mock_city,
                location=mock_location
            )

            result = enrich_ip("8.8.8.8")

            assert result["country_name"] == "United States"
            assert result["city_name"] == "San Francisco"
            assert result["location"]["lat"] == 37.7749

    def test_private_ip_returns_private(self):
        """Private IP should return 'private' indicator."""
        from app.services.geoip import enrich_ip

        result = enrich_ip("192.168.1.1")
        assert result["country_name"] == "private"

    def test_invalid_ip_returns_none(self):
        """Invalid IP should return None."""
        from app.services.geoip import enrich_ip

        result = enrich_ip("not-an-ip")
        assert result is None

    def test_disabled_when_no_database(self):
        """Should gracefully handle missing database."""
        from app.services.geoip import enrich_ip

        with patch('app.services.geoip._reader', None):
            result = enrich_ip("8.8.8.8")
            assert result is None

    def test_private_ip_10_range(self):
        """10.x.x.x should be detected as private."""
        from app.services.geoip import enrich_ip
        result = enrich_ip("10.0.0.1")
        assert result["country_name"] == "private"

    def test_private_ip_172_range(self):
        """172.16-31.x.x should be detected as private."""
        from app.services.geoip import enrich_ip
        result = enrich_ip("172.16.0.1")
        assert result["country_name"] == "private"

    def test_localhost(self):
        """127.0.0.1 should be detected as private."""
        from app.services.geoip import enrich_ip
        result = enrich_ip("127.0.0.1")
        assert result["country_name"] == "private"

    def test_is_geoip_available(self):
        """is_geoip_available should return reader status."""
        from app.services.geoip import is_geoip_available

        with patch('app.services.geoip._reader', None):
            assert is_geoip_available() is False

        with patch('app.services.geoip._reader', MagicMock()):
            assert is_geoip_available() is True
