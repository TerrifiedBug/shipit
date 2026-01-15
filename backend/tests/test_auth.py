import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import hash_password, verify_password, create_session_token, verify_session_token
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


class TestAuthService:
    def test_hash_and_verify_password(self):
        password = "mysecretpassword"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False

    def test_create_and_verify_session_token(self):
        user_id = "user-123"
        token = create_session_token(user_id)
        assert token is not None
        payload = verify_session_token(token)
        assert payload is not None
        assert payload["sub"] == user_id

    def test_expired_session_token(self):
        # Create token with -1 hour expiry (already expired)
        user_id = "user-123"
        from app.services.auth import _create_token
        token = _create_token(user_id, expires_hours=-1)
        payload = verify_session_token(token)
        assert payload is None


client = TestClient(app)


class TestAuthEndpoints:
    def test_setup_first_user(self, db):
        response = client.post("/api/auth/setup", json={
            "email": "admin@example.com",
            "password": "adminpassword",
            "name": "Admin User",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@example.com"
        assert data["is_admin"] == 1

    def test_setup_fails_when_users_exist(self, db):
        # Create first user
        client.post("/api/auth/setup", json={
            "email": "admin@example.com",
            "password": "adminpassword",
            "name": "Admin",
        })
        # Try to create another via setup
        response = client.post("/api/auth/setup", json={
            "email": "hacker@example.com",
            "password": "hackpass",
            "name": "Hacker",
        })
        assert response.status_code == 400

    def test_login_success(self, db):
        # Setup user first
        client.post("/api/auth/setup", json={
            "email": "login@example.com",
            "password": "testpassword",
            "name": "Login User",
        })
        # Login
        response = client.post("/api/auth/login", json={
            "email": "login@example.com",
            "password": "testpassword",
        })
        assert response.status_code == 200
        assert "session" in response.cookies

    def test_login_wrong_password(self, db):
        client.post("/api/auth/setup", json={
            "email": "wrong@example.com",
            "password": "correctpassword",
            "name": "User",
        })
        response = client.post("/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword",
        })
        assert response.status_code == 401

    def test_me_authenticated(self, db):
        # Setup and login
        client.post("/api/auth/setup", json={
            "email": "me@example.com",
            "password": "password",
            "name": "Me User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "me@example.com",
            "password": "password",
        })
        # Get me
        response = client.get("/api/auth/me", cookies=login_response.cookies)
        assert response.status_code == 200
        assert response.json()["email"] == "me@example.com"

    def test_me_unauthenticated(self, db):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_logout(self, db):
        # Setup and login
        client.post("/api/auth/setup", json={
            "email": "logout@example.com",
            "password": "password",
            "name": "Logout User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "logout@example.com",
            "password": "password",
        })
        # Logout
        logout_response = client.post("/api/auth/logout", cookies=login_response.cookies)
        assert logout_response.status_code == 200
        # Session should be cleared
        me_response = client.get("/api/auth/me", cookies=logout_response.cookies)
        assert me_response.status_code == 401
