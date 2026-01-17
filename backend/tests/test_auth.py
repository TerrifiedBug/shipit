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
    deactivate_user,
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
        create_audit_log(
            event_type="index_deleted",
            actor_id=user["id"],
            actor_name=user["email"],
            target_type="index",
            target_id="shipit-test",
        )
        logs, total = list_audit_logs()
        assert total >= 1
        # Find our log
        matching = [log for log in logs if log.get("event_type") == "index_deleted"]
        assert len(matching) >= 1
        assert matching[0]["actor_id"] == user["id"]

    def test_list_audit_logs(self, db):
        user = create_user(email="audit2@example.com", name="Audit User", auth_type="local")
        create_audit_log(event_type="test_event_1", actor_id=user["id"], actor_name=user["email"])
        create_audit_log(event_type="test_event_2", actor_id=user["id"], actor_name=user["email"])
        logs, total = list_audit_logs()
        assert total >= 2


class TestAuthService:
    def test_hash_and_verify_password(self):
        password = "mysecretpassword"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword123", hashed) is False

    def test_create_and_verify_session_token(self, db):
        # Now requires database since sessions are tracked
        user_id = "user-123"
        token = create_session_token(user_id)
        assert token is not None
        payload = verify_session_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        # Verify session ID is included in token
        assert "sid" in payload

    def test_expired_session_token(self):
        # Create token with -1 hour expiry (already expired)
        # Note: session_id=None means no database session tracking
        user_id = "user-123"
        from app.services.auth import _create_token
        token = _create_token(user_id, session_id=None, expires_hours=-1)
        payload = verify_session_token(token)
        assert payload is None


client = TestClient(app)


class TestAuthEndpoints:
    def test_setup_first_user(self, db):
        response = client.post("/api/auth/setup", json={
            "email": "admin@example.com",
            "password": "AdminPass123",
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
            "password": "AdminPass123",
            "name": "Admin",
        })
        # Try to create another via setup
        response = client.post("/api/auth/setup", json={
            "email": "hacker@example.com",
            "password": "HackPass123",
            "name": "Hacker",
        })
        assert response.status_code == 400

    def test_login_success(self, db):
        # Setup user first
        client.post("/api/auth/setup", json={
            "email": "login@example.com",
            "password": "TestPass123",
            "name": "Login User",
        })
        # Login
        response = client.post("/api/auth/login", json={
            "email": "login@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 200
        assert "session" in response.cookies

    def test_login_wrong_password(self, db):
        client.post("/api/auth/setup", json={
            "email": "wrong@example.com",
            "password": "CorrectPass123",
            "name": "User",
        })
        response = client.post("/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "WrongPass123",
        })
        assert response.status_code == 401

    def test_login_deactivated_user(self, db):
        """Test that deactivated users cannot login."""
        # Setup user first
        client.post("/api/auth/setup", json={
            "email": "deactivated@example.com",
            "password": "TestPass123",
            "name": "Deactivated User",
        })
        # Deactivate the user
        user = get_user_by_email("deactivated@example.com")
        deactivate_user(user["id"])
        # Try to login - should fail with 403
        response = client.post("/api/auth/login", json={
            "email": "deactivated@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 403
        assert "deactivated" in response.json()["detail"].lower()

    def test_me_authenticated(self, db):
        # Setup and login
        client.post("/api/auth/setup", json={
            "email": "me@example.com",
            "password": "Password123",
            "name": "Me User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "me@example.com",
            "password": "Password123",
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
            "password": "Password123",
            "name": "Logout User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "logout@example.com",
            "password": "Password123",
        })
        # Logout
        logout_response = client.post("/api/auth/logout", cookies=login_response.cookies)
        assert logout_response.status_code == 200
        # Session should be cleared
        me_response = client.get("/api/auth/me", cookies=logout_response.cookies)
        assert me_response.status_code == 401


class TestApiKeyEndpoints:
    def _login(self, db):
        """Helper to setup and login, returns cookies."""
        client.post("/api/auth/setup", json={
            "email": "keytest@example.com",
            "password": "Password123",
            "name": "Key Test User",
        })
        response = client.post("/api/auth/login", json={
            "email": "keytest@example.com",
            "password": "Password123",
        })
        return response.cookies

    def test_create_api_key(self, db):
        cookies = self._login(db)
        response = client.post("/api/keys", json={
            "name": "My Key",
            "expires_in_days": 30,
        }, cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Key"
        assert data["key"].startswith("shipit_")
        # Key should only be shown once
        assert len(data["key"]) > 20

    def test_list_api_keys(self, db):
        cookies = self._login(db)
        # Create a key
        client.post("/api/keys", json={"name": "List Key", "expires_in_days": 30}, cookies=cookies)
        # List keys
        response = client.get("/api/keys", cookies=cookies)
        assert response.status_code == 200
        keys = response.json()
        assert len(keys) >= 1
        # Key hash should not be in response
        assert "key_hash" not in keys[0]

    def test_delete_api_key(self, db):
        cookies = self._login(db)
        # Create a key
        create_response = client.post("/api/keys", json={"name": "Delete Key", "expires_in_days": 30}, cookies=cookies)
        key_id = create_response.json()["id"]
        # Delete it
        delete_response = client.delete(f"/api/keys/{key_id}", cookies=cookies)
        assert delete_response.status_code == 200
        # Should not be in list anymore
        list_response = client.get("/api/keys", cookies=cookies)
        key_ids = [k["id"] for k in list_response.json()]
        assert key_id not in key_ids

    def test_api_key_auth(self, db):
        cookies = self._login(db)
        # Create a key
        create_response = client.post("/api/keys", json={"name": "Auth Key", "expires_in_days": 30}, cookies=cookies)
        api_key = create_response.json()["key"]
        # Use the key to access /api/auth/me
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {api_key}"})
        assert response.status_code == 200
        assert response.json()["email"] == "keytest@example.com"


class TestPasswordChange:
    def _setup_and_login(self, db, email, password):
        """Helper to setup user and return login cookies."""
        client.post("/api/auth/setup", json={
            "email": email,
            "password": password,
            "name": "Test User",
        })
        response = client.post("/api/auth/login", json={
            "email": email,
            "password": password,
        })
        return response.cookies

    def test_change_password_success(self, db):
        """Test successful password change."""
        cookies = self._setup_and_login(db, "changepw@example.com", "OldPassword123")
        session_token = cookies.get("session")

        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123",
                "new_password": "NewPassword456"
            },
            cookies={"session": session_token}
        )

        assert response.status_code == 200

        # Clear rate limit by using a fresh test client
        # Verify user data was updated properly instead of re-login
        # to avoid rate limiting issues
        from app.services.auth import verify_password
        user = get_user_by_email("changepw@example.com")
        assert verify_password("NewPassword456", user["password_hash"])

    def test_change_password_wrong_current(self, db):
        """Test password change with wrong current password."""
        cookies = self._setup_and_login(db, "wrongpw@example.com", "CorrectPassword123")

        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "WrongPassword123",
                "new_password": "NewPassword123"
            },
            cookies=cookies
        )

        assert response.status_code == 401
        assert "current password" in response.json()["detail"].lower()

    def test_change_password_oidc_user(self, db):
        """Test that OIDC users cannot change password."""
        from app.services.auth import create_session_token

        # Use a fresh TestClient to avoid test pollution
        from fastapi.testclient import TestClient as FreshClient
        from app.main import app
        fresh_client = FreshClient(app)

        # Create an OIDC user directly in the database
        user = create_user("oidc@example.com", "OIDC User", "oidc", is_admin=False)
        # create_session_token now creates a database session too
        token = create_session_token(user["id"])

        response = fresh_client.post(
            "/api/auth/change-password",
            json={
                "current_password": "anypass",
                "new_password": "NewPassword123"
            },
            cookies={"session": token}
        )

        assert response.status_code == 403
        assert "cannot change password" in response.json()["detail"].lower()

    def test_change_password_too_short(self, db):
        """Test password change with too short new password."""
        cookies = self._setup_and_login(db, "shortpw@example.com", "OldPassword123")

        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123",
                "new_password": "short"
            },
            cookies=cookies
        )

        assert response.status_code == 400
        assert "8 characters" in response.json()["detail"]


class TestSessionInvalidation:
    """Test session invalidation on password change."""

    def test_password_change_invalidates_other_sessions(self, db):
        """Test that changing password invalidates other sessions but keeps current one."""
        from app.services.database import get_session, create_session
        from app.services.auth import _create_token
        from datetime import datetime, timedelta, timezone

        # Create user via the shared client (which uses the patched DB)
        setup_resp = client.post("/api/auth/setup", json={
            "email": "session-test@example.com",
            "password": "Password123",
            "name": "Session Test User",
        })

        # Login from "device 1"
        login1_response = client.post("/api/auth/login", json={
            "email": "session-test@example.com",
            "password": "Password123",
        })
        assert login1_response.status_code == 200, f"Login failed: {login1_response.json()}"
        # Access cookie via dict method
        token1 = dict(login1_response.cookies).get("session")
        assert token1 is not None, f"Expected session cookie, got: {login1_response.cookies}"

        # Get user ID
        user = get_user_by_email("session-test@example.com")

        # Create a second session manually (simulating device 2)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        session2_id = create_session(user["id"], expires_at)
        token2 = _create_token(user["id"], session2_id, expires_hours=8)

        # Verify both sessions exist in database
        payload1 = verify_session_token(token1)
        assert payload1 is not None
        assert get_session(payload1["sid"]) is not None
        assert get_session(session2_id) is not None

        # Change password from device 1
        change_response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Password123",
                "new_password": "NewPassword456"
            },
            cookies={"session": token1}
        )
        assert change_response.status_code == 200
        # Should report sessions invalidated
        assert change_response.json().get("sessions_invalidated", 0) >= 1

        # Device 1 session should still be valid
        assert client.get("/api/auth/me", cookies={"session": token1}).status_code == 200

        # Device 2 session should be invalidated (deleted from database)
        assert get_session(session2_id) is None

    def test_logout_invalidates_session_in_database(self, db):
        """Test that logout removes session from database."""
        from app.services.database import get_session

        # Create user and login
        client.post("/api/auth/setup", json={
            "email": "logout-test@example.com",
            "password": "Password123",
            "name": "Logout Test User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "logout-test@example.com",
            "password": "Password123",
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.json()}"
        # Access cookie via dict method
        session_token = dict(login_response.cookies).get("session")
        assert session_token is not None, f"Expected session cookie, got: {login_response.cookies}"

        # Extract session ID from token
        payload = verify_session_token(session_token)
        assert payload is not None
        session_id = payload.get("sid")
        assert session_id is not None

        # Verify session exists in database
        session = get_session(session_id)
        assert session is not None

        # Logout
        client.post("/api/auth/logout", cookies={"session": session_token})

        # Session should be deleted from database
        session = get_session(session_id)
        assert session is None


class TestAuthMiddleware:
    def test_protected_endpoint_requires_auth(self, db):
        # /api/history should require auth
        response = client.get("/api/history")
        assert response.status_code == 401

    def test_health_is_public(self, db):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_protected_endpoint_with_auth(self, db):
        # Setup and login
        client.post("/api/auth/setup", json={
            "email": "middleware@example.com",
            "password": "Password123",
            "name": "Middleware User",
        })
        login_response = client.post("/api/auth/login", json={
            "email": "middleware@example.com",
            "password": "Password123",
        })
        # Access protected endpoint
        response = client.get("/api/history", cookies=login_response.cookies)
        assert response.status_code == 200
