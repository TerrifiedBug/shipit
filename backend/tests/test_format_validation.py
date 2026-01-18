# backend/tests/test_format_validation.py
import pytest
from app.services.parser import FormatValidationError


class TestFormatValidationError:
    def test_exception_has_message_and_suggestions(self):
        """FormatValidationError should have message and suggestions."""
        error = FormatValidationError(
            "File doesn't appear to be CSV",
            suggested_formats=["ndjson", "raw"]
        )
        assert "CSV" in str(error)
        assert error.suggested_formats == ["ndjson", "raw"]

    def test_exception_message_attribute(self):
        """FormatValidationError should store message in attribute."""
        error = FormatValidationError("Test error message")
        assert error.message == "Test error message"

    def test_exception_default_suggestions_empty_list(self):
        """FormatValidationError should default to empty suggestions list."""
        error = FormatValidationError("Some error")
        assert error.suggested_formats == []

    def test_exception_is_exception_subclass(self):
        """FormatValidationError should be an Exception subclass."""
        error = FormatValidationError("Test")
        assert isinstance(error, Exception)

    def test_exception_can_be_raised_and_caught(self):
        """FormatValidationError should be raisable and catchable."""
        with pytest.raises(FormatValidationError) as exc_info:
            raise FormatValidationError(
                "Invalid format",
                suggested_formats=["json_array", "ndjson"]
            )
        assert exc_info.value.message == "Invalid format"
        assert exc_info.value.suggested_formats == ["json_array", "ndjson"]
