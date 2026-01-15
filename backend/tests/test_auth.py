import hashlib

import pytest
from app.services.database import (
    create_user,
    get_user_by_id,
    get_user_by_email,
    list_users,
    create_api_key,
    get_api_key_by_hash,
    list_api_keys_for_user,
    delete_api_key,
    create_audit_log,
    list_audit_logs,
)


class TestUsers:
    def test_create_user_local(self, db):
        user = create_user(
            email="test@example.com",
            name="Test User",
            auth_type="local",
            password_hash="hashed123",
        )
        assert user["id"] is not None
        assert user["email"] == "test@example.com"
        assert user["auth_type"] == "local"

    def test_get_user_by_email(self, db):
        create_user(
            email="find@example.com",
            name="Find Me",
            auth_type="local",
        )
        user = get_user_by_email("find@example.com")
        assert user is not None
        assert user["name"] == "Find Me"

    def test_get_user_by_email_not_found(self, db):
        user = get_user_by_email("notfound@example.com")
        assert user is None


class TestApiKeys:
    def test_create_api_key(self, db):
        user = create_user(email="keyuser@example.com", name="Key User", auth_type="local")
        key_hash = hashlib.sha256(b"test-key").hexdigest()
        api_key = create_api_key(
            user_id=user["id"],
            name="Test Key",
            key_hash=key_hash,
            expires_in_days=30,
        )
        assert api_key["id"] is not None
        assert api_key["name"] == "Test Key"

    def test_get_api_key_by_hash(self, db):
        user = create_user(email="keyuser2@example.com", name="Key User", auth_type="local")
        key_hash = hashlib.sha256(b"find-key").hexdigest()
        create_api_key(user_id=user["id"], name="Find Key", key_hash=key_hash, expires_in_days=30)
        found = get_api_key_by_hash(key_hash)
        assert found is not None
        assert found["name"] == "Find Key"

    def test_list_api_keys_for_user(self, db):
        user = create_user(email="keyuser3@example.com", name="Key User", auth_type="local")
        key_hash1 = hashlib.sha256(b"key1").hexdigest()
        key_hash2 = hashlib.sha256(b"key2").hexdigest()
        create_api_key(user_id=user["id"], name="Key 1", key_hash=key_hash1, expires_in_days=30)
        create_api_key(user_id=user["id"], name="Key 2", key_hash=key_hash2, expires_in_days=30)
        keys = list_api_keys_for_user(user["id"])
        assert len(keys) == 2

    def test_delete_api_key(self, db):
        user = create_user(email="keyuser4@example.com", name="Key User", auth_type="local")
        key_hash = hashlib.sha256(b"delete-key").hexdigest()
        api_key = create_api_key(user_id=user["id"], name="Delete Key", key_hash=key_hash, expires_in_days=30)
        delete_api_key(api_key["id"])
        found = get_api_key_by_hash(key_hash)
        assert found is None


class TestAuditLog:
    def test_create_audit_log(self, db):
        user = create_user(email="audit@example.com", name="Audit User", auth_type="local")
        log = create_audit_log(
            user_id=user["id"],
            action="delete_index",
            target="shipit-test",
        )
        assert log["id"] is not None
        assert log["action"] == "delete_index"

    def test_list_audit_logs(self, db):
        user = create_user(email="audit2@example.com", name="Audit User", auth_type="local")
        create_audit_log(user_id=user["id"], action="action1", target="target1")
        create_audit_log(user_id=user["id"], action="action2", target="target2")
        logs = list_audit_logs()
        assert len(logs) >= 2
