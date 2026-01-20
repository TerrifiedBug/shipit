"""Audit logging service for tracking security-relevant events."""
from __future__ import annotations

from app.services import database as db


def log_login_success(user_id: str, user_email: str, ip_address: str | None = None) -> None:
    """Log a successful login."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_LOGIN_SUCCESS,
        actor_id=user_id,
        actor_name=user_email,
        ip_address=ip_address,
    )


def log_login_failed(email: str, reason: str, ip_address: str | None = None) -> None:
    """Log a failed login attempt."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_LOGIN_FAILED,
        actor_name=email,
        details={"reason": reason},
        ip_address=ip_address,
    )


def log_logout(user_id: str, user_email: str, ip_address: str | None = None) -> None:
    """Log a user logout."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_LOGOUT,
        actor_id=user_id,
        actor_name=user_email,
        ip_address=ip_address,
    )


def log_user_created(
    actor_id: str,
    actor_name: str,
    target_user_id: str,
    target_email: str,
    is_admin: bool,
    role: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Log user creation."""
    details = {"email": target_email, "is_admin": is_admin}
    if role:
        details["role"] = role
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_USER_CREATED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="user",
        target_id=target_user_id,
        details=details,
        ip_address=ip_address,
    )


def log_user_modified(
    actor_id: str,
    actor_name: str,
    target_user_id: str,
    target_email: str,
    changes: dict,
    ip_address: str | None = None,
) -> None:
    """Log user modification."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_USER_MODIFIED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="user",
        target_id=target_user_id,
        details={"email": target_email, "changes": changes},
        ip_address=ip_address,
    )


def log_user_deleted(
    actor_id: str,
    actor_name: str,
    target_user_id: str,
    target_email: str,
    ip_address: str | None = None,
) -> None:
    """Log user deletion."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_USER_DELETED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="user",
        target_id=target_user_id,
        details={"email": target_email},
        ip_address=ip_address,
    )


def log_api_key_created(
    actor_id: str,
    actor_name: str,
    key_id: str,
    key_name: str,
    expires_in_days: int,
    ip_address: str | None = None,
) -> None:
    """Log API key creation."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_API_KEY_CREATED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="api_key",
        target_id=key_id,
        details={"name": key_name, "expires_in_days": expires_in_days},
        ip_address=ip_address,
    )


def log_api_key_deleted(
    actor_id: str,
    actor_name: str,
    key_id: str,
    key_name: str,
    ip_address: str | None = None,
) -> None:
    """Log API key deletion."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_API_KEY_DELETED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="api_key",
        target_id=key_id,
        details={"name": key_name},
        ip_address=ip_address,
    )


def log_index_created(
    actor_id: str | None,
    actor_name: str | None,
    index_name: str,
    ip_address: str | None = None,
) -> None:
    """Log index creation."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_INDEX_CREATED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="index",
        target_id=index_name,
        ip_address=ip_address,
    )


def log_index_deleted(
    actor_id: str,
    actor_name: str,
    index_name: str,
    ip_address: str | None = None,
) -> None:
    """Log index deletion."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_INDEX_DELETED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="index",
        target_id=index_name,
        ip_address=ip_address,
    )


def log_ingestion_started(
    actor_id: str | None,
    actor_name: str | None,
    upload_id: str,
    index_name: str,
    total_records: int,
    ip_address: str | None = None,
) -> None:
    """Log ingestion start."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_INGESTION_STARTED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="upload",
        target_id=upload_id,
        details={"index_name": index_name, "total_records": total_records},
        ip_address=ip_address,
    )


def log_ingestion_completed(
    actor_id: str | None,
    actor_name: str | None,
    upload_id: str,
    index_name: str,
    success_count: int,
    failure_count: int,
    ip_address: str | None = None,
) -> None:
    """Log ingestion completion."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_INGESTION_COMPLETED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="upload",
        target_id=upload_id,
        details={
            "index_name": index_name,
            "success_count": success_count,
            "failure_count": failure_count,
        },
        ip_address=ip_address,
    )


def log_template_created(
    actor_id: str,
    actor_name: str,
    template_id: str,
    template_name: str,
    ip_address: str | None = None,
) -> None:
    """Log index template creation."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_TEMPLATE_CREATED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="template",
        target_id=template_id,
        details={"name": template_name},
        ip_address=ip_address,
    )


def log_template_deleted(
    actor_id: str,
    actor_name: str,
    template_id: str,
    template_name: str,
    ip_address: str | None = None,
) -> None:
    """Log index template deletion."""
    db.create_audit_log(
        event_type=db.AUDIT_EVENT_TEMPLATE_DELETED,
        actor_id=actor_id,
        actor_name=actor_name,
        target_type="template",
        target_id=template_id,
        details={"name": template_name},
        ip_address=ip_address,
    )
