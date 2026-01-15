import pytest
from app.services.database import (
    create_user,
    get_user_by_id,
    get_user_by_email,
    list_users,
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
