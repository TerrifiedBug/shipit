# backend/tests/test_ecs.py
import pytest
from app.services.ecs import (
    suggest_ecs_mappings,
    get_ecs_field_type,
    get_all_ecs_fields,
    get_all_ecs_mappings,
    SAFE_ECS_MAPPINGS,
    ECS_SCHEMA,
    ECS_FIELD_MAP,
)


class TestECSSchema:
    """Tests for ECS schema loading and structure."""

    def test_ecs_schema_loads(self):
        """ECS schema should load from JSON file."""
        assert len(ECS_SCHEMA) > 50  # Has many fields
        assert "source.ip" in ECS_SCHEMA
        assert ECS_SCHEMA["source.ip"]["type"] == "ip"

    def test_ecs_schema_has_required_fields(self):
        """ECS schema should include core field categories."""
        # Base fields
        assert "@timestamp" in ECS_SCHEMA
        assert "message" in ECS_SCHEMA

        # Source fields
        assert "source.ip" in ECS_SCHEMA
        assert "source.port" in ECS_SCHEMA
        assert "source.geo.country_name" in ECS_SCHEMA

        # Destination fields
        assert "destination.ip" in ECS_SCHEMA
        assert "destination.port" in ECS_SCHEMA

        # Event fields
        assert "event.action" in ECS_SCHEMA
        assert "event.category" in ECS_SCHEMA

        # Host fields
        assert "host.name" in ECS_SCHEMA
        assert "host.ip" in ECS_SCHEMA

        # HTTP fields
        assert "http.request.method" in ECS_SCHEMA
        assert "http.response.status_code" in ECS_SCHEMA

        # User fields
        assert "user.name" in ECS_SCHEMA
        assert "user.id" in ECS_SCHEMA

    def test_ecs_schema_field_structure(self):
        """Each ECS field should have type and description."""
        for field_name, field_info in ECS_SCHEMA.items():
            assert "type" in field_info, f"Field {field_name} missing type"
            assert "description" in field_info, f"Field {field_name} missing description"

    def test_ecs_schema_field_types(self):
        """ECS schema should use valid Elasticsearch field types."""
        # Official ECS schema uses full range of Elasticsearch types
        valid_types = {
            "boolean",
            "constant_keyword",
            "date",
            "double",
            "flattened",
            "float",
            "geo_point",
            "integer",
            "ip",
            "keyword",
            "long",
            "match_only_text",
            "nested",
            "object",
            "scaled_float",
            "text",
            "wildcard",
        }
        for field_name, field_info in ECS_SCHEMA.items():
            assert field_info["type"] in valid_types, (
                f"Field {field_name} has invalid type: {field_info['type']}"
            )


class TestAmbiguousMappings:
    """Tests to verify ambiguous mappings are removed."""

    def test_ambiguous_mappings_removed(self):
        """Ambiguous mappings should not be in SAFE_ECS_MAPPINGS."""
        assert "remote_ip" not in SAFE_ECS_MAPPINGS
        assert "server_ip" not in SAFE_ECS_MAPPINGS
        assert "host" not in SAFE_ECS_MAPPINGS

    def test_ambiguous_remote_addr_removed(self):
        """remote_addr should also be removed as ambiguous."""
        assert "remote_addr" not in SAFE_ECS_MAPPINGS

    def test_ambiguous_server_removed(self):
        """server should also be removed as ambiguous."""
        assert "server" not in SAFE_ECS_MAPPINGS

    def test_ambiguous_port_removed(self):
        """Generic 'port' should be removed as ambiguous."""
        assert "port" not in SAFE_ECS_MAPPINGS


class TestSuggestEcsMappings:
    """Tests for the suggest_ecs_mappings function."""

    def test_suggest_ecs_mappings_unambiguous(self):
        """Should suggest mappings for unambiguous field names."""
        suggestions = suggest_ecs_mappings(["src_ip", "dst_ip", "username"])

        assert suggestions["src_ip"] == "source.ip"
        assert suggestions["dst_ip"] == "destination.ip"
        assert suggestions["username"] == "user.name"

    def test_suggest_ecs_mappings_no_ambiguous(self):
        """Should NOT suggest mappings for ambiguous field names."""
        suggestions = suggest_ecs_mappings(["remote_ip", "server_ip", "host"])

        assert "remote_ip" not in suggestions
        assert "server_ip" not in suggestions
        assert "host" not in suggestions

    def test_suggest_source_ip(self):
        """Should suggest source.ip for common source IP fields."""
        fields = ["src_ip", "source_ip", "client_ip", "username", "action"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["src_ip"] == "source.ip"
        assert suggestions["source_ip"] == "source.ip"
        assert suggestions["client_ip"] == "source.ip"

    def test_suggest_destination_ip(self):
        """Should suggest destination.ip for common dest fields."""
        fields = ["dst_ip", "dest_ip", "target_ip"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["dst_ip"] == "destination.ip"
        assert suggestions["dest_ip"] == "destination.ip"
        assert suggestions["target_ip"] == "destination.ip"

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

    def test_suggest_http_fields(self):
        """Should suggest HTTP-related ECS mappings."""
        fields = ["http_method", "status_code", "referrer", "user_agent"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["http_method"] == "http.request.method"
        assert suggestions["status_code"] == "http.response.status_code"
        assert suggestions["referrer"] == "http.request.referrer"
        assert suggestions["user_agent"] == "user_agent.original"

    def test_suggest_url_fields(self):
        """Should suggest URL-related ECS mappings."""
        fields = ["url", "url_path", "query_string"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["url"] == "url.full"
        assert suggestions["url_path"] == "url.path"
        assert suggestions["query_string"] == "url.query"

    def test_suggest_log_fields(self):
        """Should suggest log-related ECS mappings."""
        fields = ["log_level", "level", "logger"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["log_level"] == "log.level"
        assert suggestions["level"] == "log.level"
        assert suggestions["logger"] == "log.logger"

    def test_suggest_process_fields(self):
        """Should suggest process-related ECS mappings."""
        fields = ["pid", "process_name", "command_line"]

        suggestions = suggest_ecs_mappings(fields)

        assert suggestions["pid"] == "process.pid"
        assert suggestions["process_name"] == "process.name"
        assert suggestions["command_line"] == "process.command_line"


class TestGetEcsFieldType:
    """Tests for the get_ecs_field_type function."""

    def test_get_ecs_field_type(self):
        """Should return correct type for ECS fields."""
        assert get_ecs_field_type("source.ip") == "ip"
        assert get_ecs_field_type("source.port") == "long"
        # Official ECS schema uses match_only_text for message field
        assert get_ecs_field_type("message") == "match_only_text"
        assert get_ecs_field_type("not.a.field") is None

    def test_get_ecs_field_type_various(self):
        """Should return correct types for various ECS fields."""
        assert get_ecs_field_type("@timestamp") == "date"
        assert get_ecs_field_type("event.action") == "keyword"
        assert get_ecs_field_type("host.name") == "keyword"
        assert get_ecs_field_type("source.geo.location") == "geo_point"
        assert get_ecs_field_type("labels") == "object"

    def test_get_ecs_field_type_not_found(self):
        """Should return None for unknown fields."""
        assert get_ecs_field_type("unknown.field") is None
        assert get_ecs_field_type("") is None
        assert get_ecs_field_type("source.unknown") is None


class TestGetAllEcsFields:
    """Tests for the get_all_ecs_fields function."""

    def test_get_all_ecs_fields(self):
        """Should return all ECS fields from schema."""
        all_fields = get_all_ecs_fields()

        assert len(all_fields) > 50
        assert "source.ip" in all_fields
        assert "destination.ip" in all_fields
        assert "message" in all_fields

    def test_get_all_ecs_fields_returns_copy(self):
        """Should return a copy, not the original dict."""
        all_fields = get_all_ecs_fields()
        all_fields["test.field"] = {"type": "keyword"}

        # Original should not be modified
        assert "test.field" not in ECS_SCHEMA


class TestGetAllEcsMappings:
    """Tests for the get_all_ecs_mappings function."""

    def test_get_all_ecs_mappings(self):
        """Should return all available mappings."""
        all_mappings = get_all_ecs_mappings()

        assert "src_ip" in all_mappings
        assert all_mappings["src_ip"] == "source.ip"

    def test_get_all_ecs_mappings_excludes_ambiguous(self):
        """Returned mappings should not include ambiguous fields."""
        all_mappings = get_all_ecs_mappings()

        assert "remote_ip" not in all_mappings
        assert "server_ip" not in all_mappings
        assert "host" not in all_mappings


class TestBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_ecs_field_map_alias(self):
        """ECS_FIELD_MAP should be an alias for SAFE_ECS_MAPPINGS."""
        assert ECS_FIELD_MAP is SAFE_ECS_MAPPINGS

    def test_ecs_field_map_has_mappings(self):
        """ECS_FIELD_MAP should have the expected mappings."""
        assert ECS_FIELD_MAP["src_ip"] == "source.ip"
        assert ECS_FIELD_MAP["dst_ip"] == "destination.ip"
        assert ECS_FIELD_MAP["username"] == "user.name"
