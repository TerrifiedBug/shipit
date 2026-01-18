# backend/tests/test_format_validation.py
import pytest
from app.services.parser import FormatValidationError, validate_format


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


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for test files."""
    return tmp_path


class TestCsvValidation:
    def test_valid_csv_passes(self, temp_dir):
        """Valid CSV should pass validation."""
        file_path = temp_dir / "valid.csv"
        file_path.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA")
        validate_format(file_path, "csv")  # Should not raise

    def test_no_header_fails(self, temp_dir):
        """CSV without consistent header should fail."""
        file_path = temp_dir / "noheader.csv"
        file_path.write_text("just some text without any delimiters")

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "raw" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_inconsistent_columns_fails(self, temp_dir):
        """CSV with inconsistent column counts should fail."""
        file_path = temp_dir / "inconsistent.csv"
        file_path.write_text("a,b,c\n1,2\n3,4,5,6,7")

        with pytest.raises(FormatValidationError):
            validate_format(file_path, "csv")

    def test_empty_file_fails(self, temp_dir):
        """Empty CSV file should fail validation."""
        file_path = temp_dir / "empty.csv"
        file_path.write_text("")

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "empty" in exc_info.value.message.lower()

    def test_whitespace_only_fails(self, temp_dir):
        """Whitespace-only file should fail validation."""
        file_path = temp_dir / "whitespace.csv"
        file_path.write_text("   \n\n   \n")

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "empty" in exc_info.value.message.lower()

    def test_single_row_fails(self, temp_dir):
        """CSV with only header row (no data) should fail."""
        file_path = temp_dir / "headeronly.csv"
        file_path.write_text("name,age,city")

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "raw" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_unknown_format_passes(self, temp_dir):
        """Unknown format should pass (no validator)."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("anything")
        validate_format(file_path, "raw")  # Should not raise - no validator for raw
