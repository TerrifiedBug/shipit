import tempfile
from pathlib import Path

import pytest

from app.services.parser import detect_format, infer_fields, parse_preview


class TestDetectFormat:
    def test_json_array(self, json_array_file):
        assert detect_format(json_array_file) == "json_array"

    def test_ndjson(self, ndjson_file):
        assert detect_format(ndjson_file) == "ndjson"

    def test_csv(self, csv_file):
        assert detect_format(csv_file) == "csv"

    def test_empty_file(self, empty_file):
        # Empty files default to CSV
        assert detect_format(empty_file) == "csv"

    def test_json_array_with_whitespace(self, temp_dir):
        """JSON array with leading whitespace should still be detected."""
        file_path = temp_dir / "whitespace.json"
        file_path.write_text('  \n  [{"a": 1}]')
        assert detect_format(file_path) == "json_array"

    def test_ndjson_with_whitespace(self, temp_dir):
        """NDJSON with leading whitespace should still be detected."""
        file_path = temp_dir / "whitespace.ndjson"
        file_path.write_text('  \n  {"a": 1}\n{"b": 2}')
        assert detect_format(file_path) == "ndjson"

    def test_misnamed_json_as_csv(self, temp_dir):
        """Test that .csv file with JSON content is detected as JSON."""
        file_path = temp_dir / "data.csv"
        file_path.write_text('[{"name": "Alice", "age": 30}]')
        assert detect_format(file_path) == "json_array"

    def test_misnamed_ndjson_as_txt(self, temp_dir):
        """Test that .txt file with NDJSON content is detected as NDJSON."""
        file_path = temp_dir / "data.txt"
        file_path.write_text('{"name": "Alice"}\n{"name": "Bob"}')
        assert detect_format(file_path) == "ndjson"

    def test_correct_csv_extension(self, temp_dir):
        """Test that .csv file with valid CSV content is detected as CSV."""
        file_path = temp_dir / "data.csv"
        file_path.write_text('name,age\nAlice,30\nBob,25')
        assert detect_format(file_path) == "csv"

    def test_correct_json_extension(self, temp_dir):
        """Test that .json file with valid JSON content is detected as JSON."""
        file_path = temp_dir / "data.json"
        file_path.write_text('[{"name": "Alice"}]')
        assert detect_format(file_path) == "json_array"


class TestParsePreview:
    def test_json_array(self, json_array_file):
        records = parse_preview(json_array_file, "json_array", limit=100)
        assert len(records) == 3
        assert records[0]["name"] == "Alice"
        assert records[0]["age"] == 30
        assert records[0]["active"] is True

    def test_ndjson(self, ndjson_file):
        records = parse_preview(ndjson_file, "ndjson", limit=100)
        assert len(records) == 3
        assert records[1]["name"] == "Bob"
        assert records[1]["age"] == 25

    def test_csv(self, csv_file):
        records = parse_preview(csv_file, "csv", limit=100)
        assert len(records) == 3
        # CSV values are strings
        assert records[0]["name"] == "Alice"
        assert records[0]["age"] == "30"

    def test_limit(self, temp_dir):
        """Preview should respect the limit parameter."""
        file_path = temp_dir / "large.json"
        data = [{"id": i} for i in range(200)]
        import json
        file_path.write_text(json.dumps(data))

        records = parse_preview(file_path, "json_array", limit=50)
        assert len(records) == 50
        assert records[0]["id"] == 0
        assert records[49]["id"] == 49

    def test_csv_semicolon_delimiter(self, csv_semicolon_file):
        """CSV parser should auto-detect semicolon delimiter."""
        records = parse_preview(csv_semicolon_file, "csv", limit=100)
        assert len(records) == 2
        assert records[0]["name"] == "Alice"


class TestInferFields:
    def test_basic_fields(self):
        records = [
            {"name": "Alice", "age": 30, "active": True},
            {"name": "Bob", "age": 25, "active": False},
        ]
        fields = infer_fields(records)

        assert len(fields) == 3
        field_map = {f["name"]: f["type"] for f in fields}
        assert field_map["name"] == "string"
        assert field_map["age"] == "integer"
        assert field_map["active"] == "boolean"

    def test_float_type(self):
        records = [{"value": 1.5}, {"value": 2.7}]
        fields = infer_fields(records)
        assert fields[0]["type"] == "float"

    def test_mixed_int_float(self):
        """Mixed integer and float should result in float."""
        records = [{"value": 1}, {"value": 2.5}]
        fields = infer_fields(records)
        assert fields[0]["type"] == "float"

    def test_object_type(self):
        records = [{"data": {"nested": "value"}}]
        fields = infer_fields(records)
        assert fields[0]["type"] == "object"

    def test_array_type(self):
        records = [{"items": [1, 2, 3]}]
        fields = infer_fields(records)
        assert fields[0]["type"] == "array"

    def test_string_numbers(self):
        """String values that look like numbers should be detected."""
        records = [{"id": "123"}, {"id": "456"}]
        fields = infer_fields(records)
        assert fields[0]["type"] == "integer"

    def test_empty_records(self):
        assert infer_fields([]) == []

    def test_preserves_field_order(self):
        """Fields should be in the order they appear in the first record."""
        records = [{"z": 1, "a": 2, "m": 3}]
        fields = infer_fields(records)
        assert [f["name"] for f in fields] == ["z", "a", "m"]

    def test_additional_fields_from_later_records(self):
        """Fields that only appear in later records should be included."""
        records = [
            {"a": 1},
            {"a": 2, "b": 3},
        ]
        fields = infer_fields(records)
        assert len(fields) == 2
        assert [f["name"] for f in fields] == ["a", "b"]


class TestTsvParser:
    def test_parse_tsv(self, temp_dir):
        """Test TSV parsing."""
        content = "name\tage\tcity\nAlice\t30\tNYC\nBob\t25\tLA"
        file_path = temp_dir / "test.tsv"
        file_path.write_text(content)
        records = parse_preview(file_path, "tsv", limit=10)
        assert len(records) == 2
        assert records[0] == {"name": "Alice", "age": "30", "city": "NYC"}

    def test_detect_tsv_by_extension(self, temp_dir):
        """Test TSV detection by file extension."""
        content = "name\tage\nAlice\t30"
        file_path = temp_dir / "test.tsv"
        file_path.write_text(content)
        assert detect_format(file_path) == "tsv"


class TestLtsvParser:
    def test_parse_ltsv(self, temp_dir):
        """Test LTSV parsing."""
        content = "host:192.168.1.1\tmethod:GET\tpath:/api/health\nhost:192.168.1.2\tmethod:POST\tpath:/api/upload"
        file_path = temp_dir / "test.ltsv"
        file_path.write_text(content)
        records = parse_preview(file_path, "ltsv", limit=10)
        assert len(records) == 2
        assert records[0] == {"host": "192.168.1.1", "method": "GET", "path": "/api/health"}

    def test_detect_ltsv_by_extension(self, temp_dir):
        """Test LTSV detection by file extension."""
        content = "host:192.168.1.1\tmethod:GET"
        file_path = temp_dir / "test.ltsv"
        file_path.write_text(content)
        assert detect_format(file_path) == "ltsv"


class TestSyslogParser:
    def test_parse_syslog_rfc3164(self, temp_dir):
        """Test syslog RFC 3164 parsing."""
        content = "<34>Oct 11 22:14:15 mymachine su: 'su root' failed for user on /dev/pts/8"
        file_path = temp_dir / "test.log"
        file_path.write_text(content)
        records = parse_preview(file_path, "syslog", limit=10)
        assert len(records) == 1
        assert records[0]["priority"] == "34"
        assert records[0]["hostname"] == "mymachine"

    def test_detect_syslog_by_content(self, temp_dir):
        """Test syslog detection by content pattern."""
        content = "<34>Oct 11 22:14:15 mymachine su: test message"
        file_path = temp_dir / "test.log"
        file_path.write_text(content)
        assert detect_format(file_path) == "syslog"

    def test_log_file_not_syslog(self, temp_dir):
        """Test .log file that is not syslog defaults to csv."""
        content = "name,age\nAlice,30"
        file_path = temp_dir / "test.log"
        file_path.write_text(content)
        assert detect_format(file_path) == "csv"

    def test_syslog_fallback(self, temp_dir):
        """Test syslog parser fallback for non-matching lines."""
        content = "This is just a plain log message"
        file_path = temp_dir / "test.log"
        file_path.write_text(content)
        records = parse_preview(file_path, "syslog", limit=10)
        assert len(records) == 1
        assert records[0] == {"message": "This is just a plain log message"}
