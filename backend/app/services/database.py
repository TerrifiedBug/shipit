import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.config import settings


def get_db_path() -> Path:
    """Get the path to the SQLite database file."""
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "shipit.db"


def _init_uploads_table(conn: sqlite3.Connection) -> None:
    """Create uploads table."""
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
            error_message   TEXT,
            user_id         TEXT REFERENCES users(id),
            index_deleted   INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
    """)
    # Migration: add index_deleted column if it doesn't exist
    try:
        conn.execute("ALTER TABLE uploads ADD COLUMN index_deleted INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _init_users_table(conn: sqlite3.Connection) -> None:
    """Create users table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            auth_type TEXT NOT NULL,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            password_change_required INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            deleted_at TIMESTAMP
        )
    """)
    # Migration: add new columns if they don't exist
    for column, definition in [
        ("password_change_required", "INTEGER DEFAULT 0"),
        ("deleted_at", "TIMESTAMP"),
        ("is_active", "INTEGER DEFAULT 1"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def _init_api_keys_table(conn: sqlite3.Connection) -> None:
    """Create api_keys table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP
        )
    """)


def _init_audit_log_table(conn: sqlite3.Connection) -> None:
    """Create audit_log table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            action TEXT NOT NULL,
            target TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def init_db() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        _init_uploads_table(conn)
        _init_users_table(conn)
        _init_api_keys_table(conn)
        _init_audit_log_table(conn)


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
    filenames: list[str],
    file_sizes: list[int],
    file_format: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create a new upload record for one or more files."""
    # Store filenames as JSON array, total size
    filename_json = json.dumps(filenames)
    total_size = sum(file_sizes)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, filename, file_size, file_format, status, user_id)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (upload_id, filename_json, total_size, file_format, user_id),
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


def mark_index_deleted(index_name: str) -> int:
    """Mark index as deleted for all uploads that used this index. Returns count of updated rows."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE uploads SET index_deleted = 1 WHERE index_name = ?",
            (index_name,),
        )
        return cursor.rowcount


def delete_pending_upload(upload_id: str) -> bool:
    """Delete a pending upload record. Only allows deletion of pending uploads."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM uploads WHERE id = ? AND status = 'pending'",
            (upload_id,),
        )
        return cursor.rowcount > 0


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
    """List uploads with optional filtering, including user info."""
    with get_connection() as conn:
        base_query = """
            SELECT uploads.*, users.name as user_name, users.email as user_email
            FROM uploads
            LEFT JOIN users ON uploads.user_id = users.id
        """
        if status:
            rows = conn.execute(
                f"""
                {base_query}
                WHERE uploads.status = ?
                ORDER BY uploads.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                {base_query}
                ORDER BY uploads.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a database row to a dictionary."""
    result = dict(row)

    # Parse filename - could be JSON array (new) or plain string (old)
    if result.get("filename"):
        try:
            parsed = json.loads(result["filename"])
            if isinstance(parsed, list):
                result["filenames"] = parsed
                # Keep filename as display string for backward compat
                result["filename"] = ", ".join(parsed) if len(parsed) > 1 else parsed[0]
            else:
                result["filenames"] = [result["filename"]]
        except json.JSONDecodeError:
            # Old format - single filename string
            result["filenames"] = [result["filename"]]

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


# User functions


def create_user(
    email: str,
    name: str | None,
    auth_type: str,
    password_hash: str | None = None,
    is_admin: bool = False,
    password_change_required: bool = False,
) -> dict:
    """Create a new user."""
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, auth_type, password_hash, is_admin, password_change_required)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, email, name, auth_type, password_hash, 1 if is_admin else 0, 1 if password_change_required else 0),
        )
    return get_user_by_id(user_id)


def get_user_by_id(user_id: str) -> dict | None:
    """Get user by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row:
        return dict(row)
    return None


def get_user_by_email(email: str) -> dict | None:
    """Get user by email."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row:
        return dict(row)
    return None


def list_users(include_deleted: bool = True) -> list[dict]:
    """List all users, optionally excluding deleted ones."""
    with get_connection() as conn:
        if include_deleted:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def update_user(user_id: str, **kwargs) -> dict | None:
    """Update a user record with the given fields."""
    if not kwargs:
        return get_user_by_id(user_id)

    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [user_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            values,
        )
    return get_user_by_id(user_id)


def count_admins() -> int:
    """Count active admin users."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE is_admin = 1 AND deleted_at IS NULL"
        ).fetchone()
    return row["count"] if row else 0


def update_user_last_login(user_id: str) -> None:
    """Update user's last login timestamp."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user_id),
        )


def count_users() -> int:
    """Count total users."""
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def deactivate_user(user_id: str) -> None:
    """
    Deactivate a user account.

    Prevents the user from logging in while keeping their email address
    associated with the account. The user can be reactivated later.

    Args:
        user_id: The unique identifier of the user to deactivate.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?",
            (user_id,)
        )


def reactivate_user(user_id: str) -> None:
    """
    Reactivate a deactivated user account.

    Restores login access for a previously deactivated user.

    Args:
        user_id: The unique identifier of the user to reactivate.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET is_active = 1 WHERE id = ?",
            (user_id,)
        )


# API Key functions


def create_api_key(
    user_id: str,
    name: str,
    key_hash: str,
    expires_in_days: int,
) -> dict:
    """Create a new API key."""
    key_id = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (id, user_id, name, key_hash, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key_id, user_id, name, key_hash, expires_at),
        )
    return get_api_key_by_id(key_id)


def get_api_key_by_id(key_id: str) -> dict | None:
    """Get API key by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE id = ?", (key_id,)
        ).fetchone()
    if row:
        return dict(row)
    return None


def get_api_key_by_hash(key_hash: str) -> dict | None:
    """Get API key by hash."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
    if row:
        return dict(row)
    return None


def list_api_keys_for_user(user_id: str) -> list[dict]:
    """List all API keys for a user."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_api_key(key_id: str) -> None:
    """Delete an API key."""
    with get_connection() as conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))


def update_api_key_last_used(key_id: str) -> None:
    """Update API key last used timestamp."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE api_keys SET last_used = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), key_id),
        )


# Audit log functions


def create_audit_log(
    user_id: str,
    action: str,
    target: str | None = None,
    details: str | None = None,
) -> dict:
    """Create an audit log entry."""
    log_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (id, user_id, action, target, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (log_id, user_id, action, target, details),
        )
        row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (log_id,)).fetchone()
    return dict(row)


def list_audit_logs(
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List audit logs with optional filters."""
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
