"""Tests for AI-assisted ECS mapping service."""
from unittest.mock import patch

import pytest

from app.services.ai_mappings import infer_type_hint, is_ai_enabled


class TestInferTypeHint:
    """Tests for type hint inference."""

    def test_infer_type_hint_ipv4(self):
        assert infer_type_hint(["192.168.1.1"]) == "ipv4"

    def test_infer_type_hint_string(self):
        assert infer_type_hint(["hello"]) == "string"

    def test_infer_type_hint_integer(self):
        assert infer_type_hint([42]) == "integer"

    def test_infer_type_hint_float(self):
        assert infer_type_hint([3.14]) == "float"

    def test_infer_type_hint_boolean(self):
        assert infer_type_hint([True]) == "boolean"

    def test_infer_type_hint_empty(self):
        assert infer_type_hint([]) == "unknown"

    def test_infer_type_hint_none(self):
        assert infer_type_hint([None]) == "null"

    def test_infer_type_hint_timestamp_iso(self):
        assert infer_type_hint(["2024-01-15T10:30:00Z"]) == "timestamp"

    def test_infer_type_hint_uuid(self):
        assert infer_type_hint(["550e8400-e29b-41d4-a716-446655440000"]) == "uuid"


class TestIsAiEnabled:
    """Tests for AI enabled check."""

    @patch("app.services.ai_mappings.settings")
    def test_is_ai_enabled_false(self, mock_settings):
        mock_settings.openai_api_key = None
        assert is_ai_enabled() is False

    @patch("app.services.ai_mappings.settings")
    def test_is_ai_enabled_true(self, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        assert is_ai_enabled() is True

    @patch("app.services.ai_mappings.settings")
    def test_is_ai_enabled_empty_string(self, mock_settings):
        mock_settings.openai_api_key = ""
        assert is_ai_enabled() is False
