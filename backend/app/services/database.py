from __future__ import annotations

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
            index_deleted   INTEGER DEFAULT 0,
            pattern_id      TEXT,
            multiline_start TEXT,
            multiline_max_lines INTEGER DEFAULT 100
        );

        CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
    """)
    # Migration: add index_deleted column if it doesn't exist
    try:
        conn.execute("ALTER TABLE uploads ADD COLUMN index_deleted INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add upload_method column if it doesn't exist
    try:
        conn.execute("ALTER TABLE uploads ADD COLUMN upload_method TEXT DEFAULT 'web'")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add api_key_name column if it doesn't exist
    try:
        conn.execute("ALTER TABLE uploads ADD COLUMN api_key_name TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add pattern_id column if it doesn't exist
    cursor = conn.execute("PRAGMA table_info(uploads)")
    columns = [row[1] for row in cursor.fetchall()]
    if "pattern_id" not in columns:
        conn.execute("ALTER TABLE uploads ADD COLUMN pattern_id TEXT")

    # Migration: add multiline columns if they don't exist
    if "multiline_start" not in columns:
        conn.execute("ALTER TABLE uploads ADD COLUMN multiline_start TEXT")
    if "multiline_max_lines" not in columns:
        conn.execute("ALTER TABLE uploads ADD COLUMN multiline_max_lines INTEGER DEFAULT 100")


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
    # Migration: add allowed_ips column if it doesn't exist
    try:
        conn.execute("ALTER TABLE api_keys ADD COLUMN allowed_ips TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _init_audit_log_table(conn: sqlite3.Connection) -> None:
    """Create audit_log table for comprehensive audit logging."""
    # Check if old audit_log table exists with incompatible schema
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    table_exists = cursor.fetchone() is not None

    if table_exists:
        # Check if it has the new schema (event_type column)
        cursor = conn.execute("PRAGMA table_info(audit_log)")
        columns = {row[1] for row in cursor.fetchall()}

        if "event_type" not in columns:
            # Old schema - drop and recreate (audit logs are not critical data)
            conn.execute("DROP TABLE audit_log")
            table_exists = False

    if not table_exists:
        conn.execute("""
            CREATE TABLE audit_log (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                actor_id TEXT,
                actor_name TEXT,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # Create indexes (safe now that schema is correct)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_actor_id ON audit_log(actor_id)")


def _init_shipit_indices_table(conn: sqlite3.Connection) -> None:
    """Create shipit_indices table for tracking ShipIt-created indices."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shipit_indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by_user_id TEXT
        )
    """)


def _init_failed_logins_table(conn: sqlite3.Connection) -> None:
    """Create failed_logins table for tracking failed login attempts."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS failed_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            ip_address TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_logins_user_id ON failed_logins(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_logins_attempted_at ON failed_logins(attempted_at)")


def _init_sessions_table(conn: sqlite3.Connection) -> None:
    """Create sessions table for tracking active user sessions."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")


def _init_patterns_table(conn: sqlite3.Connection) -> None:
    """Create patterns table for storing custom parsing patterns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            description TEXT,
            test_sample TEXT,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_name ON patterns(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_created_by ON patterns(created_by)")


def _init_grok_patterns_table(conn: sqlite3.Connection) -> None:
    """Create grok_patterns table for storing reusable grok pattern components."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grok_patterns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            regex TEXT NOT NULL,
            description TEXT,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_grok_patterns_name ON grok_patterns(name)")


def init_db() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        _init_uploads_table(conn)
        _init_users_table(conn)
        _init_api_keys_table(conn)
        _init_audit_log_table(conn)
        _init_shipit_indices_table(conn)
        _init_failed_logins_table(conn)
        _init_sessions_table(conn)
        _init_patterns_table(conn)
        _init_grok_patterns_table(conn)


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
    upload_method: str = "web",
    api_key_name: str | None = None,
) -> dict[str, Any]:
    """Create a new upload record for one or more files.

    Args:
        upload_id: Unique identifier for this upload
        filenames: List of uploaded filenames
        file_sizes: List of file sizes in bytes
        file_format: Detected file format (json_array, ndjson, csv, etc.)
        user_id: ID of the user performing the upload (optional)
        upload_method: "web" for UI uploads, "api" for API uploads
        api_key_name: Name of the API key if upload_method is "api"
    """
    # Store filenames as JSON array, total size
    filename_json = json.dumps(filenames)
    total_size = sum(file_sizes)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, filename, file_size, file_format, status, user_id, upload_method, api_key_name)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (upload_id, filename_json, total_size, file_format, user_id, upload_method, api_key_name),
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
    """Create a new user or reactivate a deleted user.

    If a user with the same email was previously deleted, reactivate them
    with the new information instead of creating a duplicate.
    """
    with get_connection() as conn:
        # Check if a deleted user exists with this email
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? AND deleted_at IS NOT NULL",
            (email,),
        ).fetchone()

        if existing:
            # Reactivate deleted user with new information
            user_id = existing[0]
            conn.execute(
                """UPDATE users
                   SET name = ?, auth_type = ?, password_hash = ?, is_admin = ?,
                       password_change_required = ?, deleted_at = NULL, is_active = 1
                   WHERE id = ?""",
                (name, auth_type, password_hash, 1 if is_admin else 0,
                 1 if password_change_required else 0, user_id),
            )
        else:
            # Create new user
            user_id = str(uuid.uuid4())
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


def get_user_by_email(email: str, include_deleted: bool = False) -> dict | None:
    """Get user by email.

    Args:
        email: The email address to look up.
        include_deleted: If True, include soft-deleted users. Defaults to False.
    """
    with get_connection() as conn:
        if include_deleted:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? AND deleted_at IS NULL", (email,)
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


def delete_user(user_id: str) -> None:
    """
    Soft delete a user account.

    Sets the deleted_at timestamp, which prevents login and hides the user
    from default queries. The email remains tied to the account but can be
    reclaimed if the user re-registers.

    Args:
        user_id: The unique identifier of the user to delete.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET deleted_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user_id),
        )


# API Key functions


def create_api_key(
    user_id: str,
    name: str,
    key_hash: str,
    expires_in_days: int,
    allowed_ips: str | None = None,
) -> dict:
    """Create a new API key.

    Args:
        user_id: The user ID who owns this key
        name: Human-readable name for the key
        key_hash: SHA-256 hash of the raw API key
        expires_in_days: Number of days until expiration
        allowed_ips: Optional comma-separated IPs/CIDRs (e.g., "10.0.0.0/24, 192.168.1.5")
    """
    key_id = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (id, user_id, name, key_hash, expires_at, allowed_ips)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key_id, user_id, name, key_hash, expires_at, allowed_ips),
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

# Event type constants
AUDIT_EVENT_LOGIN_SUCCESS = "login_success"
AUDIT_EVENT_LOGIN_FAILED = "login_failed"
AUDIT_EVENT_LOGOUT = "logout"
AUDIT_EVENT_USER_CREATED = "user_created"
AUDIT_EVENT_USER_MODIFIED = "user_modified"
AUDIT_EVENT_USER_DELETED = "user_deleted"
AUDIT_EVENT_API_KEY_CREATED = "api_key_created"
AUDIT_EVENT_API_KEY_DELETED = "api_key_deleted"
AUDIT_EVENT_INDEX_CREATED = "index_created"
AUDIT_EVENT_INDEX_DELETED = "index_deleted"
AUDIT_EVENT_INGESTION_STARTED = "ingestion_started"
AUDIT_EVENT_INGESTION_COMPLETED = "ingestion_completed"


def create_audit_log(
    event_type: str,
    actor_id: str | None = None,
    actor_name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> dict:
    """Create an audit log entry.

    Args:
        event_type: Type of event (e.g., 'login_success', 'user_created')
        actor_id: ID of the user who performed the action
        actor_name: Name/email of the actor (for display when user is deleted)
        target_type: Type of target (e.g., 'user', 'api_key', 'index')
        target_id: ID of the target entity
        details: Additional details as a dictionary (stored as JSON)
        ip_address: IP address of the client

    Returns:
        The created audit log entry as a dictionary
    """
    log_id = str(uuid.uuid4())
    details_json = json.dumps(details) if details else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (id, event_type, actor_id, actor_name, target_type, target_id, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, event_type, actor_id, actor_name, target_type, target_id, details_json, ip_address),
        )
        row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (log_id,)).fetchone()

    result = dict(row)
    if result.get("details"):
        try:
            result["details"] = json.loads(result["details"])
        except json.JSONDecodeError:
            pass
    return result


def list_audit_logs(
    actor_id: str | None = None,
    event_type: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List audit logs with optional filters.

    Args:
        actor_id: Filter by actor ID
        event_type: Filter by event type
        target_type: Filter by target type
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        Tuple of (list of audit log entries, total count)
    """
    query = "SELECT * FROM audit_log WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM audit_log WHERE 1=1"
    params: list[Any] = []

    if actor_id:
        query += " AND actor_id = ?"
        count_query += " AND actor_id = ?"
        params.append(actor_id)
    if event_type:
        query += " AND event_type = ?"
        count_query += " AND event_type = ?"
        params.append(event_type)
    if target_type:
        query += " AND target_type = ?"
        count_query += " AND target_type = ?"
        params.append(target_type)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"

    with get_connection() as conn:
        # Get total count
        total = conn.execute(count_query, params).fetchone()[0]

        # Get paginated results
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        entry = dict(row)
        if entry.get("details"):
            try:
                entry["details"] = json.loads(entry["details"])
            except json.JSONDecodeError:
                pass
        results.append(entry)

    return results, total


def get_audit_log_event_types() -> list[str]:
    """Get list of distinct event types in audit log."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT event_type FROM audit_log ORDER BY event_type"
        ).fetchall()
    return [row[0] for row in rows if row[0]]


# Index tracking functions


def track_index(index_name: str, user_id: str | None = None) -> None:
    """
    Track a ShipIt-created index.

    Records that an index was created by ShipIt, allowing us to distinguish
    between ShipIt-managed indices and external indices.

    Args:
        index_name: The name of the Elasticsearch index.
        user_id: The ID of the user who created the index.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO shipit_indices (index_name, created_by_user_id)
            VALUES (?, ?)
            """,
            (index_name, user_id),
        )


def untrack_index(index_name: str) -> None:
    """
    Remove tracking for an index.

    Called when a ShipIt-managed index is deleted.

    Args:
        index_name: The name of the Elasticsearch index to untrack.
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM shipit_indices WHERE index_name = ?",
            (index_name,),
        )


def is_index_tracked(index_name: str) -> bool:
    """
    Check if an index is tracked by ShipIt.

    Args:
        index_name: The name of the Elasticsearch index to check.

    Returns:
        True if the index was created by ShipIt, False otherwise.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM shipit_indices WHERE index_name = ?",
            (index_name,),
        ).fetchone()
    return row is not None


# Failed login tracking functions (for account lockout)


def record_failed_login(user_id: str, ip_address: str | None = None) -> None:
    """
    Record a failed login attempt for a user.

    Args:
        user_id: The ID of the user who failed to log in.
        ip_address: The IP address of the client.
    """
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO failed_logins (user_id, ip_address) VALUES (?, ?)",
            (user_id, ip_address),
        )


def get_failed_login_count(user_id: str, minutes: int) -> int:
    """
    Get the number of failed login attempts for a user within the given time window.

    Args:
        user_id: The ID of the user to check.
        minutes: The time window in minutes to check for failed attempts.

    Returns:
        The number of failed login attempts within the time window.
    """
    # Use strftime format to match SQLite's CURRENT_TIMESTAMP format (space separator, not 'T')
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM failed_logins WHERE user_id = ? AND attempted_at > ?",
            (user_id, cutoff),
        ).fetchone()
    return row[0] if row else 0


def clear_failed_logins(user_id: str) -> None:
    """
    Clear all failed login attempts for a user.

    Called after a successful login to reset the lockout counter.

    Args:
        user_id: The ID of the user to clear failed logins for.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM failed_logins WHERE user_id = ?", (user_id,))


def is_account_locked(user_id: str, lockout_minutes: int) -> bool:
    """
    Check if an account is locked due to too many failed login attempts.

    Args:
        user_id: The ID of the user to check.
        lockout_minutes: The time window in minutes for the lockout period.

    Returns:
        True if the account is locked, False otherwise.
    """
    from app.config import settings
    failed_count = get_failed_login_count(user_id, lockout_minutes)
    return failed_count >= settings.account_lockout_attempts


# Session management functions


def create_session(user_id: str, expires_at: datetime) -> str:
    """
    Create a new session for a user.

    Args:
        user_id: The ID of the user.
        expires_at: When the session expires.

    Returns:
        The session ID.
    """
    session_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
            (session_id, user_id, expires_at.isoformat()),
        )
    return session_id


def get_session(session_id: str) -> dict | None:
    """
    Get a session by ID.

    Args:
        session_id: The session ID.

    Returns:
        The session record or None if not found/expired.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND expires_at > ?",
            (session_id, datetime.utcnow().isoformat()),
        ).fetchone()
    if row:
        return dict(row)
    return None


def delete_session(session_id: str) -> None:
    """
    Delete a specific session.

    Args:
        session_id: The session ID to delete.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def delete_other_sessions(user_id: str, current_session_id: str) -> int:
    """
    Delete all sessions for a user except the current one.

    Used when changing password to invalidate other sessions.

    Args:
        user_id: The ID of the user.
        current_session_id: The session ID to keep.

    Returns:
        The number of sessions deleted.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND id != ?",
            (user_id, current_session_id),
        )
        return cursor.rowcount


def cleanup_expired_sessions() -> int:
    """
    Delete all expired sessions.

    Should be called periodically to clean up the sessions table.

    Returns:
        The number of sessions deleted.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.utcnow().isoformat(),),
        )
        return cursor.rowcount


# Pattern management functions (for complete parsing patterns)


def create_pattern(
    name: str,
    pattern_type: str,
    pattern: str,
    user_id: str,
    description: str | None = None,
    test_sample: str | None = None,
) -> dict:
    """Create a new parsing pattern."""
    pattern_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO patterns (id, name, type, pattern, description, test_sample, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pattern_id, name, pattern_type, pattern, description, test_sample, user_id, now, now),
        )
    return get_pattern(pattern_id)


def get_pattern(pattern_id: str) -> dict | None:
    """Get a pattern by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM patterns WHERE id = ?", (pattern_id,)
        ).fetchone()
    return dict(row) if row else None


def list_patterns() -> list[dict]:
    """List all patterns."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM patterns ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def update_pattern(
    pattern_id: str,
    name: str | None = None,
    pattern: str | None = None,
    description: str | None = None,
    test_sample: str | None = None,
) -> dict | None:
    """Update a pattern."""
    existing = get_pattern(pattern_id)
    if not existing:
        return None

    updates = {"updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}
    if name is not None:
        updates["name"] = name
    if pattern is not None:
        updates["pattern"] = pattern
    if description is not None:
        updates["description"] = description
    if test_sample is not None:
        updates["test_sample"] = test_sample

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [pattern_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE patterns SET {set_clause} WHERE id = ?",
            values,
        )
    return get_pattern(pattern_id)


def delete_pattern(pattern_id: str) -> bool:
    """Delete a pattern. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM patterns WHERE id = ?", (pattern_id,)
        )
        return cursor.rowcount > 0


# Grok pattern component functions (for reusable grok patterns like %{MYPATTERN})


def create_grok_pattern(
    name: str,
    regex: str,
    user_id: str,
    description: str | None = None,
) -> dict:
    """Create a new reusable grok pattern component."""
    pattern_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO grok_patterns (id, name, regex, description, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pattern_id, name, regex, description, user_id, now, now),
        )
    return get_grok_pattern(pattern_id)


def get_grok_pattern(pattern_id: str) -> dict | None:
    """Get a grok pattern by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grok_patterns WHERE id = ?", (pattern_id,)
        ).fetchone()
    return dict(row) if row else None


def get_grok_pattern_by_name(name: str) -> dict | None:
    """Get a grok pattern by name."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grok_patterns WHERE name = ?", (name,)
        ).fetchone()
    return dict(row) if row else None


def list_grok_patterns() -> list[dict]:
    """List all custom grok patterns."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM grok_patterns ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def get_grok_patterns_dict() -> dict[str, str]:
    """Get all custom grok patterns as a name->regex dict."""
    patterns = list_grok_patterns()
    return {p["name"]: p["regex"] for p in patterns}


def update_grok_pattern(
    pattern_id: str,
    name: str | None = None,
    regex: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update a grok pattern."""
    existing = get_grok_pattern(pattern_id)
    if not existing:
        return None

    updates = {"updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}
    if name is not None:
        updates["name"] = name
    if regex is not None:
        updates["regex"] = regex
    if description is not None:
        updates["description"] = description

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [pattern_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE grok_patterns SET {set_clause} WHERE id = ?",
            values,
        )
    return get_grok_pattern(pattern_id)


def delete_grok_pattern(pattern_id: str) -> bool:
    """Delete a grok pattern. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM grok_patterns WHERE id = ?", (pattern_id,)
        )
        return cursor.rowcount > 0
