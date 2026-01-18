"""Request utility functions for extracting client information."""
from __future__ import annotations

import ipaddress

from fastapi import Request

from app.config import settings


def _is_trusted_proxy(ip: str) -> bool:
    """Check if IP is in the trusted proxy ranges.

    Args:
        ip: The IP address to check

    Returns:
        True if IP is in a trusted proxy CIDR range, False otherwise
    """
    if not settings.trusted_proxies:
        return False

    try:
        client_addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for cidr in settings.trusted_proxies:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            if client_addr in network:
                return True
        except ValueError:
            # Invalid CIDR in config - skip it
            continue

    return False


def get_client_ip(request: Request | None) -> str:
    """Extract client IP from request, respecting trusted proxy configuration.

    Only trusts X-Forwarded-For header when the direct connection comes from
    a trusted proxy. This prevents IP spoofing by untrusted clients.

    Args:
        request: The FastAPI Request object

    Returns:
        The client IP address, or 'unknown' if it cannot be determined
    """
    if not request:
        return "unknown"

    # Get direct connection IP
    if not request.client:
        return "unknown"

    direct_ip = request.client.host

    # Only trust X-Forwarded-For if connection is from a trusted proxy
    if _is_trusted_proxy(direct_ip):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Use the first IP in the chain (original client)
            first_ip = forwarded.split(",")[0].strip()
            if first_ip:
                return first_ip

    return direct_ip
