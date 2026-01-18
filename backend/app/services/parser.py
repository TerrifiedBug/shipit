from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Literal

import ijson

from app.config import settings

FileFormat = Literal["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog", "logfmt", "raw"]


class FormatValidationError(Exception):
    """Raised when file content doesn't match selected format."""

    def __init__(self, message: str, suggested_formats: list[str] | None = None):
        self.message = message
        self.suggested_formats = suggested_formats or []
        super().__init__(message)


def _validate_file_path(file_path: Path) -> Path:
    """Validate file path is within allowed data directory.

    Prevents path traversal attacks by ensuring the resolved path
    is under the configured data directory.
    """
    # Resolve to absolute path (resolves symlinks and ..)
    resolved = file_path.resolve()
    allowed_dir = Path(settings.data_dir).resolve()

    # Check path is under allowed directory
    try:
        resolved.relative_to(allowed_dir)
    except ValueError:
        raise ValueError(f"Access denied: path outside allowed directory")

    return resolved


def detect_format(file_path: Path) -> FileFormat:
    """Detect file format based on extension and content."""
    safe_path = _validate_file_path(file_path)
    ext = safe_path.suffix.lower()

    # Extension-based detection
    if ext == '.tsv':
        return "tsv"
    if ext == '.ltsv':
        return "ltsv"
    if ext == '.log':
        with open(safe_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()

            # Check for NDJSON (starts with {)
            if first_line.startswith('{'):
                return "ndjson"

            # Check for JSON array (starts with [)
            if first_line.startswith('['):
                return "json_array"

            # Check for syslog pattern (starts with <priority>)
            if first_line.startswith('<') and '>' in first_line[:5]:
                return "syslog"

            # Check for LTSV pattern (key:value pairs separated by tabs or spaces)
            # LTSV has multiple key:value pairs where key doesn't contain spaces
            if '\t' in first_line:
                pairs = first_line.split('\t')
            else:
                pairs = re.split(r'\s{2,}', first_line)

            if len(pairs) >= 2:
                # Check if most pairs look like key:value (word:something)
                ltsv_like = sum(1 for p in pairs if re.match(r'^\w+:', p))
                if ltsv_like >= len(pairs) * 0.7:  # 70% match threshold
                    return "ltsv"

            # Check for logfmt before defaulting to CSV
            f.seek(0)
            if _detect_logfmt(f):
                return "logfmt"

        return "csv"  # Default for .log if not detected as another format

    # Content-based detection (existing logic)
    with open(safe_path, "r", encoding="utf-8") as f:
        while True:
            char = f.read(1)
            if not char:
                return "csv"
            if not char.isspace():
                break

        if char == "[":
            return "json_array"
        elif char == "{":
            return "ndjson"
        else:
            # Check for logfmt pattern before falling back to CSV
            f.seek(0)
            if _detect_logfmt(f):
                return "logfmt"
            return "csv"


def _detect_logfmt(f) -> bool:
    """Detect if file content looks like logfmt (key=value pairs)."""
    # Pattern: key=value or key="quoted value" or key='quoted value'
    logfmt_pattern = re.compile(r'\b\w+=(?:"[^"]*"|\'[^\']*\'|\S+)')

    lines_checked = 0
    lines_matched = 0

    for line in f:
        line = line.strip()
        if not line:
            continue

        lines_checked += 1
        if lines_checked > 20:  # Check first 20 non-empty lines
            break

        # Count key=value pairs in the line
        matches = logfmt_pattern.findall(line)
        if len(matches) >= 2:  # At least 2 key=value pairs
            lines_matched += 1

    # Return True if at least 70% of lines match logfmt pattern
    if lines_checked == 0:
        return False
    return lines_matched / lines_checked >= 0.7


def parse_preview(
    file_path: Path,
    format: FileFormat,
    limit: int = 100,
    multiline_start: str | None = None,
    multiline_max_lines: int = 100,
) -> list[dict]:
    """Parse first N records from file for preview."""
    safe_path = _validate_file_path(file_path)

    # Apply multiline merging first for supported formats
    if multiline_start and format in ("raw", "logfmt"):
        from app.services.ingestion import merge_multiline

        with open(safe_path, "r", encoding="utf-8") as f:
            merged = list(merge_multiline(f, multiline_start, multiline_max_lines))

        # Then parse merged lines
        if format == "raw":
            return [{"raw_message": line} for line in merged[:limit]]
        elif format == "logfmt":
            return [_parse_logfmt_record(line) for line in merged[:limit]]

    if format == "json_array":
        return _parse_json_array(safe_path, limit)
    elif format == "ndjson":
        return _parse_ndjson(safe_path, limit)
    elif format == "tsv":
        return _parse_tsv(safe_path, limit)
    elif format == "ltsv":
        return _parse_ltsv(safe_path, limit)
    elif format == "syslog":
        return _parse_syslog(safe_path, limit)
    elif format == "logfmt":
        return _parse_logfmt(safe_path, limit)
    elif format == "raw":
        return _parse_raw(safe_path, limit)
    else:
        return _parse_csv(safe_path, limit)


def _parse_json_array(file_path: Path, limit: int) -> list[dict]:
    """Parse JSON array using ijson for streaming."""
    records = []
    with open(file_path, "rb") as f:
        for item in ijson.items(f, "item"):
            records.append(item)
            if len(records) >= limit:
                break
    return records


def _parse_ndjson(file_path: Path, limit: int) -> list[dict]:
    """Parse newline-delimited JSON."""
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
            if len(records) >= limit:
                break
    return records


def _parse_csv(file_path: Path, limit: int) -> list[dict]:
    """Parse CSV with auto-detected delimiter.

    Raises ValueError if content doesn't look like valid CSV.
    """
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        # Sniff delimiter from first 8KB
        sample = f.read(8192)
        f.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            # Default to comma if sniffing fails
            dialect = csv.excel

        reader = csv.DictReader(f, dialect=dialect)
        records = []
        fieldnames = reader.fieldnames or []

        # Validate: CSV should have multiple columns, or if single column,
        # the header should be a reasonable field name (not a long log line)
        if len(fieldnames) == 1:
            header = fieldnames[0]
            # If the "header" is very long or contains multiple spaces,
            # it's likely a log line, not a CSV header
            if len(header) > 50 or header.count(' ') > 3:
                raise ValueError(
                    "Content doesn't appear to be valid CSV. "
                    "Single-column detected with log-like content. "
                    "Try 'Raw Lines' or 'Logfmt' format instead."
                )

        for row in reader:
            records.append(dict(row))
            if len(records) >= limit:
                break
        return records


def _parse_tsv(file_path: Path, limit: int) -> list[dict]:
    """Parse tab-separated values.

    Handles both actual tabs and multiple spaces as delimiters.
    Raises ValueError if content doesn't look like valid TSV.
    """
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        # Read first line to detect delimiter
        first_line = f.readline()
        f.seek(0)

        # Check if actual tabs exist
        if '\t' in first_line:
            reader = csv.DictReader(f, delimiter='\t')
            fieldnames = reader.fieldnames or []

            # Validate: TSV should have multiple columns
            if len(fieldnames) == 1:
                header = fieldnames[0]
                if len(header) > 50 or header.count(' ') > 3:
                    raise ValueError(
                        "Content doesn't appear to be valid TSV. "
                        "No tab delimiters found. "
                        "Try 'Raw Lines' or 'Logfmt' format instead."
                    )

            records = []
            for row in reader:
                records.append(dict(row))
                if len(records) >= limit:
                    break
            return records
        else:
            # Fall back to splitting on 2+ spaces
            lines = f.readlines()
            if not lines:
                return []

            # Parse header
            header = re.split(r'\s{2,}', lines[0].strip())

            # Validate: need multiple columns from 2+ space splitting
            if len(header) == 1:
                if len(header[0]) > 50 or header[0].count(' ') > 3:
                    raise ValueError(
                        "Content doesn't appear to be valid TSV. "
                        "No tab or multi-space delimiters found. "
                        "Try 'Raw Lines' or 'Logfmt' format instead."
                    )

            records = []
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                values = re.split(r'\s{2,}', line)
                # Pad with empty strings if fewer values than headers
                while len(values) < len(header):
                    values.append('')
                record = dict(zip(header, values[:len(header)]))
                records.append(record)
                if len(records) >= limit:
                    break
            return records


def _parse_ltsv(file_path: Path, limit: int) -> list[dict]:
    """Parse Labeled Tab-separated Values (key:value pairs separated by tabs).

    Handles both actual tabs and multiple spaces as delimiters.
    """
    records = []
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
                records.append(record)
                if len(records) >= limit:
                    break

    return records


def _parse_syslog(file_path: Path, limit: int) -> list[dict]:
    """Parse syslog format (RFC 3164 and RFC 5424)."""
    # RFC 3164: <PRI>TIMESTAMP HOSTNAME TAG: MESSAGE
    # RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG

    rfc3164_pattern = re.compile(
        r'^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+?):\s*(.*)$'
    )
    rfc5424_pattern = re.compile(
        r'^<(\d+)>(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(?:\[.*?\]\s*)?(.*)$'
    )

    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = {}

            # Try RFC 5424 first (more structured)
            match = rfc5424_pattern.match(line)
            if match:
                record = {
                    "priority": match.group(1),
                    "version": match.group(2),
                    "timestamp": match.group(3),
                    "hostname": match.group(4),
                    "app_name": match.group(5),
                    "proc_id": match.group(6),
                    "msg_id": match.group(7),
                    "message": match.group(8),
                }
            else:
                # Try RFC 3164
                match = rfc3164_pattern.match(line)
                if match:
                    record = {
                        "priority": match.group(1),
                        "timestamp": match.group(2),
                        "hostname": match.group(3),
                        "app_name": match.group(4),
                        "message": match.group(5),
                    }
                else:
                    # Fallback: just store as message
                    record = {"message": line}

            records.append(record)
            if len(records) >= limit:
                break

    return records


def _parse_logfmt_record(line: str) -> dict:
    """Parse a single logfmt line into a dict."""
    # Regex handles: key=value, key="quoted", key='quoted'
    pattern = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))')

    record = {}
    for match in pattern.finditer(line):
        key = match.group(1)
        # Value is in group 2 (double-quoted), 3 (single-quoted), or 4 (unquoted)
        value = match.group(2) or match.group(3) or match.group(4)
        record[key] = value

    # Return record if we found key-value pairs, otherwise raw_message fallback
    return record if record else {"raw_message": line}


def _parse_logfmt(file_path: Path, limit: int) -> list[dict]:
    """Parse logfmt format: key=value key2="quoted value" ..."""
    # Regex handles: key=value, key="quoted", key='quoted'
    pattern = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))')

    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = {}
            for match in pattern.finditer(line):
                key = match.group(1)
                # Value is in group 2 (double-quoted), 3 (single-quoted), or 4 (unquoted)
                value = match.group(2) or match.group(3) or match.group(4)
                record[key] = value

            if record:
                records.append(record)
                if len(records) >= limit:
                    break

    return records


def _parse_raw(file_path: Path, limit: int) -> list[dict]:
    """Fallback parser - each line becomes a record with raw_message field."""
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip('\n\r')
            records.append({"raw_message": line})
            if len(records) >= limit:
                break
    return records


def parse_with_pattern(
    file_path: Path,
    pattern: dict,
    limit: int = 100
) -> list[dict]:
    """Parse file line-by-line using regex or grok pattern.

    Non-matching lines fallback to {"raw_message": line}.
    """
    from app.services.grok_patterns import expand_grok, safe_regex_match

    safe_path = _validate_file_path(file_path)

    # Get regex (expand if grok)
    if pattern["type"] == "grok":
        regex_str = expand_grok(pattern["pattern"])
    else:
        regex_str = pattern["pattern"]

    try:
        compiled = re.compile(regex_str)
    except re.error as e:
        raise ValueError(f"Invalid pattern: {e}")

    records = []
    with open(safe_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip('\n\r')
            if not line:
                continue

            match = safe_regex_match(compiled, line)
            if match and match.groupdict():
                # Pattern matched — use captured groups
                records.append(match.groupdict())
            else:
                # No match — fallback to raw
                records.append({"raw_message": line})

            if len(records) >= limit:
                break

    return records


def infer_fields(records: list[dict]) -> list[dict]:
    """Infer field names and types from records."""
    if not records:
        return []

    # Collect all unique field names preserving order from first record
    # Filter out None and empty string keys (can occur with malformed CSV)
    field_names = [k for k in records[0].keys() if k is not None and k != ""]
    seen = set(field_names)

    # Add any additional fields from other records
    for record in records[1:]:
        for key in record.keys():
            if key is not None and key != "" and key not in seen:
                field_names.append(key)
                seen.add(key)

    # Infer types by sampling values
    fields = []
    for name in field_names:
        field_type = _infer_type(name, records)
        fields.append({"name": name, "type": field_type})

    return fields


def _infer_type(field_name: str, records: list[dict]) -> str:
    """Infer the type of a field by examining sample values."""
    # Collect non-null values
    values = []
    for record in records[:100]:  # Sample first 100
        value = record.get(field_name)
        if value is not None and value != "":
            values.append(value)

    if not values:
        return "string"

    # Check if all values are of the same type
    types_seen = set()
    for value in values:
        if isinstance(value, bool):
            types_seen.add("boolean")
        elif isinstance(value, int):
            types_seen.add("integer")
        elif isinstance(value, float):
            types_seen.add("float")
        elif isinstance(value, dict):
            types_seen.add("object")
        elif isinstance(value, list):
            types_seen.add("array")
        elif isinstance(value, str):
            # Try to detect if string looks like a date/number
            types_seen.add(_infer_string_type(value))
        else:
            types_seen.add("string")

    # If mixed types or multiple types, default to string
    if len(types_seen) == 1:
        return types_seen.pop()
    elif types_seen == {"integer", "float"}:
        return "float"
    else:
        return "string"


def _infer_string_type(value: str) -> str:
    """Try to infer a more specific type from a string value."""
    # Try integer
    try:
        int(value)
        return "integer"
    except ValueError:
        pass

    # Try float
    try:
        float(value)
        return "float"
    except ValueError:
        pass

    # Could add date detection here in the future
    return "string"


def count_fields(record: dict, prefix: str = "") -> int:
    """Count all fields in a record, including nested fields.

    Nested objects are flattened with dot notation for counting.
    For example: {"a": {"b": 1, "c": 2}} counts as 2 fields (a.b, a.c).

    Arrays count as 1 field regardless of content.
    """
    count = 0
    for key, value in record.items():
        if isinstance(value, dict):
            # Recursively count nested fields
            count += count_fields(value, f"{prefix}{key}.")
        else:
            # Leaf field (including arrays)
            count += 1
    return count


def validate_field_count(records: list[dict], max_fields: int) -> tuple[bool, int]:
    """Validate that no record exceeds the maximum field count.

    Args:
        records: List of parsed records to validate
        max_fields: Maximum allowed fields per document (0 = disabled)

    Returns:
        (is_valid, max_found) - True if all records are valid, plus the max field count found
    """
    if max_fields == 0:
        return True, 0

    max_found = 0
    for record in records:
        field_count = count_fields(record)
        max_found = max(max_found, field_count)
        if field_count > max_fields:
            return False, field_count

    return True, max_found


def _validate_json_array(file_path: Path) -> None:
    """Validate file is a JSON array."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read(8192).lstrip()

        if not content:
            raise FormatValidationError("File is empty", suggested_formats=[])

        if not content.startswith("["):
            raise FormatValidationError(
                "File is not a JSON array - must start with '['. Try: NDJSON",
                suggested_formats=["ndjson"]
            )

        # Try to parse
        f.seek(0)
        try:
            json.load(f)
        except json.JSONDecodeError as e:
            raise FormatValidationError(
                f"File is not valid JSON: {e}. Try: NDJSON or Raw",
                suggested_formats=["ndjson", "raw"]
            )


def _validate_ndjson(file_path: Path) -> None:
    """Validate file is NDJSON (newline-delimited JSON)."""
    with open(file_path, "r", encoding="utf-8") as f:
        valid_lines = 0
        invalid_lines = 0

        for i, line in enumerate(f):
            if i >= 5:  # Check first 5 lines
                break

            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    invalid_lines += 1
                else:
                    valid_lines += 1
            except json.JSONDecodeError:
                invalid_lines += 1

        if valid_lines == 0:
            raise FormatValidationError(
                "Lines are not valid JSON objects. Try: Raw or Logfmt",
                suggested_formats=["raw", "logfmt"]
            )

        if invalid_lines > valid_lines:
            raise FormatValidationError(
                f"Most lines are not valid JSON ({invalid_lines}/{valid_lines + invalid_lines}). Try: Raw or Logfmt",
                suggested_formats=["raw", "logfmt"]
            )


def _validate_csv(file_path: Path) -> None:
    """Validate file looks like CSV with header row."""
    with open(file_path, "r", encoding="utf-8") as f:
        # Read sample
        sample = f.read(8192)
        if not sample.strip():
            raise FormatValidationError(
                "File is empty",
                suggested_formats=[]
            )

        f.seek(0)

        # Try to detect delimiter
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            raise FormatValidationError(
                "File doesn't appear to be CSV - no consistent delimiter detected. Try: Raw or Logfmt",
                suggested_formats=["raw", "logfmt"]
            )

        # Check column consistency
        f.seek(0)
        reader = csv.reader(f, dialect=dialect)
        rows = []
        for i, row in enumerate(reader):
            if i >= 5:  # Check first 5 rows
                break
            rows.append(row)

        if len(rows) < 2:
            raise FormatValidationError(
                "File doesn't appear to be CSV - no data rows found. Try: Raw",
                suggested_formats=["raw"]
            )

        header_len = len(rows[0])
        for i, row in enumerate(rows[1:], 1):
            if len(row) != header_len:
                raise FormatValidationError(
                    f"File doesn't appear to be CSV - row {i+1} has {len(row)} columns but header has {header_len}. Try: Raw or Logfmt",
                    suggested_formats=["raw", "logfmt"]
                )


def validate_format(file_path: Path, file_format: str) -> None:
    """Validate file content matches the selected format.

    Raises FormatValidationError with suggestions if mismatch.
    """
    validators = {
        "csv": _validate_csv,
        "json_array": _validate_json_array,
        "ndjson": _validate_ndjson,
    }

    validator = validators.get(file_format)
    if validator:
        validator(file_path)
