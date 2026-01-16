
from typing import Any, Literal

from pydantic import BaseModel


class FieldInfo(BaseModel):
    name: str
    type: str


class UploadResponse(BaseModel):
    upload_id: str
    filename: str  # Display name (comma-separated if multiple)
    filenames: list[str] = []  # Individual filenames
    file_size: int  # Total size
    file_format: Literal["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog"]
    preview: list[dict[str, Any]]
    fields: list[FieldInfo]


class PreviewResponse(BaseModel):
    upload_id: str
    filename: str
    file_format: Literal["json_array", "ndjson", "csv", "tsv", "ltsv", "syslog"]
    preview: list[dict[str, Any]]
    fields: list[FieldInfo]


class IngestRequest(BaseModel):
    index_name: str
    timestamp_field: str | None = None
    field_mappings: dict[str, str] = {}
    excluded_fields: list[str] = []
    include_filename: bool = False
    filename_field: str = "source_file"


class IngestResponse(BaseModel):
    upload_id: str
    index_name: str
    processed: int
    success: int
    failed: int
