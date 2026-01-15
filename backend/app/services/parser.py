import csv
import json
import re
from pathlib import Path
from typing import Literal

import ijson

FileFormat = Literal["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog"]


def detect_format(file_path: Path) -> FileFormat:
    """Detect file format based on extension and content."""
    ext = file_path.suffix.lower()

    # Extension-based detection
    if ext == '.tsv':
        return "tsv"
    if ext == '.ltsv':
        return "ltsv"
    if ext == '.log':
        # Check for syslog pattern (starts with <priority>)
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if first_line.startswith('<') and '>' in first_line[:5]:
                return "syslog"
        return "csv"  # Default for .log if not syslog

    # Content-based detection (existing logic)
    with open(file_path, "r", encoding="utf-8") as f:
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
            return "csv"


def parse_preview(file_path: Path, format: FileFormat, limit: int = 100) -> list[dict]:
    """Parse first N records from file for preview."""
    if format == "json_array":
        return _parse_json_array(file_path, limit)
    elif format == "ndjson":
        return _parse_ndjson(file_path, limit)
    elif format == "tsv":
        return _parse_tsv(file_path, limit)
    elif format == "ltsv":
        return _parse_ltsv(file_path, limit)
    elif format == "syslog":
        return _parse_syslog(file_path, limit)
    else:
        return _parse_csv(file_path, limit)


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
    """Parse CSV with auto-detected delimiter."""
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
        for row in reader:
            records.append(dict(row))
            if len(records) >= limit:
                break
        return records


def _parse_tsv(file_path: Path, limit: int) -> list[dict]:
    """Parse tab-separated values."""
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter='\t')
        records = []
        for row in reader:
            records.append(dict(row))
            if len(records) >= limit:
                break
        return records


def _parse_ltsv(file_path: Path, limit: int) -> list[dict]:
    """Parse Labeled Tab-separated Values (key:value pairs separated by tabs)."""
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = {}
            for pair in line.split('\t'):
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    record[key] = value

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


def infer_fields(records: list[dict]) -> list[dict]:
    """Infer field names and types from records."""
    if not records:
        return []

    # Collect all unique field names preserving order from first record
    field_names = list(records[0].keys())
    seen = set(field_names)

    # Add any additional fields from other records
    for record in records[1:]:
        for key in record.keys():
            if key not in seen:
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
