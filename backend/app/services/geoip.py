# backend/app/services/geoip.py
"""GeoIP enrichment using MaxMind GeoLite2 database."""
from __future__ import annotations

import ipaddress
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

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

MAXMIND_DOWNLOAD_URL = "https://download.maxmind.com/app/geoip_download"
DB_EDITION = "GeoLite2-City"


def _is_private_ip(ip_str: str) -> bool:
    """Check if IP is in a private range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return False


def _get_db_path() -> Path:
    """Get the path to the GeoIP database file."""
    return Path(settings.data_dir) / "GeoLite2-City.mmdb"


def _get_db_age_days() -> float | None:
    """Get the age of the database file in days, or None if it doesn't exist."""
    db_path = _get_db_path()
    if not db_path.exists():
        return None
    mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 86400  # Convert to days


def _download_database() -> bool:
    """Download the GeoLite2-City database from MaxMind.

    Returns:
        True if download was successful, False otherwise.
    """
    if not settings.maxmind_license_key:
        logger.warning("Cannot download GeoIP database: MAXMIND_LICENSE_KEY not set")
        return False

    logger.info("Downloading GeoLite2-City database from MaxMind...")

    try:
        # Download the tarball
        params = {
            "edition_id": DB_EDITION,
            "license_key": settings.maxmind_license_key,
            "suffix": "tar.gz",
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.get(MAXMIND_DOWNLOAD_URL, params=params)

            if response.status_code == 401:
                logger.error("Invalid MaxMind license key")
                return False
            elif response.status_code != 200:
                logger.error(f"Failed to download GeoIP database: HTTP {response.status_code}")
                return False

            # Save to temp file and extract
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name

        # Extract the .mmdb file from the tarball
        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".mmdb"):
                    # Extract to temp location first
                    member.name = os.path.basename(member.name)
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tar.extract(member, tmp_dir)
                        extracted_path = Path(tmp_dir) / member.name

                        # Move to final location
                        db_path = _get_db_path()
                        db_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(extracted_path), str(db_path))

                        logger.info(f"GeoIP database downloaded successfully to {db_path}")
                        return True

        logger.error("No .mmdb file found in downloaded archive")
        return False

    except httpx.TimeoutException:
        logger.error("Timeout downloading GeoIP database")
        return False
    except Exception as e:
        logger.error(f"Error downloading GeoIP database: {e}")
        return False
    finally:
        # Clean up temp file
        try:
            if 'tmp_path' in locals():
                os.unlink(tmp_path)
        except Exception:
            pass


def _should_update() -> bool:
    """Check if the database should be updated."""
    if settings.geoip_auto_update_days <= 0:
        return False

    age = _get_db_age_days()
    if age is None:
        return True  # Database doesn't exist, need to download

    return age >= settings.geoip_auto_update_days


def init_geoip() -> None:
    """Initialize GeoIP database reader, downloading if necessary."""
    global _reader

    if not settings.maxmind_license_key:
        logger.info("MAXMIND_LICENSE_KEY not set - GeoIP enrichment disabled")
        return

    db_path = _get_db_path()

    # Check if we need to download or update
    if not db_path.exists():
        logger.info("GeoIP database not found, attempting to download...")
        if not _download_database():
            logger.warning("GeoIP enrichment disabled - database download failed")
            return
    elif _should_update():
        age = _get_db_age_days()
        logger.info(f"GeoIP database is {age:.1f} days old, checking for updates...")
        _download_database()  # Best-effort update, continue with existing if fails

    # Load the database
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
