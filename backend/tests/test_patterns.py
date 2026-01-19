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


# =============================================================================
# parse_grok_file tests
# =============================================================================

from app.services.grok_patterns import parse_grok_file


def test_parse_grok_file_basic():
    """Parse simple grok pattern file."""
    content = """# Comment line
WORD \\w+
NUMBER \\d+
"""
    patterns, errors = parse_grok_file(content)

    assert len(patterns) == 2
    assert patterns[0] == ("WORD", "\\w+")
    assert patterns[1] == ("NUMBER", "\\d+")
    assert len(errors) == 0


def test_parse_grok_file_skips_comments_and_blanks():
    """Comments and blank lines are skipped."""
    content = """# Header comment

PATTERN1 value1
# Middle comment

PATTERN2 value2
"""
    patterns, errors = parse_grok_file(content)

    assert len(patterns) == 2
    assert len(errors) == 0


def test_parse_grok_file_reports_invalid_lines():
    """Lines without whitespace separator are errors."""
    content = """VALID pattern
INVALID_NO_SPACE
ALSO_VALID another pattern
"""
    patterns, errors = parse_grok_file(content)

    assert len(patterns) == 2
    assert len(errors) == 1
    assert "Line 2" in errors[0]


def test_parse_grok_file_handles_tabs():
    """Tab separator should work."""
    content = "PATTERN\tvalue with spaces"
    patterns, errors = parse_grok_file(content)

    assert len(patterns) == 1
    assert patterns[0] == ("PATTERN", "value with spaces")


# =============================================================================
# Import endpoint tests
# =============================================================================


def test_import_grok_patterns(db, auth_headers):
    """Import multiple grok patterns from file content."""
    content = """# Cisco ASA patterns
CISCO_ACTION Built|Teardown|Deny
CISCO_REASON reason\\s+\\S+
"""
    response = client.post(
        "/api/patterns/grok/import",
        json={"content": content, "overwrite": False},
        headers=auth_headers
    )

    assert response.status_code == 200
    result = response.json()
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert len(result["errors"]) == 0


def test_import_grok_patterns_skips_duplicates(db, auth_headers):
    """Duplicate patterns are skipped by default."""
    # First import
    content = "TEST_IMPORT_PATTERN value1"
    client.post(
        "/api/patterns/grok/import",
        json={"content": content},
        headers=auth_headers
    )

    # Second import with same name
    response = client.post(
        "/api/patterns/grok/import",
        json={"content": content, "overwrite": False},
        headers=auth_headers
    )

    result = response.json()
    assert result["imported"] == 0
    assert result["skipped"] == 1


def test_import_grok_patterns_with_overwrite(db, auth_headers):
    """Patterns can be overwritten when overwrite=True."""
    # First import
    content = "TEST_OVERWRITE_PATTERN value1"
    client.post(
        "/api/patterns/grok/import",
        json={"content": content},
        headers=auth_headers
    )

    # Second import with overwrite=True and different value
    content = "TEST_OVERWRITE_PATTERN value2"
    response = client.post(
        "/api/patterns/grok/import",
        json={"content": content, "overwrite": True},
        headers=auth_headers
    )

    result = response.json()
    assert result["imported"] == 1
    assert result["skipped"] == 0

    # Verify the pattern was updated
    get_response = client.get(
        "/api/patterns/grok",
        headers=auth_headers
    )
    patterns = get_response.json()
    matching = [p for p in patterns if p["name"] == "TEST_OVERWRITE_PATTERN"]
    assert len(matching) == 1
    assert matching[0]["regex"] == "value2"


def test_import_grok_patterns_with_parse_errors(db, auth_headers):
    """Parse errors are reported in the response."""
    content = """VALID_PATTERN value
INVALID_NO_SPACE
ANOTHER_VALID another value
"""
    response = client.post(
        "/api/patterns/grok/import",
        json={"content": content},
        headers=auth_headers
    )

    assert response.status_code == 200
    result = response.json()
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert len(result["errors"]) == 1
    assert "Line 2" in result["errors"][0]
