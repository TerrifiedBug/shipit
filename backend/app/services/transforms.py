# backend/app/services/transforms.py
"""Field transformation functions for data ingestion."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)

# Limit pattern complexity to mitigate ReDoS attacks
MAX_PATTERN_LENGTH = 500


def apply_transform(value: Any, transform_name: str, **options) -> Any:
    """Apply a single transform to a value.

    Args:
        value: The value to transform
        transform_name: Name of the transform to apply
        **options: Transform-specific options

    Returns:
        Transformed value, or original value if transform doesn't apply
    """
    # Special handling for transforms that need to process None values
    if value is None and transform_name not in ("default", "hash_sha256"):
        return None

    transform_fn = TRANSFORMS.get(transform_name)
    if transform_fn:
        return transform_fn(value, **options)

    return value


def apply_transforms(value: Any, transforms: list[dict]) -> Any:
    """Apply a list of transforms in order.

    Args:
        value: The value to transform
        transforms: List of transform configs, each with 'name' and optional params

    Returns:
        Value after all transforms applied
    """
    for t in transforms:
        name = t.get("name")
        options = {k: v for k, v in t.items() if k != "name"}
        value = apply_transform(value, name, **options)
    return value


# Transform implementations

def _lowercase(value: Any, **_) -> Any:
    return value.lower() if isinstance(value, str) else value


def _uppercase(value: Any, **_) -> Any:
    return value.upper() if isinstance(value, str) else value


def _trim(value: Any, **_) -> Any:
    return value.strip() if isinstance(value, str) else value


def _regex_extract(value: Any, pattern: str = "", **_) -> Any:
    """Extract first capture group from regex match."""
    if not isinstance(value, str) or not pattern:
        return value
    if len(pattern) > MAX_PATTERN_LENGTH:
        logger.warning(f"Regex pattern too long ({len(pattern)} chars), skipping transform")
        return value
    try:
        match = re.search(pattern, value)
        if match and match.groups():
            return match.group(1)
    except re.error as e:
        logger.warning(f"Invalid regex pattern in regex_extract: {e}")
    return value


def _regex_replace(value: Any, pattern: str = "", replacement: str = "", **_) -> Any:
    """Replace regex matches in string."""
    if not isinstance(value, str) or not pattern:
        return value
    if len(pattern) > MAX_PATTERN_LENGTH:
        logger.warning(f"Regex pattern too long ({len(pattern)} chars), skipping transform")
        return value
    try:
        return re.sub(pattern, replacement, value)
    except re.error as e:
        logger.warning(f"Invalid regex pattern in regex_replace: {e}")
        return value


def _truncate(value: Any, max_length: int = 100, **_) -> Any:
    """Truncate string to max length."""
    if not isinstance(value, str):
        return value
    return value[:max_length]


def _base64_decode(value: Any, **_) -> Any:
    """Decode base64 string."""
    if not isinstance(value, str):
        return value
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        return decoded
    except Exception:
        return value


def _url_decode(value: Any, **_) -> Any:
    """Decode URL-encoded string."""
    if not isinstance(value, str):
        return value
    return urllib.parse.unquote(value)


def _hash_sha256(value: Any, **_) -> Any:
    """Hash value with SHA256."""
    if value is None:
        return value
    return hashlib.sha256(str(value).encode()).hexdigest()


def _mask_email(value: Any, **_) -> Any:
    """Mask email address, keeping first char and domain extension."""
    if not isinstance(value, str) or "@" not in value:
        return value

    local, domain = value.rsplit("@", 1)
    domain_parts = domain.rsplit(".", 1)

    masked_local = local[0] + "****" if local else "****"

    if len(domain_parts) == 2:
        masked_domain = domain_parts[0][0] + "******." + domain_parts[1]
    else:
        masked_domain = domain[0] + "******"

    return f"{masked_local}@{masked_domain}"


def _mask_ip(value: Any, **_) -> Any:
    """Mask IP address last octet."""
    if not isinstance(value, str):
        return value

    # IPv4
    ipv4_pattern = re.compile(r'^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$')
    match = ipv4_pattern.match(value)
    if match:
        return f"{match.group(1)}.x"

    return value


def _default(value: Any, default_value: str = "", **_) -> Any:
    """Replace None or empty string with default value."""
    if value is None or value == "":
        return default_value
    return value


def _parse_json(value: Any, path: str = "", **_) -> Any:
    """Parse JSON string and optionally extract a value by path."""
    if not isinstance(value, str):
        return value

    try:
        parsed = json.loads(value)

        if not path:
            return parsed

        # Navigate the path
        current = parsed
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return value  # Path not found, return original

        return current
    except json.JSONDecodeError:
        return value


def _parse_kv(value: Any, delimiter: str = " ", separator: str = "=", **_) -> Any:
    """Parse key=value pairs into a dictionary."""
    if not isinstance(value, str):
        return value

    result = {}
    pairs = value.split(delimiter)
    for pair in pairs:
        if separator in pair:
            key, val = pair.split(separator, 1)
            result[key.strip()] = val.strip()

    return result if result else value


TRANSFORMS = {
    "lowercase": _lowercase,
    "uppercase": _uppercase,
    "trim": _trim,
    "regex_extract": _regex_extract,
    "regex_replace": _regex_replace,
    "truncate": _truncate,
    "base64_decode": _base64_decode,
    "url_decode": _url_decode,
    "hash_sha256": _hash_sha256,
    "mask_email": _mask_email,
    "mask_ip": _mask_ip,
    "default": _default,
    "parse_json": _parse_json,
    "parse_kv": _parse_kv,
}
