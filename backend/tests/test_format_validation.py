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


class TestJsonValidation:
    def test_valid_json_array_passes(self, temp_dir):
        """Valid JSON array should pass validation."""
        file_path = temp_dir / "valid.json"
        file_path.write_text('[{"name": "Alice"}, {"name": "Bob"}]')
        validate_format(file_path, "json_array")

    def test_ndjson_as_json_array_fails(self, temp_dir):
        """NDJSON file selected as JSON array should fail."""
        file_path = temp_dir / "ndjson.json"
        file_path.write_text('{"name": "Alice"}\n{"name": "Bob"}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "json_array")
        assert "ndjson" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_empty_json_file_fails(self, temp_dir):
        """Empty JSON file should fail validation."""
        file_path = temp_dir / "empty.json"
        file_path.write_text("")

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "json_array")
        assert "empty" in exc_info.value.message.lower()

    def test_invalid_json_fails(self, temp_dir):
        """Invalid JSON should fail with suggestions."""
        file_path = temp_dir / "invalid.json"
        file_path.write_text('[{"name": "Alice"')  # Missing closing brackets

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "json_array")
        assert "ndjson" in [s.lower() for s in exc_info.value.suggested_formats]


class TestNdjsonValidation:
    def test_valid_ndjson_passes(self, temp_dir):
        """Valid NDJSON should pass validation."""
        file_path = temp_dir / "valid.ndjson"
        file_path.write_text('{"a": 1}\n{"b": 2}\n{"c": 3}')
        validate_format(file_path, "ndjson")

    def test_invalid_json_lines_fail(self, temp_dir):
        """Lines that aren't valid JSON should fail."""
        file_path = temp_dir / "invalid.ndjson"
        file_path.write_text('not json\nalso not json')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "ndjson")
        assert "raw" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_ndjson_with_empty_lines_passes(self, temp_dir):
        """NDJSON with empty lines should still pass."""
        file_path = temp_dir / "with_empty.ndjson"
        file_path.write_text('{"a": 1}\n\n{"b": 2}\n\n{"c": 3}')
        validate_format(file_path, "ndjson")

    def test_mostly_invalid_lines_fail(self, temp_dir):
        """NDJSON with more invalid than valid lines should fail."""
        file_path = temp_dir / "mostly_invalid.ndjson"
        file_path.write_text('{"valid": 1}\nnot json\nalso not json\nstill not json')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "ndjson")
        assert "raw" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_array_lines_fail(self, temp_dir):
        """Lines that are JSON arrays (not objects) should fail."""
        file_path = temp_dir / "arrays.ndjson"
        file_path.write_text('[1, 2, 3]\n[4, 5, 6]')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "ndjson")
        assert "raw" in [s.lower() for s in exc_info.value.suggested_formats]


class TestTsvValidation:
    def test_valid_tsv_passes(self, temp_dir):
        file_path = temp_dir / "valid.tsv"
        file_path.write_text("name\tage\tcity\nAlice\t30\tNYC")
        validate_format(file_path, "tsv")

    def test_no_tabs_fails(self, temp_dir):
        file_path = temp_dir / "notabs.tsv"
        file_path.write_text("name age city\nAlice 30 NYC")
        with pytest.raises(FormatValidationError):
            validate_format(file_path, "tsv")


class TestLtsvValidation:
    def test_valid_ltsv_passes(self, temp_dir):
        file_path = temp_dir / "valid.ltsv"
        file_path.write_text("host:192.168.1.1\tmethod:GET\nhost:192.168.1.2\tmethod:POST")
        validate_format(file_path, "ltsv")

    def test_no_colons_fails(self, temp_dir):
        file_path = temp_dir / "nocolons.ltsv"
        file_path.write_text("just\tsome\ttabs")
        with pytest.raises(FormatValidationError):
            validate_format(file_path, "ltsv")


class TestSyslogValidation:
    def test_valid_syslog_passes(self, temp_dir):
        file_path = temp_dir / "valid.log"
        file_path.write_text("<34>Oct 11 22:14:15 mymachine su: test message")
        validate_format(file_path, "syslog")

    def test_no_priority_fails(self, temp_dir):
        file_path = temp_dir / "nosyslog.log"
        file_path.write_text("Oct 11 22:14:15 mymachine su: test message")
        with pytest.raises(FormatValidationError):
            validate_format(file_path, "syslog")


class TestLogfmtValidation:
    def test_valid_logfmt_passes(self, temp_dir):
        file_path = temp_dir / "valid.log"
        file_path.write_text('level=info msg="hello world" time=2024-01-01')
        validate_format(file_path, "logfmt")

    def test_no_keyvalue_fails(self, temp_dir):
        file_path = temp_dir / "nologfmt.log"
        file_path.write_text("just plain text without equals signs")
        with pytest.raises(FormatValidationError):
            validate_format(file_path, "logfmt")


class TestJsonRejectionInOtherFormats:
    """Ensure JSON content is rejected when user selects non-JSON formats."""

    def test_json_object_rejected_as_csv(self, temp_dir):
        """JSON objects should be rejected when parsed as CSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('{"name": "Alice", "age": 30}\n{"name": "Bob", "age": 25}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "json" in exc_info.value.message.lower()
        assert "ndjson" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_array_rejected_as_csv(self, temp_dir):
        """JSON arrays should be rejected when parsed as CSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('[{"name": "Alice"}, {"name": "Bob"}]')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "json" in exc_info.value.message.lower()
        assert "json_array" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_object_rejected_as_tsv(self, temp_dir):
        """JSON objects should be rejected when parsed as TSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('{"name": "Alice", "age": 30}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "tsv")
        assert "json" in exc_info.value.message.lower()

    def test_json_array_rejected_as_tsv(self, temp_dir):
        """JSON arrays should be rejected when parsed as TSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('[{"name": "Alice"}]')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "tsv")
        assert "json_array" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_object_rejected_as_ltsv(self, temp_dir):
        """JSON objects should be rejected when parsed as LTSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('{"host": "192.168.1.1", "method": "GET"}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "ltsv")
        assert "json" in exc_info.value.message.lower()

    def test_json_array_rejected_as_ltsv(self, temp_dir):
        """JSON arrays should be rejected when parsed as LTSV."""
        file_path = temp_dir / "data.json"
        file_path.write_text('[{"host": "192.168.1.1"}]')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "ltsv")
        assert "json_array" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_object_rejected_as_logfmt(self, temp_dir):
        """JSON objects should be rejected when parsed as logfmt."""
        file_path = temp_dir / "data.json"
        file_path.write_text('{"level": "info", "msg": "hello"}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "logfmt")
        assert "json" in exc_info.value.message.lower()

    def test_json_array_rejected_as_logfmt(self, temp_dir):
        """JSON arrays should be rejected when parsed as logfmt."""
        file_path = temp_dir / "data.json"
        file_path.write_text('[{"level": "info"}]')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "logfmt")
        assert "json_array" in [s.lower() for s in exc_info.value.suggested_formats]

    def test_json_with_leading_whitespace_rejected(self, temp_dir):
        """JSON with leading whitespace should still be rejected."""
        file_path = temp_dir / "data.json"
        file_path.write_text('  \n  {"name": "Alice"}')

        with pytest.raises(FormatValidationError) as exc_info:
            validate_format(file_path, "csv")
        assert "json" in exc_info.value.message.lower()
