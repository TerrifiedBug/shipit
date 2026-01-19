#!/usr/bin/env python3
"""Download ECS schema from Elastic GitHub at build time."""
import json
import os
import sys
import urllib.request
from pathlib import Path

ECS_FLAT_URL = "https://raw.githubusercontent.com/elastic/ecs/main/generated/ecs/ecs_flat.yml"


def get_output_path() -> Path:
    """Get output path, handling both local dev and Docker build contexts."""
    # Check for environment variable override (useful for Docker)
    if env_path := os.environ.get("ECS_SCHEMA_OUTPUT"):
        return Path(env_path)

    script_dir = Path(__file__).parent.parent

    # Docker build context: /app/scripts/.. -> /app, output to /app/app/data/
    docker_path = script_dir / "app" / "data" / "ecs_schema.json"
    if docker_path.parent.exists():
        return docker_path

    # Local development: repo_root/backend/app/data/
    local_path = script_dir / "backend" / "app" / "data" / "ecs_schema.json"
    return local_path


def download_ecs_schema():
    """Download and convert ECS schema to JSON format."""
    try:
        import yaml
    except ImportError:
        print("PyYAML required. Install with: pip install pyyaml")
        sys.exit(1)

    output_path = get_output_path()
    print(f"Downloading ECS schema from {ECS_FLAT_URL}...")
    print(f"Output path: {output_path}")

    try:
        with urllib.request.urlopen(ECS_FLAT_URL, timeout=30) as response:
            content = response.read().decode("utf-8")
    except Exception as e:
        print(f"Failed to download ECS schema: {e}")
        print("Using existing bundled schema as fallback.")
        sys.exit(0)  # Don't fail build, use existing

    schema = yaml.safe_load(content)

    # Convert to our format: {field_name: {type, description}}
    ecs_fields = {}
    for field_name, field_data in schema.items():
        ecs_fields[field_name] = {
            "type": field_data.get("type", "keyword"),
            "description": field_data.get("description", ""),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(ecs_fields, f, indent=2)

    print(f"ECS schema saved to {output_path} ({len(ecs_fields)} fields)")


if __name__ == "__main__":
    download_ecs_schema()
