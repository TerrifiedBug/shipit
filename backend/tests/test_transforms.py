import pytest
from app.services.transforms import apply_transform, apply_transforms


class TestBasicTransforms:
    def test_lowercase(self):
        assert apply_transform("HELLO", "lowercase") == "hello"

    def test_uppercase(self):
        assert apply_transform("hello", "uppercase") == "HELLO"

    def test_trim(self):
        assert apply_transform("  hello  ", "trim") == "hello"

    def test_non_string_passthrough(self):
        """Non-string values should pass through unchanged."""
        assert apply_transform(123, "lowercase") == 123
        assert apply_transform(None, "trim") is None


class TestApplyTransforms:
    def test_multiple_transforms(self):
        """Should apply transforms in order."""
        result = apply_transforms("  HELLO  ", [
            {"name": "trim"},
            {"name": "lowercase"}
        ])
        assert result == "hello"

    def test_unknown_transform_passthrough(self):
        """Unknown transforms should pass value through."""
        assert apply_transform("test", "nonexistent") == "test"
