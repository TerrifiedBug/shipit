"""Tests for timestamp history functionality."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.database import add_timestamp_history, get_timestamp_history


client = TestClient(app)


class TestTimestampHistoryDatabase:
    """Tests for timestamp history database functions."""

    def test_add_timestamp_history(self, db):
        """Test adding a timestamp history entry."""
        result = add_timestamp_history(
            user_id="user123",
            source_field="created_at",
            format_string="%Y-%m-%d %H:%M:%S",
            target_field="@timestamp",
        )

        assert result["source_field"] == "created_at"
        assert result["format_string"] == "%Y-%m-%d %H:%M:%S"
        assert result["target_field"] == "@timestamp"

    def test_get_timestamp_history(self, db):
        """Test retrieving timestamp history."""
        # Add some history with small delays
        add_timestamp_history("user123", "field1", "format1")
        time.sleep(0.01)
        add_timestamp_history("user123", "field2", "format2")

        history = get_timestamp_history("user123")

        assert len(history) == 2

    def test_timestamp_history_limits_to_5(self, db):
        """Test that only 5 entries are kept per user."""
        for i in range(7):
            add_timestamp_history("user123", f"field{i}", f"format{i}")
            time.sleep(0.01)  # Small delay to ensure different timestamps

        history = get_timestamp_history("user123")

        assert len(history) == 5
        # Should have the 5 most recent (2-6)
        source_fields = [h["source_field"] for h in history]
        assert "field6" in source_fields
        assert "field5" in source_fields
        assert "field4" in source_fields
        assert "field3" in source_fields
        assert "field2" in source_fields
        # Oldest should be gone
        assert "field0" not in source_fields
        assert "field1" not in source_fields

    def test_timestamp_history_per_user(self, db):
        """Test that history is isolated per user."""
        add_timestamp_history("user1", "field_a", "format_a")
        add_timestamp_history("user2", "field_b", "format_b")

        history1 = get_timestamp_history("user1")
        history2 = get_timestamp_history("user2")

        assert len(history1) == 1
        assert len(history2) == 1
        assert history1[0]["source_field"] == "field_a"
        assert history2[0]["source_field"] == "field_b"


class TestTimestampHistoryEndpoint:
    """Tests for timestamp history API endpoint."""

    def _login(self, db):
        """Helper to setup and login, returns cookies."""
        client.post("/api/auth/setup", json={
            "email": "historytest@example.com",
            "password": "Password123",
            "name": "History Test User",
        })
        response = client.post("/api/auth/login", json={
            "email": "historytest@example.com",
            "password": "Password123",
        })
        return response.cookies

    def test_get_timestamp_history_endpoint(self, db):
        """Test the timestamp history API endpoint."""
        cookies = self._login(db)

        response = client.get("/api/timestamp-history", cookies=cookies)

        assert response.status_code == 200
        assert "history" in response.json()
        assert isinstance(response.json()["history"], list)

    def test_timestamp_history_requires_auth(self, db):
        """Test that timestamp history endpoint requires authentication."""
        response = client.get("/api/timestamp-history")
        assert response.status_code == 401
