"""Patterns API router for managing custom parsing patterns and grok patterns."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.auth import require_auth
from app.services import database
from app.services.grok_patterns import (
    list_builtin_patterns,
    validate_grok_pattern,
    validate_regex_pattern,
    parse_with_grok,
    safe_regex_match,
    RegexTimeoutError,
    expand_grok,
    parse_grok_file,
)

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


# =============================================================================
# Request/Response Models
# =============================================================================


class PatternCreate(BaseModel):
    """Request model for creating a custom pattern."""
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(regex|grok)$")
    pattern: str = Field(..., min_length=1)
    description: str | None = None
    test_sample: str | None = None


class PatternUpdate(BaseModel):
    """Request model for updating a custom pattern."""
    name: str | None = Field(None, min_length=1, max_length=100)
    type: str | None = Field(None, pattern="^(regex|grok)$")
    pattern: str | None = Field(None, min_length=1)
    description: str | None = None
    test_sample: str | None = None


class PatternResponse(BaseModel):
    """Response model for a custom pattern."""
    id: str
    name: str
    type: str
    pattern: str
    description: str | None
    test_sample: str | None
    created_by: str
    created_at: str
    updated_at: str


class GrokPatternCreate(BaseModel):
    """Request model for creating a grok pattern component."""
    name: str = Field(..., min_length=1, max_length=50, pattern="^[A-Z][A-Z0-9_]*$")
    regex: str = Field(..., min_length=1)
    description: str | None = None


class GrokPatternUpdate(BaseModel):
    """Request model for updating a grok pattern component."""
    regex: str | None = Field(None, min_length=1)
    description: str | None = None


class GrokPatternResponse(BaseModel):
    """Response model for a grok pattern component."""
    id: str
    name: str
    regex: str
    description: str | None
    created_by: str
    created_at: str
    updated_at: str
    builtin: bool = False


class BuiltinGrokPattern(BaseModel):
    """Response model for a built-in grok pattern."""
    name: str
    regex: str
    description: str
    builtin: bool = True


class PatternTestRequest(BaseModel):
    """Request model for testing a pattern against sample text."""
    pattern: str
    pattern_type: str = Field(..., pattern="^(regex|grok)$")
    test_text: str


class PatternTestResponse(BaseModel):
    """Response model for pattern test results."""
    success: bool
    matches: dict | None = None
    error: str | None = None


class GrokImportRequest(BaseModel):
    """Request model for bulk importing grok patterns."""
    content: str
    overwrite: bool = False


class GrokImportResult(BaseModel):
    """Response model for bulk grok pattern import."""
    imported: int
    skipped: int
    errors: list[str]


# =============================================================================
# Custom Patterns Endpoints (non-parameterized routes first)
# =============================================================================


@router.get("")
async def list_patterns(
    user: dict = Depends(require_auth),
) -> list[PatternResponse]:
    """List all custom patterns."""
    patterns = database.list_patterns()
    return [PatternResponse(**p) for p in patterns]


@router.post("", status_code=201)
async def create_pattern(
    data: PatternCreate,
    user: dict = Depends(require_auth),
) -> PatternResponse:
    """Create a new custom pattern."""
    # Validate the pattern
    if data.type == "grok":
        is_valid, error = validate_grok_pattern(data.pattern)
    else:
        is_valid, error = validate_regex_pattern(data.pattern)

    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid pattern: {error}")

    pattern = database.create_pattern(
        name=data.name,
        pattern_type=data.type,
        pattern=data.pattern,
        user_id=user["email"],
        description=data.description,
        test_sample=data.test_sample,
    )

    if not pattern:
        raise HTTPException(status_code=500, detail="Failed to create pattern")

    return PatternResponse(**pattern)


@router.post("/test")
async def test_pattern(
    data: PatternTestRequest,
    user: dict = Depends(require_auth),
) -> PatternTestResponse:
    """Test a pattern against sample text."""
    try:
        if data.pattern_type == "grok":
            result = parse_with_grok(data.test_text, data.pattern)
            if result:
                return PatternTestResponse(success=True, matches=result)
            else:
                return PatternTestResponse(success=False, error="Pattern did not match")
        else:
            # Regex pattern - use safe_regex_match for ReDoS protection
            is_valid, error = validate_regex_pattern(data.pattern)
            if not is_valid:
                return PatternTestResponse(success=False, error=error)

            match = safe_regex_match(data.pattern, data.test_text)
            if match:
                return PatternTestResponse(success=True, matches=match.groupdict())
            else:
                return PatternTestResponse(success=False, error="Pattern did not match")

    except RegexTimeoutError:
        return PatternTestResponse(
            success=False,
            error="Pattern matching timed out - the pattern may be too complex"
        )
    except Exception as e:
        return PatternTestResponse(success=False, error=str(e))


# =============================================================================
# Grok Pattern Components Endpoints (must come before /{pattern_id} routes)
# =============================================================================


@router.get("/grok/builtin")
async def list_builtin_grok_patterns(
    user: dict = Depends(require_auth),
) -> list[BuiltinGrokPattern]:
    """List all built-in grok patterns."""
    patterns = list_builtin_patterns()
    return [BuiltinGrokPattern(**p) for p in patterns]


@router.get("/grok/expand")
async def expand_grok_pattern(
    pattern: str,
    user: dict = Depends(require_auth),
) -> dict:
    """Expand a grok pattern to regex for client-side matching."""
    try:
        expanded = expand_grok(pattern)
        # Extract named groups from the expanded regex
        groups = re.findall(r'\?P<(\w+)>', expanded)
        return {"expanded": expanded, "groups": groups, "valid": True}
    except ValueError as e:
        # Sanitize error message - never expose raw exception details
        error_msg = str(e)
        # Construct safe error messages without exposing exception content
        if "Unknown grok pattern" in error_msg or "Unknown pattern" in error_msg:
            # Don't pass through error_msg - use static safe message
            safe_error = "Unknown grok pattern referenced in expression"
        else:
            safe_error = "Invalid grok pattern syntax"
        return {"expanded": None, "groups": [], "valid": False, "error": safe_error}


@router.get("/grok")
async def list_grok_patterns(
    user: dict = Depends(require_auth),
) -> list[GrokPatternResponse]:
    """List all custom grok pattern components."""
    patterns = database.list_grok_patterns()
    return [GrokPatternResponse(**p) for p in patterns]


@router.post("/grok", status_code=201)
async def create_grok_pattern(
    data: GrokPatternCreate,
    user: dict = Depends(require_auth),
) -> GrokPatternResponse:
    """Create a new custom grok pattern component."""
    # Check if name conflicts with built-in
    builtins = {p["name"] for p in list_builtin_patterns()}
    if data.name in builtins:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot override built-in pattern: {data.name}"
        )

    # Check if name already exists
    existing = database.get_grok_pattern_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Grok pattern with name '{data.name}' already exists"
        )

    # Validate the regex
    is_valid, error = validate_regex_pattern(data.regex)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {error}")

    pattern = database.create_grok_pattern(
        name=data.name,
        regex=data.regex,
        user_id=user["email"],
        description=data.description,
    )

    if not pattern:
        raise HTTPException(status_code=500, detail="Failed to create grok pattern")

    return GrokPatternResponse(**pattern)


@router.post("/grok/import", response_model=GrokImportResult)
async def import_grok_patterns(
    request: GrokImportRequest,
    user: dict = Depends(require_auth),
) -> GrokImportResult:
    """Import multiple grok patterns from file content.

    Parses grok pattern file format (PATTERN_NAME<whitespace>pattern_expression).
    Lines starting with # are comments, blank lines are skipped.

    Args:
        request: Contains the file content and overwrite flag

    Returns:
        Import result with counts of imported, skipped patterns and any parse errors
    """
    patterns, parse_errors = parse_grok_file(request.content)

    imported = 0
    skipped = 0

    for name, regex in patterns:
        # Check if pattern exists
        existing = database.get_grok_pattern_by_name(name)

        if existing:
            if request.overwrite:
                database.update_grok_pattern(existing["id"], regex=regex)
                imported += 1
            else:
                skipped += 1
        else:
            database.create_grok_pattern(name, regex, user["email"])
            imported += 1

    return GrokImportResult(
        imported=imported,
        skipped=skipped,
        errors=parse_errors
    )


@router.get("/grok/{pattern_id}")
async def get_grok_pattern(
    pattern_id: str,
    user: dict = Depends(require_auth),
) -> GrokPatternResponse:
    """Get a specific custom grok pattern component."""
    pattern = database.get_grok_pattern(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Grok pattern not found")

    return GrokPatternResponse(**pattern)


@router.put("/grok/{pattern_id}")
async def update_grok_pattern(
    pattern_id: str,
    data: GrokPatternUpdate,
    user: dict = Depends(require_auth),
) -> GrokPatternResponse:
    """Update a custom grok pattern component."""
    existing = database.get_grok_pattern(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Grok pattern not found")

    # Validate the regex if being updated
    if data.regex:
        is_valid, error = validate_regex_pattern(data.regex)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {error}")

    updated = database.update_grok_pattern(
        pattern_id=pattern_id,
        regex=data.regex,
        description=data.description,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update grok pattern")

    return GrokPatternResponse(**updated)


@router.delete("/grok/{pattern_id}", status_code=204)
async def delete_grok_pattern(
    pattern_id: str,
    user: dict = Depends(require_auth),
) -> None:
    """Delete a custom grok pattern component."""
    existing = database.get_grok_pattern(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Grok pattern not found")

    database.delete_grok_pattern(pattern_id)


# =============================================================================
# Parameterized Pattern Routes (must come LAST to avoid catching /test, /grok)
# =============================================================================


@router.get("/{pattern_id}")
async def get_pattern(
    pattern_id: str,
    user: dict = Depends(require_auth),
) -> PatternResponse:
    """Get a specific custom pattern."""
    pattern = database.get_pattern(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    return PatternResponse(**pattern)


@router.put("/{pattern_id}")
async def update_pattern(
    pattern_id: str,
    data: PatternUpdate,
    user: dict = Depends(require_auth),
) -> PatternResponse:
    """Update a custom pattern."""
    existing = database.get_pattern(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # Validate the pattern if being updated
    pattern_type = data.type if data.type else existing["type"]
    pattern_str = data.pattern if data.pattern else existing["pattern"]

    if data.pattern:
        if pattern_type == "grok":
            is_valid, error = validate_grok_pattern(pattern_str)
        else:
            is_valid, error = validate_regex_pattern(pattern_str)

        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid pattern: {error}")

    updated = database.update_pattern(
        pattern_id=pattern_id,
        name=data.name,
        type=data.type,
        pattern=data.pattern,
        description=data.description,
        test_sample=data.test_sample,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update pattern")

    return PatternResponse(**updated)


@router.delete("/{pattern_id}", status_code=204)
async def delete_pattern(
    pattern_id: str,
    user: dict = Depends(require_auth),
) -> None:
    """Delete a custom pattern."""
    existing = database.get_pattern(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pattern not found")

    database.delete_pattern(pattern_id)
