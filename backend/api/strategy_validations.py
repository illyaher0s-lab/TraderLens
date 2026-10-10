"""
Strategy Validations API - Read-only access to validation cases.

Red lines:
1. Read-only: no POST/PUT/DELETE endpoints
2. Returns only real validation cases (currently empty)
3. No fake validation cases
"""

from fastapi import APIRouter

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
    return {
        "validations": [],
        "count": 0,
        "validation_status": load_strategy_validation_status(),
    }
