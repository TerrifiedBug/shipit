import pytest
from unittest.mock import patch, MagicMock

from app.services.ingestion import apply_field_mappings, ingest_file, stream_records
from app.services.opensearch import validate_index_name


class TestApplyFieldMappings:
    def test_no_mappings(self):
        record = {"name": "Alice", "age": 30}
        result = apply_field_mappings(record, {}, [])
        assert result == {"name": "Alice", "age": 30}

    def test_rename_field(self):
        record = {"src_ip": "1.2.3.4", "dst_ip": "5.6.7.8"}
        mappings = {"src_ip": "source.ip", "dst_ip": "destination.ip"}
        result = apply_field_mappings(record, mappings, [])
        assert result == {"source.ip": "1.2.3.4", "destination.ip": "5.6.7.8"}

    def test_exclude_field(self):
        record = {"name": "Alice", "internal_id": "xyz", "age": 30}
        result = apply_field_mappings(record, {}, ["internal_id"])
        assert result == {"name": "Alice", "age": 30}

    def test_rename_and_exclude(self):
        record = {"name": "Alice", "internal_id": "xyz", "src_ip": "1.2.3.4"}
        mappings = {"src_ip": "source.ip"}
        excluded = ["internal_id"]
        result = apply_field_mappings(record, mappings, excluded)
        assert result == {"name": "Alice", "source.ip": "1.2.3.4"}


class TestValidateIndexName:
    def test_valid_name(self):
        is_valid, error = validate_index_name("my-index")
        assert is_valid is True
        assert error == ""

    def test_empty_name(self):
        is_valid, error = validate_index_name("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_uppercase(self):
        is_valid, error = validate_index_name("MyIndex")
        assert is_valid is False
        assert "lowercase" in error.lower()

    def test_invalid_start_dash(self):
        is_valid, error = validate_index_name("-index")
        assert is_valid is False

    def test_invalid_start_underscore(self):
        is_valid, error = validate_index_name("_index")
        assert is_valid is False

    def test_invalid_characters(self):
        invalid_names = ["my index", "my/index", "my*index", "my?index", "my:index"]
        for name in invalid_names:
            is_valid, error = validate_index_name(name)
            assert is_valid is False, f"Expected '{name}' to be invalid"


class TestStreamRecords:
    def test_stream_json_array(self, json_array_file):
        records = list(stream_records(json_array_file, "json_array"))
        assert len(records) == 3
        assert records[0]["name"] == "Alice"

    def test_stream_ndjson(self, ndjson_file):
        records = list(stream_records(ndjson_file, "ndjson"))
        assert len(records) == 3
        assert records[1]["name"] == "Bob"

    def test_stream_csv(self, csv_file):
        records = list(stream_records(csv_file, "csv"))
        assert len(records) == 3
        assert records[0]["name"] == "Alice"


class TestIngestFile:
    @patch("app.services.ingestion.bulk_index")
    def test_basic_ingestion(self, mock_bulk_index, json_array_file):
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
        )

        assert result.processed == 3
        assert result.success == 3
        assert result.failed == 0
        mock_bulk_index.assert_called_once()

    @patch("app.services.ingestion.bulk_index")
    def test_ingestion_with_field_mappings(self, mock_bulk_index, json_array_file):
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
            field_mappings={"name": "user.name"},
        )

        # Check that mappings were applied
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]  # Second positional arg is records
        assert all("user.name" in r for r in records)
        assert all("name" not in r for r in records)

    @patch("app.services.ingestion.bulk_index")
    def test_ingestion_with_exclusions(self, mock_bulk_index, json_array_file):
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
            excluded_fields=["age"],
        )

        # Check that exclusions were applied
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all("age" not in r for r in records)

    @patch("app.services.ingestion.settings")
    @patch("app.services.ingestion.bulk_index")
    def test_batching(self, mock_bulk_index, mock_settings, temp_dir):
        """Test that records are batched correctly."""
        # Create a file with 5 records
        import json
        file_path = temp_dir / "batch_test.json"
        data = [{"id": i} for i in range(5)]
        file_path.write_text(json.dumps(data))

        mock_bulk_index.return_value = {"success": 2, "failed": []}
        mock_settings.bulk_batch_size = 2  # Small batch size
        mock_settings.data_dir = "/data"

        result = ingest_file(
            file_path=file_path,
            file_format="json_array",
            index_name="shipit-test",
        )

        # Should have been called 3 times: 2+2+1
        assert mock_bulk_index.call_count == 3
        assert result.processed == 5

    @patch("app.services.ingestion.settings")
    @patch("app.services.ingestion.bulk_index")
    def test_progress_callback(self, mock_bulk_index, mock_settings, temp_dir):
        """Test that progress callback is called."""
        import json
        file_path = temp_dir / "progress_test.json"
        data = [{"id": i} for i in range(4)]
        file_path.write_text(json.dumps(data))

        mock_bulk_index.return_value = {"success": 2, "failed": []}
        mock_settings.bulk_batch_size = 2  # Small batch size
        mock_settings.data_dir = "/data"

        progress_calls = []

        def progress_callback(processed, success, failed):
            progress_calls.append((processed, success, failed))

        ingest_file(
            file_path=file_path,
            file_format="json_array",
            index_name="shipit-test",
            progress_callback=progress_callback,
        )

        # Should have been called twice (after each batch)
        assert len(progress_calls) == 2
        assert progress_calls[0] == (2, 2, 0)
        assert progress_calls[1] == (4, 4, 0)

    @patch("app.services.ingestion.bulk_index")
    def test_handles_failures(self, mock_bulk_index, json_array_file):
        """Test that failures are tracked correctly."""
        mock_bulk_index.return_value = {
            "success": 2,
            "failed": [{"record": {"name": "Bob"}, "error": "Mapping error"}],
        }

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
        )

        assert result.success == 2
        assert result.failed == 1
        assert len(result.failed_records) == 1
