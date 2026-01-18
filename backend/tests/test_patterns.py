"""Tests for patterns API router."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.fixture
def auth_headers(db):
    """Setup a user and return auth headers for API calls."""
    # Setup user
    client.post("/api/auth/setup", json={
        "email": "patterns-test@example.com",
        "password": "Password123",
        "name": "Patterns Test User",
    })
    # Login and get session cookie
    response = client.post("/api/auth/login", json={
        "email": "patterns-test@example.com",
        "password": "Password123",
    })
    cookies = response.cookies
    # Return headers dict with cookie for use in test client
    return {"Cookie": f"session={cookies.get('session')}"}


def test_expand_grok_pattern(db, auth_headers):
    """Test grok pattern expansion endpoint."""
    response = client.get(
        "/api/patterns/grok/expand",
        params={"pattern": "%{IP:client_ip} %{USER:username}"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "expanded" in data
    assert "client_ip" in data["groups"]
    assert "username" in data["groups"]


def test_expand_grok_pattern_invalid(db, auth_headers):
    """Test grok expansion with invalid pattern."""
    response = client.get(
        "/api/patterns/grok/expand",
        params={"pattern": "%{NONEXISTENT:field}"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "error" in data
