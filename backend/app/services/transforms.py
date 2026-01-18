# backend/app/services/transforms.py
"""Field transformation functions for data ingestion."""
from __future__ import annotations

from typing import Any


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


TRANSFORMS = {
    "lowercase": _lowercase,
    "uppercase": _uppercase,
    "trim": _trim,
}
