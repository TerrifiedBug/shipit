import pytest
from unittest.mock import patch, MagicMock

from app.services.ingestion import apply_field_mappings, ingest_file, stream_records, merge_multiline
from app.services.opensearch import validate_index_name


def test_merge_multiline_with_timestamp():
    """Test merging lines based on timestamp pattern."""
    lines = [
        "2026-01-18 10:00:00 First message",
        "  continuation line 1",
        "  continuation line 2",
        "2026-01-18 10:00:01 Second message",
        "2026-01-18 10:00:02 Third message",
    ]

    pattern = r"^\d{4}-\d{2}-\d{2}"
    result = list(merge_multiline(iter(lines), pattern, max_lines=100))

    assert len(result) == 3
    assert result[0] == "2026-01-18 10:00:00 First message\n  continuation line 1\n  continuation line 2"
    assert result[1] == "2026-01-18 10:00:01 Second message"
    assert result[2] == "2026-01-18 10:00:02 Third message"


def test_merge_multiline_max_lines():
    """Test max_lines limit prevents runaway merging."""
    lines = ["START"] + [f"  line {i}" for i in range(200)]

    pattern = r"^START"
    result = list(merge_multiline(iter(lines), pattern, max_lines=50))

    # Should have flushed at 50 lines
    assert len(result) >= 2


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
        mock_settings.data_dir = str(temp_dir)

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
        mock_settings.data_dir = str(temp_dir)

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

    @patch("app.services.ingestion.bulk_index")
    def test_include_filename(self, mock_bulk_index, json_array_file):
        """Test that source filename is added to records when requested."""
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
            include_filename=True,
        )

        # Check that filename field was added
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all("source_file" in r for r in records)
        # The fixture file is named test_data.json
        assert all(r["source_file"] == json_array_file.name for r in records)

    @patch("app.services.ingestion.bulk_index")
    def test_custom_filename_field(self, mock_bulk_index, json_array_file):
        """Test that custom filename field name works."""
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
            include_filename=True,
            filename_field="origin_file",
        )

        # Check that custom field name was used
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all("origin_file" in r for r in records)
        assert all("source_file" not in r for r in records)

    @patch("app.services.ingestion.bulk_index")
    def test_filename_not_included_by_default(self, mock_bulk_index, json_array_file):
        """Test that filename is not added when not requested."""
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
        )

        # Check that filename field was NOT added
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all("source_file" not in r for r in records)


class TestFieldTransforms:
    """Tests for field transforms integration in ingestion pipeline."""

    def test_transforms_applied_before_mapping(self):
        """Test that transforms are applied using original field names before mapping."""
        record = {"email": "  USER@EXAMPLE.COM  ", "name": "Alice"}
        # Transform lowercase and trim on original field name 'email'
        field_transforms = {
            "email": [{"name": "trim"}, {"name": "lowercase"}]
        }
        # Mapping renames 'email' to 'user_email'
        field_mappings = {"email": "user_email"}

        result = apply_field_mappings(
            record, field_mappings, [], field_transforms=field_transforms
        )

        # Value should be transformed AND renamed
        assert "user_email" in result
        assert result["user_email"] == "user@example.com"
        assert "email" not in result

    def test_transform_with_options(self):
        """Test transform with options (e.g., truncate with max_length)."""
        record = {"message": "This is a very long message that should be truncated"}
        field_transforms = {
            "message": [{"name": "truncate", "max_length": 10}]
        }

        result = apply_field_mappings(record, {}, [], field_transforms=field_transforms)

        assert result["message"] == "This is a "

    def test_multiple_transforms_in_sequence(self):
        """Test multiple transforms applied in sequence."""
        record = {"data": "  HELLO WORLD  "}
        field_transforms = {
            "data": [
                {"name": "trim"},
                {"name": "lowercase"},
                {"name": "truncate", "max_length": 5}
            ]
        }

        result = apply_field_mappings(record, {}, [], field_transforms=field_transforms)

        # trim -> "HELLO WORLD", lowercase -> "hello world", truncate -> "hello"
        assert result["data"] == "hello"

    def test_field_without_transforms_unchanged(self):
        """Test that fields without transforms remain unchanged."""
        record = {"name": "Alice", "email": "ALICE@EXAMPLE.COM"}
        field_transforms = {
            "email": [{"name": "lowercase"}]
        }

        result = apply_field_mappings(record, {}, [], field_transforms=field_transforms)

        assert result["name"] == "Alice"  # Unchanged
        assert result["email"] == "alice@example.com"  # Transformed

    def test_empty_transforms_list(self):
        """Test that empty transforms list has no effect."""
        record = {"name": "Alice"}
        field_transforms = {"name": []}

        result = apply_field_mappings(record, {}, [], field_transforms=field_transforms)

        assert result["name"] == "Alice"

    def test_no_transforms_parameter(self):
        """Test that missing field_transforms parameter works."""
        record = {"name": "Alice", "age": 30}
        result = apply_field_mappings(record, {}, [])
        assert result == {"name": "Alice", "age": 30}

    @patch("app.services.ingestion.bulk_index")
    def test_ingest_file_with_transforms(self, mock_bulk_index, json_array_file):
        """Test that ingest_file passes transforms to apply_field_mappings."""
        mock_bulk_index.return_value = {"success": 3, "failed": []}

        # Transform names to uppercase
        field_transforms = {
            "name": [{"name": "uppercase"}]
        }

        result = ingest_file(
            file_path=json_array_file,
            file_format="json_array",
            index_name="shipit-test",
            field_transforms=field_transforms,
        )

        assert result.processed == 3
        # Check that transforms were applied
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all(r["name"].isupper() for r in records)
        assert records[0]["name"] == "ALICE"


class TestGeoIPIntegration:
    """Tests for GeoIP integration in ingestion pipeline."""

    def test_geoip_enrichment_adds_geo_field(self):
        """GeoIP enrichment should add _geo field."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        # Mock GeoIP as available and returning data
        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            mock_enrich.return_value = {
                "country_name": "United States",
                "city_name": "San Francisco",
                "location": {"lat": 37.77, "lon": -122.41}
            }

            result = apply_field_mappings(
                {"src_ip": "8.8.8.8", "message": "test"},
                {},  # no mappings
                [],  # no exclusions
                geoip_fields=["src_ip"]
            )

            assert "src_ip" in result
            assert "src_ip_geo" in result
            assert result["src_ip_geo"]["country_name"] == "United States"

    def test_geoip_enrichment_respects_field_mapping(self):
        """GeoIP enrichment should use mapped field name for _geo suffix."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            mock_enrich.return_value = {"country_name": "US"}

            result = apply_field_mappings(
                {"client_ip": "8.8.8.8"},
                {"client_ip": "source.ip"},  # mapping
                [],
                geoip_fields=["client_ip"]
            )

            # Should use mapped name for geo field
            assert "source.ip_geo" in result
            assert "source.ip" in result
            assert "client_ip" not in result

    def test_geoip_enrichment_skipped_when_not_in_list(self):
        """GeoIP enrichment should only apply to fields in geoip_fields."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            result = apply_field_mappings(
                {"ip": "8.8.8.8"},
                {},
                [],
                geoip_fields=[]  # Empty list
            )

            mock_enrich.assert_not_called()
            assert "ip_geo" not in result

    def test_geoip_enrichment_skipped_when_none(self):
        """GeoIP enrichment should be skipped when geoip_fields is None."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            result = apply_field_mappings(
                {"ip": "8.8.8.8"},
                {},
                [],
                geoip_fields=None
            )

            mock_enrich.assert_not_called()
            assert "ip_geo" not in result

    def test_geoip_enrichment_skipped_for_none_value(self):
        """GeoIP enrichment should not add _geo field when value is None."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            result = apply_field_mappings(
                {"src_ip": None, "message": "test"},
                {},
                [],
                geoip_fields=["src_ip"]
            )

            mock_enrich.assert_not_called()
            assert "src_ip_geo" not in result

    def test_geoip_enrichment_skipped_when_enrich_returns_none(self):
        """GeoIP enrichment should not add _geo field when enrich_ip returns None."""
        from unittest.mock import patch
        from app.services.ingestion import apply_field_mappings

        with patch('app.services.ingestion.enrich_ip') as mock_enrich:
            mock_enrich.return_value = None  # Lookup failed

            result = apply_field_mappings(
                {"src_ip": "invalid_ip"},
                {},
                [],
                geoip_fields=["src_ip"]
            )

            mock_enrich.assert_called_once_with("invalid_ip")
            assert "src_ip_geo" not in result
            assert "src_ip" in result

    @patch("app.services.ingestion.bulk_index")
    @patch("app.services.ingestion.enrich_ip")
    def test_ingest_file_with_geoip_fields(self, mock_enrich, mock_bulk_index, json_array_file, temp_dir):
        """Test that ingest_file passes geoip_fields to apply_field_mappings."""
        import json

        # Create a test file with IP addresses
        file_path = temp_dir / "ip_test.json"
        data = [
            {"src_ip": "8.8.8.8", "message": "test1"},
            {"src_ip": "1.1.1.1", "message": "test2"},
        ]
        file_path.write_text(json.dumps(data))

        mock_bulk_index.return_value = {"success": 2, "failed": []}
        mock_enrich.return_value = {"country_name": "US", "city_name": "Test"}

        result = ingest_file(
            file_path=file_path,
            file_format="json_array",
            index_name="shipit-test",
            geoip_fields=["src_ip"],
        )

        assert result.processed == 2
        # Check that GeoIP enrichment was applied
        call_args = mock_bulk_index.call_args
        records = call_args[0][1]
        assert all("src_ip_geo" in r for r in records)
        assert records[0]["src_ip_geo"]["country_name"] == "US"
