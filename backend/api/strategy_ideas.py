"""
Strategy Ideas API

REST endpoints for strategy idea flow.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.strategy_idea_flow import StrategyIdeaFlowService


router = APIRouter(prefix="/api/strategy-ideas", tags=["strategy-ideas"])
flow_service = StrategyIdeaFlowService()


class CreateIdeaRequest(BaseModel):
    """Create idea request."""
    raw_source_text: str
    source_channel: str


class ValidateIdeaRequest(BaseModel):
    """Validate idea request."""
    pass  # Trigger validation


@router.post("")
def create_idea(request: CreateIdeaRequest):
    """
    Create strategy idea (defaults to untrusted).
    
    Red line 1: Defaults to untrusted, no signals.
    """
    idea = flow_service.create_idea(
        raw_source_text=request.raw_source_text,
        source_channel=request.source_channel,
    )
    
    return {
        "idea_id": idea.idea_id,
        "trust_status": idea.trust_status.value,
        "source_channel": idea.source_channel,
    }


@router.get("/{idea_id}")
def get_idea(idea_id: str):
    """Get strategy idea status and full chain."""
    # Placeholder - would fetch from DB
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{idea_id}/validate")
def validate_idea(idea_id: str, request: ValidateIdeaRequest):
    """
    Trigger validation path (template mapping/candidate evaluation).
    
    Red line 3: Not direct approval, goes through validation.
    """
    # Placeholder - would trigger validation flow
    raise HTTPException(status_code=501, detail="Not implemented")
