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


class TestBasicTransformsEdgeCases:
    def test_unicode_strings(self):
        """Unicode strings are handled correctly."""
        assert apply_transform("CAFÉ", "lowercase") == "café"
        assert apply_transform("héllo", "uppercase") == "HÉLLO"


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

    def test_empty_transforms_list(self):
        """Empty transform list returns original value."""
        assert apply_transforms("test", []) == "test"

    def test_transform_order_matters(self):
        """Different order produces different results."""
        result = apply_transforms("  HELLO  ", [
            {"name": "trim"},
            {"name": "lowercase"}
        ])
        assert result == "hello"

    def test_missing_transform_name(self):
        """Transform without name key is handled gracefully."""
        result = apply_transforms("test", [{"typo": "lowercase"}])
        assert result == "test"


class TestRegexTransforms:
    def test_regex_extract(self):
        """regex_extract should capture first group."""
        result = apply_transform(
            "user=danny action=login",
            "regex_extract",
            pattern=r"user=(\w+)"
        )
        assert result == "danny"

    def test_regex_extract_no_match(self):
        """regex_extract with no match should return original."""
        result = apply_transform(
            "no match here",
            "regex_extract",
            pattern=r"user=(\w+)"
        )
        assert result == "no match here"

    def test_regex_replace(self):
        """regex_replace should replace matches."""
        result = apply_transform(
            "192.168.1.50",
            "regex_replace",
            pattern=r"(\d+)\.(\d+)\.(\d+)\.\d+",
            replacement=r"\1.\2.\3.x"
        )
        assert result == "192.168.1.x"

    def test_truncate(self):
        """truncate should limit string length."""
        result = apply_transform("abcdefghij", "truncate", max_length=5)
        assert result == "abcde"

    def test_regex_extract_invalid_pattern(self):
        """Invalid regex should return original value."""
        result = apply_transform("test", "regex_extract", pattern="[unclosed")
        assert result == "test"

    def test_regex_extract_no_capture_group(self):
        """Pattern without capture group returns original."""
        result = apply_transform("hello", "regex_extract", pattern=r"\w+")
        assert result == "hello"

    def test_truncate_zero_length(self):
        """Truncate to 0 returns empty string."""
        result = apply_transform("test", "truncate", max_length=0)
        assert result == ""

    def test_regex_replace_empty_replacement(self):
        """Empty replacement should remove matches."""
        result = apply_transform("hello123world", "regex_replace", pattern=r"\d+", replacement="")
        assert result == "helloworld"


class TestEncodingTransforms:
    def test_base64_decode(self):
        """base64_decode should decode base64 strings."""
        result = apply_transform("aGVsbG8gd29ybGQ=", "base64_decode")
        assert result == "hello world"

    def test_base64_decode_invalid(self):
        """base64_decode with invalid input should return original."""
        result = apply_transform("not valid base64!!!", "base64_decode")
        assert result == "not valid base64!!!"

    def test_url_decode(self):
        """url_decode should decode URL-encoded strings."""
        result = apply_transform("hello%20world%21", "url_decode")
        assert result == "hello world!"
