import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import settings


def get_db_path() -> Path:
    """Get the path to the SQLite database file."""
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "shipit.db"


def init_db() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS uploads (
                id              TEXT PRIMARY KEY,
                filename        TEXT NOT NULL,
                file_size       INTEGER NOT NULL,
                file_format     TEXT NOT NULL,
                index_name      TEXT,
                timestamp_field TEXT,
                field_mappings  TEXT,
                excluded_fields TEXT,
                status          TEXT NOT NULL DEFAULT 'pending',
                total_records   INTEGER,
                success_count   INTEGER DEFAULT 0,
                failure_count   INTEGER DEFAULT 0,
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
        """)


@contextmanager
def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_upload(
    upload_id: str,
    filename: str,
    file_size: int,
    file_format: str,
) -> dict[str, Any]:
    """Create a new upload record."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, filename, file_size, file_format, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (upload_id, filename, file_size, file_format),
        )
    return get_upload(upload_id)


def get_upload(upload_id: str) -> Optional[dict[str, Any]]:
    """Get an upload by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM uploads WHERE id = ?",
            (upload_id,),
        ).fetchone()

    if not row:
        return None

    return _row_to_dict(row)


def update_upload(upload_id: str, **kwargs) -> Optional[dict[str, Any]]:
    """Update an upload record with the given fields."""
    if not kwargs:
        return get_upload(upload_id)

    # Handle JSON serialization for dict/list fields
    if "field_mappings" in kwargs and isinstance(kwargs["field_mappings"], dict):
        kwargs["field_mappings"] = json.dumps(kwargs["field_mappings"])
    if "excluded_fields" in kwargs and isinstance(kwargs["excluded_fields"], list):
        kwargs["excluded_fields"] = json.dumps(kwargs["excluded_fields"])

    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [upload_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE uploads SET {set_clause} WHERE id = ?",
            values,
        )

    return get_upload(upload_id)


def start_ingestion(
    upload_id: str,
    index_name: str,
    timestamp_field: Optional[str],
    field_mappings: dict[str, str],
    excluded_fields: list[str],
    total_records: int,
) -> Optional[dict[str, Any]]:
    """Mark an upload as starting ingestion."""
    return update_upload(
        upload_id,
        index_name=index_name,
        timestamp_field=timestamp_field,
        field_mappings=field_mappings,
        excluded_fields=excluded_fields,
        total_records=total_records,
        status="in_progress",
        started_at=datetime.utcnow().isoformat(),
    )


def update_progress(
    upload_id: str,
    success_count: int,
    failure_count: int,
) -> None:
    """Update ingestion progress counts."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE uploads
            SET success_count = ?, failure_count = ?
            WHERE id = ?
            """,
            (success_count, failure_count, upload_id),
        )


def complete_ingestion(
    upload_id: str,
    success_count: int,
    failure_count: int,
    error_message: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Mark an upload as completed."""
    status = "failed" if error_message else "completed"
    return update_upload(
        upload_id,
        status=status,
        success_count=success_count,
        failure_count=failure_count,
        completed_at=datetime.utcnow().isoformat(),
        error_message=error_message,
    )


def list_uploads(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List uploads with optional filtering."""
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                """
                SELECT * FROM uploads
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM uploads
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a database row to a dictionary."""
    result = dict(row)

    # Parse JSON fields
    if result.get("field_mappings"):
        try:
            result["field_mappings"] = json.loads(result["field_mappings"])
        except json.JSONDecodeError:
            result["field_mappings"] = {}

    if result.get("excluded_fields"):
        try:
            result["excluded_fields"] = json.loads(result["excluded_fields"])
        except json.JSONDecodeError:
            result["excluded_fields"] = []

    return result
