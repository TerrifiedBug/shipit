import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import ijson
from dateutil import parser as dateutil_parser

from app.config import settings
from app.services.opensearch import bulk_index


# Common date formats to try
NGINX_DATE_PATTERN = re.compile(r"(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})")
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

# Syslog patterns (compiled once at module level)
_RFC3164_PATTERN = re.compile(
    r'^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+?):\s*(.*)$'
)
_RFC5424_PATTERN = re.compile(
    r'^<(\d+)>(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(?:\[.*?\]\s*)?(.*)$'
)


def _validate_file_path(file_path: Path) -> Path:
    """Validate file path is within allowed data directory.

    Prevents path traversal attacks by ensuring the resolved path
    is under the configured data directory.
    """
    resolved = file_path.resolve()
    allowed_dir = Path(settings.data_dir).resolve()

    try:
        resolved.relative_to(allowed_dir)
    except ValueError:
        raise ValueError(f"Access denied: path outside allowed directory")

    return resolved


def parse_timestamp(value: Any) -> str | None:
    """
    Parse a timestamp value and convert to ISO8601 UTC format.

    Handles:
    - ISO8601 formats
    - Nginx/Apache CLF format: 17/May/2015:08:05:02 +0000
    - Epoch seconds (int or string)
    - Epoch milliseconds (int or string)
    - Various other date formats via dateutil

    Returns:
        ISO8601 UTC string (e.g., "2015-05-17T08:05:02Z") or None if parsing fails
    """
    if value is None or value == "":
        return None

    # Handle numeric timestamps (epoch)
    if isinstance(value, (int, float)):
        # Detect if milliseconds (> year 2100 in seconds)
        if value > 4102444800:  # Jan 1, 2100 in seconds
            value = value / 1000
        try:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            return None

    value_str = str(value).strip()

    # Try epoch as string
    if value_str.isdigit():
        try:
            epoch = int(value_str)
            if epoch > 4102444800:
                epoch = epoch / 1000
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass

    # Try nginx/apache CLF format: 17/May/2015:08:05:02 +0000
    match = NGINX_DATE_PATTERN.match(value_str)
    if match:
        day, month_str, year, hour, minute, second, tz_str = match.groups()
        month = MONTH_MAP.get(month_str)
        if month:
            try:
                # Parse timezone offset
                tz_hours = int(tz_str[:3])
                tz_mins = int(tz_str[0] + tz_str[3:5])  # Preserve sign
                tz_offset = timezone(timedelta(hours=tz_hours, minutes=tz_mins))

                dt = datetime(
                    int(year), month, int(day),
                    int(hour), int(minute), int(second),
                    tzinfo=tz_offset
                )
                # Convert to UTC
                dt_utc = dt.astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                pass

    # Try dateutil parser (handles most other formats)
    try:
        dt = dateutil_parser.parse(value_str)
        # If no timezone, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        pass

    return None


def apply_field_mappings(
    record: dict[str, Any],
    field_mappings: dict[str, str],
    excluded_fields: list[str],
    timestamp_field: str | None = None,
) -> dict[str, Any]:
    """Apply field mappings, exclusions, and timestamp processing to a record."""
    result = {}

    for key, value in record.items():
        if key in excluded_fields:
            continue

        # Apply mapping if exists, otherwise keep original name
        new_key = field_mappings.get(key, key)
        result[new_key] = value

    # Process timestamp field if specified
    if timestamp_field:
        # Get the original value (before any mapping)
        timestamp_value = record.get(timestamp_field)

        if timestamp_value is not None:
            parsed = parse_timestamp(timestamp_value)
            if parsed:
                # Set @timestamp with parsed UTC value
                result["@timestamp"] = parsed

                # Also update the original field if it's in the result
                mapped_name = field_mappings.get(timestamp_field, timestamp_field)
                if mapped_name in result:
                    result[mapped_name] = parsed

    return result


def stream_records(
    file_path: Path,
    file_format: str,
) -> Iterator[dict[str, Any]]:
    """Stream records from a file without loading all into memory."""
    safe_path = _validate_file_path(file_path)
    if file_format == "json_array":
        yield from _stream_json_array(safe_path)
    elif file_format == "ndjson":
        yield from _stream_ndjson(safe_path)
    elif file_format == "tsv":
        yield from _stream_tsv(safe_path)
    elif file_format == "ltsv":
        yield from _stream_ltsv(safe_path)
    elif file_format == "syslog":
        yield from _stream_syslog(safe_path)
    else:
        yield from _stream_csv(safe_path)


def _stream_json_array(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from a JSON array file."""
    with open(file_path, "rb") as f:
        for item in ijson.items(f, "item"):
            yield item


def _stream_ndjson(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from an NDJSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _stream_csv(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from a CSV file."""
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(f, dialect=dialect)
        for row in reader:
            yield dict(row)


def _stream_tsv(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from TSV file.

    Handles both actual tabs and multiple spaces as delimiters.
    """
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        first_line = f.readline()
        f.seek(0)

        if '\t' in first_line:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                yield dict(row)
        else:
            # Fall back to splitting on 2+ spaces
            lines = f.readlines()
            if not lines:
                return

            header = re.split(r'\s{2,}', lines[0].strip())
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                values = re.split(r'\s{2,}', line)
                while len(values) < len(header):
                    values.append('')
                yield dict(zip(header, values[:len(header)]))


def _stream_ltsv(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from LTSV file (key:value pairs separated by tabs).

    Handles both actual tabs and multiple spaces as delimiters.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Detect delimiter: tabs or multiple spaces
            if '\t' in line:
                pairs = line.split('\t')
            else:
                pairs = re.split(r'\s{2,}', line)

            record = {}
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    record[key.strip()] = value.strip()
            if record:
                yield record


def _stream_syslog(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from syslog file (RFC 3164 and RFC 5424)."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Try RFC 5424 first
            match = _RFC5424_PATTERN.match(line)
            if match:
                yield {
                    "priority": match.group(1),
                    "version": match.group(2),
                    "timestamp": match.group(3),
                    "hostname": match.group(4),
                    "app_name": match.group(5),
                    "proc_id": match.group(6),
                    "msg_id": match.group(7),
                    "message": match.group(8),
                }
                continue

            # Try RFC 3164
            match = _RFC3164_PATTERN.match(line)
            if match:
                yield {
                    "priority": match.group(1),
                    "timestamp": match.group(2),
                    "hostname": match.group(3),
                    "app_name": match.group(4),
                    "message": match.group(5),
                }
                continue

            # Fallback
            yield {"message": line}


def count_records(file_path: Path, file_format: str) -> int:
    """Count total records in a file."""
    count = 0
    for _ in stream_records(file_path, file_format):
        count += 1
    return count


class IngestionResult:
    """Result of an ingestion operation."""

    def __init__(self):
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.failed_records: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "failed_records": self.failed_records,
        }


def ingest_file(
    file_path: Path,
    file_format: str,
    index_name: str,
    field_mappings: dict[str, str] | None = None,
    excluded_fields: list[str] | None = None,
    timestamp_field: str | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    include_filename: bool = False,
    filename_field: str = "source_file",
) -> IngestionResult:
    """
    Ingest a file into OpenSearch.

    Args:
        file_path: Path to the file to ingest
        file_format: Format of the file (json_array, ndjson, csv)
        index_name: Full index name (with prefix already applied)
        field_mappings: Optional dict mapping original field names to new names
        excluded_fields: Optional list of fields to exclude
        timestamp_field: Optional field to parse as timestamp and map to @timestamp
        progress_callback: Optional callback(processed, success, failed) for progress updates
        include_filename: Whether to add source filename to each record
        filename_field: Name of the field to use for filename (default: _source_file)

    Returns:
        IngestionResult with counts and any failed records
    """
    field_mappings = field_mappings or {}
    excluded_fields = excluded_fields or []

    result = IngestionResult()
    batch: list[dict] = []

    # Get failures directory
    failures_dir = Path(settings.data_dir) / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)

    for record in stream_records(file_path, file_format):
        # Add source filename if requested
        if include_filename:
            record[filename_field] = file_path.name

        # Apply field mappings and timestamp processing
        mapped_record = apply_field_mappings(
            record, field_mappings, excluded_fields, timestamp_field
        )
        batch.append(mapped_record)

        if len(batch) >= settings.bulk_batch_size:
            # Flush batch
            _flush_batch(batch, index_name, result)
            batch = []

            if progress_callback:
                progress_callback(result.processed, result.success, result.failed)

    # Flush remaining records
    if batch:
        _flush_batch(batch, index_name, result)
        if progress_callback:
            progress_callback(result.processed, result.success, result.failed)

    return result


def _flush_batch(
    batch: list[dict],
    index_name: str,
    result: IngestionResult,
) -> None:
    """Flush a batch of records to OpenSearch."""
    bulk_result = bulk_index(index_name, batch)

    result.processed += len(batch)
    result.success += bulk_result["success"]
    result.failed += len(bulk_result["failed"])
    result.failed_records.extend(bulk_result["failed"])
