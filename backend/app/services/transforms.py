# backend/app/services/transforms.py
"""Field transformation functions for data ingestion."""
from __future__ import annotations

import logging
import re
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
    if value is None:
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


TRANSFORMS = {
    "lowercase": _lowercase,
    "uppercase": _uppercase,
    "trim": _trim,
    "regex_extract": _regex_extract,
    "regex_replace": _regex_replace,
    "truncate": _truncate,
}
