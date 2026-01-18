# backend/tests/test_auth_timing.py
import pytest
from unittest.mock import patch, MagicMock
from app.routers.auth import authenticate_user


class TestTimingAttackPrevention:
    def test_nonexistent_user_still_hashes(self, db):
        """Authentication should hash password even for nonexistent users."""
        with patch('app.routers.auth.verify_password') as mock_verify:
            mock_verify.return_value = False

            result = authenticate_user("nonexistent@example.com", "anypassword")

            # verify_password should still be called (timing attack prevention)
            assert mock_verify.called
            assert result is None

    def test_existing_user_wrong_password(self, db):
        """Wrong password for existing user should fail."""
        from app.services.database import create_user
        from app.services.auth import hash_password

        create_user(
            email="test@example.com",
            name="Test User",
            auth_type="local",
            password_hash=hash_password("correctpassword")
        )

        result = authenticate_user("test@example.com", "wrongpassword")
        assert result is None

    def test_existing_user_correct_password(self, db):
        """Correct password for existing user should succeed."""
        from app.services.database import create_user
        from app.services.auth import hash_password

        create_user(
            email="valid@example.com",
            name="Valid User",
            auth_type="local",
            password_hash=hash_password("correctpassword")
        )

        result = authenticate_user("valid@example.com", "correctpassword")
        assert result is not None
        assert result["email"] == "valid@example.com"

    def test_oidc_user_cannot_authenticate(self, db):
        """OIDC users cannot authenticate with password."""
        from app.services.database import create_user

        create_user(
            email="oidc@example.com",
            name="OIDC User",
            auth_type="oidc",
        )

        result = authenticate_user("oidc@example.com", "anypassword")
        assert result is None

    def test_inactive_user_cannot_authenticate(self, db):
        """Inactive users cannot authenticate."""
        from app.services.database import create_user, deactivate_user
        from app.services.auth import hash_password

        user = create_user(
            email="inactive@example.com",
            name="Inactive User",
            auth_type="local",
            password_hash=hash_password("correctpassword")
        )
        deactivate_user(user["id"])

        result = authenticate_user("inactive@example.com", "correctpassword")
        assert result is None

    def test_user_without_password_hash_cannot_authenticate(self, db):
        """Users without a password hash cannot authenticate."""
        from app.services.database import create_user

        create_user(
            email="nohash@example.com",
            name="No Hash User",
            auth_type="local",
            password_hash=None
        )

        result = authenticate_user("nohash@example.com", "anypassword")
        assert result is None
