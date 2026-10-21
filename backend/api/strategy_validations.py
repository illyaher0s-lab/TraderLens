"""
Strategy Validations API - Read-only access to validation cases.

Red lines:
1. Read-only: no POST/PUT/DELETE endpoints
2. Returns only real validation cases (currently empty)
3. No fake validation cases
"""

import json

from fastapi import APIRouter, HTTPException, Response

from backend.services.card017_validation_artifacts import (
    ARTIFACT_FILENAMES,
    Card017ArtifactsUnavailable,
    load_card017_artifacts as _load_card017_artifacts,
    unavailable_card017_historical_results,
)
from backend.services.strategy_validation_status import (
    DEFAULT_AUDIT_PATH,
    load_strategy_validation_status as _load_strategy_validation_status,
)

router = APIRouter(prefix="/api/strategy-validations", tags=["strategy_validations"])


def load_strategy_validation_status(
    audit_path=None,
    *,
    expected_sha256=None,
):
    """Test-injectable wrapper; production defaults remain hash-bound."""
    return _load_strategy_validation_status(audit_path, expected_sha256=expected_sha256)


def load_card017_artifacts():
    """Load the fixed, hash-bound Card 017 sources for the read-only API."""
    return _load_card017_artifacts()


@router.get("")
def list_validations():
    """
    List strategy validation cases.
    
    Current state: Empty - no validation cases exist yet.
    Only strategies that pass approved template mapping enter validation.
    
    Returns:
        {
            "validations": [],
            "count": 0
        }
    """
    # Red line: No validation cases exist yet
    # Do not fake validations from candidates or templates
    try:
        historical_results = load_card017_artifacts().historical_results
    except Card017ArtifactsUnavailable:
        historical_results = unavailable_card017_historical_results()

    return {
        "validations": [],
        "count": 0,
        "validation_status": load_strategy_validation_status(),
        "historical_results": historical_results,
    }


@router.get("/historical/card017/artifacts/{artifact_id}")
def download_card017_artifact(artifact_id: str):
    """Download one fixed verified source or the path-free provenance projection."""
    if artifact_id not in ARTIFACT_FILENAMES:
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        verified = load_card017_artifacts()
    except Card017ArtifactsUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="卡017来源暂不可验证，当前无法提供材料。",
        ) from exc

    if artifact_id == "summary_provenance":
        content = json.dumps(
            verified.historical_results["items"][0]["provenance"],
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        filename = "card017-summary-provenance-safe.json"
        media_type = "application/json"
    else:
        if artifact_id not in verified.safe_download_ids:
            raise HTTPException(status_code=503, detail="材料暂不可下载")
        content = verified.bytes_by_id[artifact_id]
        filename = ARTIFACT_FILENAMES[artifact_id]
        media_type = "text/markdown; charset=utf-8" if filename.endswith(".md") else None

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
