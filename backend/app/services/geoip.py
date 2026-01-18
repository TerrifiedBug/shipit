# backend/app/services/geoip.py
"""GeoIP enrichment using MaxMind GeoLite2 database."""
from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Global reader instance
_reader = None

# Private IP ranges
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def _is_private_ip(ip_str: str) -> bool:
    """Check if IP is in a private range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return False


def init_geoip() -> None:
    """Initialize GeoIP database reader."""
    global _reader

    if not settings.maxmind_license_key:
        logger.info("MAXMIND_LICENSE_KEY not set - GeoIP enrichment disabled")
        return

    db_path = Path(settings.data_dir) / "GeoLite2-City.mmdb"

    if not db_path.exists():
        logger.warning(f"GeoIP database not found at {db_path}")
        return

    try:
        import geoip2.database
        _reader = geoip2.database.Reader(str(db_path))
        logger.info("GeoIP database loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load GeoIP database: {e}")


def enrich_ip(ip_str: str) -> dict[str, Any] | None:
    """Enrich an IP address with geographic data.

    Returns:
        Dict with country_name, city_name, location (lat/lon), or None if lookup fails.
        For private IPs, returns {"country_name": "private", ...}
    """
    if not ip_str:
        return None

    # Check for private IPs first
    if _is_private_ip(ip_str):
        return {
            "country_name": "private",
            "city_name": None,
            "location": None,
        }

    if _reader is None:
        return None

    try:
        response = _reader.city(ip_str)
        return {
            "country_name": response.country.name,
            "city_name": response.city.name if response.city else None,
            "location": {
                "lat": response.location.latitude,
                "lon": response.location.longitude,
            } if response.location.latitude else None,
        }
    except Exception:
        return None


def is_geoip_available() -> bool:
    """Check if GeoIP enrichment is available."""
    return _reader is not None
