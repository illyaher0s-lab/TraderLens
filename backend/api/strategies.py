"""
Strategies API - Read-only access to approved strategy library.

Red lines:
1. Read-only: no POST/PUT/DELETE endpoints
2. Returns only approved strategies (currently empty)
3. No fake strategies from templates or candidates
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("")
def list_strategies():
    """
    List approved strategies in the library.
    
    Current state: Empty - no approved strategies exist yet.
    
    Returns:
        {
            "strategies": [],
            "count": 0
        }
    """
    # Red line: No approved strategies exist yet
    # Do not fake strategies from templates or candidates
    return {
        "strategies": [],
        "count": 0,
    }
