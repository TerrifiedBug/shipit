"""AI-assisted ECS field mapping service using OpenAI."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.services.ecs import ECS_SCHEMA

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are an expert at mapping log field names to Elastic Common Schema (ECS) fields.

Given these fields from a log file, suggest the most appropriate ECS field mapping for each.
Only suggest mappings you are confident about. If a field is ambiguous or unknown, omit it from your response.

Fields to map:
{fields_json}

Respond with a JSON object mapping original field names to ECS field names.
Only include fields you can confidently map. Example:
{{"fw_src_addr": "source.ip", "usr": "user.name", "bytes_out": "source.bytes"}}

Do not include explanations, only the JSON object."""


def is_ai_enabled() -> bool:
    """Check if AI-assisted mappings are enabled."""
    return bool(settings.openai_api_key)


def infer_type_hint(values: list[Any]) -> str:
    """Infer type hint from sample values."""
    if not values:
        return "unknown"

    sample = values[0]
    if sample is None:
        return "null"

    if isinstance(sample, bool):
        return "boolean"
    if isinstance(sample, int):
        return "integer"
    if isinstance(sample, float):
        return "float"
    if isinstance(sample, str):
        # Check for common patterns
        if _looks_like_ip(sample):
            return "ipv4" if "." in sample else "ipv6"
        if _looks_like_timestamp(sample):
            return "timestamp"
        if _looks_like_uuid(sample):
            return "uuid"
        return "string"

    return "unknown"


def _looks_like_ip(value: str) -> bool:
    """Check if value looks like an IP address."""
    ipv4_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    ipv6_pattern = r"^[0-9a-fA-F:]+$"
    return bool(re.match(ipv4_pattern, value) or (len(value) > 7 and re.match(ipv6_pattern, value)))


def _looks_like_timestamp(value: str) -> bool:
    """Check if value looks like a timestamp."""
    patterns = [
        r"^\d{4}-\d{2}-\d{2}",  # ISO date
        r"^\d{10,13}$",  # Unix timestamp
        r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}",  # Syslog
    ]
    return any(re.match(p, value) for p in patterns)


def _looks_like_uuid(value: str) -> bool:
    """Check if value looks like a UUID."""
    return bool(
        re.match(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
            value,
        )
    )


async def suggest_mappings_with_ai(fields: list[dict[str, str]]) -> dict[str, str]:
    """Get AI-suggested ECS mappings for fields.

    Args:
        fields: List of dicts with 'name' and 'type_hint' keys

    Returns:
        Dict mapping field names to suggested ECS fields
    """
    if not is_ai_enabled():
        return {}

    try:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        fields_json = json.dumps(fields, indent=2)
        prompt = PROMPT_TEMPLATE.format(fields_json=fields_json)

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON response - handle markdown code blocks
        if content.startswith("```"):
            # Extract JSON from code block
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        suggestions = json.loads(content)

        # Validate against ECS schema
        validated = {}
        for field_name, ecs_field in suggestions.items():
            if ecs_field in ECS_SCHEMA or ecs_field == "@timestamp" or ecs_field == "message":
                validated[field_name] = ecs_field
            else:
                logger.debug(f"AI suggested invalid ECS field: {ecs_field}")

        return validated

    except Exception as e:
        logger.warning(f"AI mapping suggestion failed: {e}")
        return {}
