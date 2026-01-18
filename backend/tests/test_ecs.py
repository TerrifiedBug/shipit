# backend/tests/test_ecs.py
import pytest
from app.services.ecs import suggest_ecs_mappings, ECS_FIELD_MAP


class TestECSMapping:
    def test_suggest_source_ip(self):
        """Should suggest source.ip for common source IP fields."""
        fields = ["src_ip", "source_ip", "client_ip", "username", "action"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["src_ip"] == "source.ip"
        assert suggestions["source_ip"] == "source.ip"
        assert suggestions["client_ip"] == "source.ip"

    def test_suggest_destination_ip(self):
        """Should suggest destination.ip for common dest fields."""
        fields = ["dst_ip", "dest_ip", "server_ip"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["dst_ip"] == "destination.ip"
        assert suggestions["dest_ip"] == "destination.ip"

    def test_suggest_user_name(self):
        """Should suggest user.name for username fields."""
        fields = ["user", "username", "user_name", "login"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["user"] == "user.name"
        assert suggestions["username"] == "user.name"
        assert suggestions["user_name"] == "user.name"

    def test_no_suggestion_for_unknown_field(self):
        """Unknown fields should not get suggestions."""
        fields = ["custom_field", "my_data"]

        suggestions = suggest_ecs_mappings(fields)

        assert "custom_field" not in suggestions
        assert "my_data" not in suggestions

    def test_case_insensitive(self):
        """Field matching should be case-insensitive."""
        fields = ["SRC_IP", "Username", "MESSAGE"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["SRC_IP"] == "source.ip"
        assert suggestions["Username"] == "user.name"
        assert suggestions["MESSAGE"] == "message"

    def test_get_all_ecs_mappings(self):
        """Should return all available mappings."""
        from app.services.ecs import get_all_ecs_mappings

        all_mappings = get_all_ecs_mappings()

        assert "src_ip" in all_mappings
        assert all_mappings["src_ip"] == "source.ip"
