from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


# Supported file formats for parsing
FileFormat = Literal["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog", "logfmt", "raw"]


class FieldInfo(BaseModel):
    name: str
    type: str


class UploadResponse(BaseModel):
    upload_id: str
    filename: str  # Display name (comma-separated if multiple)
    filenames: list[str] = []  # Individual filenames
    file_size: int  # Total size
    file_format: FileFormat
    preview: list[dict[str, Any]]
    fields: list[FieldInfo]
    raw_preview: list[str] = []  # Raw lines for pattern testing


class PreviewResponse(BaseModel):
    upload_id: str
    filename: str
    file_format: FileFormat
    preview: list[dict[str, Any]]
    fields: list[FieldInfo]
    raw_preview: list[str] = []  # Raw lines for pattern testing


class FieldTransform(BaseModel):
    """Configuration for a field transformation."""
    name: str
    pattern: str | None = None
    replacement: str | None = None
    path: str | None = None
    default_value: str | None = None
    max_length: int | None = None
    delimiter: str | None = None
    separator: str | None = None


class IngestRequest(BaseModel):
    index_name: str
    timestamp_field: str | None = None
    field_mappings: dict[str, str] = {}
    excluded_fields: list[str] = []
    field_types: dict[str, str] = {}
    field_transforms: dict[str, list[FieldTransform]] = {}
    include_filename: bool = False
    filename_field: str = "source_file"
    multiline_start: str | None = None
    multiline_max_lines: int = 100


class IngestResponse(BaseModel):
    upload_id: str
    index_name: str
    processed: int
    success: int
    failed: int
