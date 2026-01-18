from __future__ import annotations

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
from app.services.transforms import apply_transforms


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


def coerce_value(value: Any, target_type: str) -> Any:
    """Coerce a value to the target type. Returns None on failure."""
    if value is None or value == "":
        return None

    try:
        if target_type == "integer":
            if isinstance(value, bool):
                return 1 if value else 0
            return int(float(value))  # float() first handles "1.0" -> 1

        elif target_type == "float":
            return float(value)

        elif target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            # String handling
            lower = str(value).lower().strip()
            if lower in ("true", "1", "yes", "on"):
                return True
            if lower in ("false", "0", "no", "off", ""):
                return False
            return None  # Unparseable

        elif target_type == "string":
            return str(value)

        else:
            return value  # Unknown type, keep as-is
    except (ValueError, TypeError):
        return None


def merge_multiline(
    lines: Iterator[str],
    start_pattern: str | re.Pattern,
    max_lines: int = 100,
    separator: str = "\n",
) -> Iterator[str]:
    """Merge lines that don't match start pattern with previous line.

    Args:
        lines: Iterator of lines to process
        start_pattern: Regex pattern (string or compiled) that marks start of new record
        max_lines: Maximum lines to merge before forcing flush
        separator: String to join merged lines

    Yields:
        Merged lines where continuation lines are joined to previous

    Note:
        Uses safe_regex_match with timeout protection against ReDoS attacks.
    """
    from app.services.grok_patterns import safe_regex_match, RegexTimeoutError

    # Pre-compile pattern if string (validated upstream)
    if isinstance(start_pattern, str):
        compiled = re.compile(start_pattern)
    else:
        compiled = start_pattern

    buffer: list[str] = []

    for line in lines:
        line = line.rstrip('\n\r')

        try:
            # Use safe_regex_match with timeout protection against ReDoS
            match = safe_regex_match(compiled, line, timeout=1.0)
            is_start = match is not None
        except RegexTimeoutError:
            # If regex times out, treat as non-matching (continuation line)
            is_start = False

        if is_start:
            # New record starts - flush buffer
            if buffer:
                yield separator.join(buffer)
            buffer = [line]
        else:
            # Continuation line
            buffer.append(line)
            if len(buffer) > max_lines:
                # Safety limit reached - flush
                yield separator.join(buffer)
                buffer = []

    # Flush remaining buffer
    if buffer:
        yield separator.join(buffer)


def apply_field_mappings(
    record: dict[str, Any],
    field_mappings: dict[str, str],
    excluded_fields: list[str],
    timestamp_field: str | None = None,
    field_types: dict[str, str] | None = None,
    field_transforms: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Apply field mappings, exclusions, type coercion, and timestamp processing to a record."""
    result = {}

    for key, value in record.items():
        if key in excluded_fields:
            continue

        # Apply transforms BEFORE mapping (transforms use original field names)
        if field_transforms and key in field_transforms:
            value = apply_transforms(value, field_transforms[key])

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

    # Apply type coercion (uses original field names as keys)
    if field_types:
        for original_name, target_type in field_types.items():
            # Get the mapped name for this field
            mapped_name = field_mappings.get(original_name, original_name)
            if mapped_name in result:
                result[mapped_name] = coerce_value(result[mapped_name], target_type)

    return result


def _stream_with_pattern(
    file_path: Path,
    pattern: dict,
) -> Iterator[dict[str, Any]]:
    """Stream records parsed with regex/grok pattern."""
    from app.services.grok_patterns import expand_grok, safe_regex_match

    if pattern["type"] == "grok":
        regex_str = expand_grok(pattern["pattern"])
    else:
        regex_str = pattern["pattern"]

    compiled = re.compile(regex_str)

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip('\n\r')
            if not line:
                continue

            match = safe_regex_match(compiled, line)
            if match and match.groupdict():
                yield match.groupdict()
            else:
                yield {"raw_message": line}


def stream_records(
    file_path: Path,
    file_format: str,
    pattern: dict | None = None,
    multiline_start: str | None = None,
    multiline_max_lines: int = 100,
) -> Iterator[dict[str, Any]]:
    """Stream records from a file, optionally using custom pattern."""
    safe_path = _validate_file_path(file_path)

    # For formats that work with raw lines, apply multiline merging if configured
    if multiline_start and file_format in ("raw", "logfmt", "custom"):
        # Read lines, merge multiline, then parse
        with open(safe_path, "r", encoding="utf-8") as f:
            merged_lines = merge_multiline(
                (line for line in f),
                multiline_start,
                multiline_max_lines
            )

            if file_format == "custom" and pattern:
                # Parse merged lines with pattern
                from app.services.grok_patterns import expand_grok, safe_regex_match

                if pattern["type"] == "grok":
                    regex_str = expand_grok(pattern["pattern"])
                else:
                    regex_str = pattern["pattern"]
                compiled = re.compile(regex_str)

                for line in merged_lines:
                    match = safe_regex_match(compiled, line)
                    if match and match.groupdict():
                        yield match.groupdict()
                    else:
                        yield {"raw_message": line}
            elif file_format == "logfmt":
                for line in merged_lines:
                    record = {}
                    pattern_logfmt = r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))'
                    for m in re.finditer(pattern_logfmt, line):
                        key = m.group(1)
                        value = m.group(2) or m.group(3) or m.group(4)
                        record[key] = value
                    if record:
                        yield record
                    else:
                        yield {"raw_message": line}
            else:  # raw
                for line in merged_lines:
                    yield {"raw_message": line}
        return  # Important: return here to skip the normal processing

    if file_format == "custom" and pattern:
        yield from _stream_with_pattern(safe_path, pattern)
    elif file_format == "json_array":
        yield from _stream_json_array(safe_path)
    elif file_format == "ndjson":
        yield from _stream_ndjson(safe_path)
    elif file_format == "tsv":
        yield from _stream_tsv(safe_path)
    elif file_format == "ltsv":
        yield from _stream_ltsv(safe_path)
    elif file_format == "syslog":
        yield from _stream_syslog(safe_path)
    elif file_format == "logfmt":
        yield from _stream_logfmt(safe_path)
    elif file_format == "raw":
        yield from _stream_raw(safe_path)
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


# Logfmt pattern: key=value, key="quoted", key='quoted'
_LOGFMT_PATTERN = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))')


def _stream_logfmt(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from a logfmt file."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = {}
            for match in _LOGFMT_PATTERN.finditer(line):
                key = match.group(1)
                # Value is in group 2 (double-quoted), 3 (single-quoted), or 4 (unquoted)
                value = match.group(2) or match.group(3) or match.group(4)
                record[key] = value

            if record:
                yield record


def _stream_raw(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from a raw file - each line as raw_message."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            yield {"raw_message": line.rstrip('\n\r')}


def count_records(
    file_path: Path,
    file_format: str,
    pattern: dict | None = None,
    multiline_start: str | None = None,
    multiline_max_lines: int = 100,
) -> int:
    """Count total records in a file."""
    count = 0
    for _ in stream_records(file_path, file_format, pattern, multiline_start, multiline_max_lines):
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
    field_types: dict[str, str] | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    include_filename: bool = False,
    filename_field: str = "source_file",
    pattern: dict | None = None,
    multiline_start: str | None = None,
    multiline_max_lines: int = 100,
    field_transforms: dict[str, list[dict]] | None = None,
) -> IngestionResult:
    """
    Ingest a file into OpenSearch.

    Args:
        file_path: Path to the file to ingest
        file_format: Format of the file (json_array, ndjson, csv, custom)
        index_name: Full index name (with prefix already applied)
        field_mappings: Optional dict mapping original field names to new names
        excluded_fields: Optional list of fields to exclude
        timestamp_field: Optional field to parse as timestamp and map to @timestamp
        field_types: Optional dict mapping original field names to target types for coercion
        progress_callback: Optional callback(processed, success, failed) for progress updates
        include_filename: Whether to add source filename to each record
        filename_field: Name of the field to use for filename (default: _source_file)
        pattern: Optional pattern dict for custom format parsing
        multiline_start: Optional regex pattern marking the start of a new record
        multiline_max_lines: Maximum lines to merge before forcing flush (default: 100)
        field_transforms: Optional dict mapping field names to list of transforms to apply

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

    for record in stream_records(file_path, file_format, pattern, multiline_start, multiline_max_lines):
        # Add source filename if requested
        if include_filename:
            record[filename_field] = file_path.name

        # Apply field mappings, timestamp processing, type coercion, and transforms
        mapped_record = apply_field_mappings(
            record, field_mappings, excluded_fields, timestamp_field, field_types, field_transforms
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
