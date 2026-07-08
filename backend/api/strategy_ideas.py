"""
Strategy Ideas API

REST endpoints for strategy idea flow.
"""

import json
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


@router.get("")
def list_ideas(conversation_id: str = None, candidate_status: str = None):
    """
    List strategy ideas, optionally filtered by conversation_id or candidate_status.
    
    Queries agent_artifact_refs for strategy_idea artifacts.
    
    Optimized: Uses JOIN queries to avoid N+1 problem.
    """
    import sqlite3
    from pathlib import Path
    
    db_path = Path(__file__).parent.parent.parent / "data" / "research.db"
    
    if not db_path.exists():
        return {"ideas": []}
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Query strategy_idea artifacts with all related data in one query
        # Use subqueries to avoid cartesian product from multiple user messages per session
        if conversation_id:
            cursor.execute("""
                SELECT 
                    i.artifact_id as idea_id,
                    i.session_id,
                    i.created_at,
                    e.artifact_id as extraction_artifact_id,
                    e.content as extraction_content,
                    m.artifact_id as mapping_artifact_id,
                    m.content as mapping_content,
                    r.content as rejection_content,
                    (SELECT content FROM agent_messages 
                     WHERE session_id = i.session_id AND role = 'user' 
                     ORDER BY created_at ASC LIMIT 1) as original_message
                FROM agent_artifact_refs i
                LEFT JOIN agent_artifact_refs e 
                    ON i.session_id = e.session_id 
                    AND e.artifact_type = 'strategy_idea_extraction'
                LEFT JOIN agent_artifact_refs m 
                    ON i.session_id = m.session_id 
                    AND m.artifact_type = 'strategy_template_mapping'
                LEFT JOIN agent_artifact_refs r 
                    ON i.session_id = r.session_id 
                    AND r.artifact_type = 'strategy_idea_rejected'
                WHERE i.artifact_type = 'strategy_idea'
                  AND i.session_id = ?
                ORDER BY i.created_at DESC
            """, (conversation_id,))
        else:
            cursor.execute("""
                SELECT 
                    i.artifact_id as idea_id,
                    i.session_id,
                    i.created_at,
                    e.artifact_id as extraction_artifact_id,
                    e.content as extraction_content,
                    m.artifact_id as mapping_artifact_id,
                    m.content as mapping_content,
                    r.content as rejection_content,
                    (SELECT content FROM agent_messages 
                     WHERE session_id = i.session_id AND role = 'user' 
                     ORDER BY created_at ASC LIMIT 1) as original_message
                FROM agent_artifact_refs i
                LEFT JOIN agent_artifact_refs e 
                    ON i.session_id = e.session_id 
                    AND e.artifact_type = 'strategy_idea_extraction'
                LEFT JOIN agent_artifact_refs m 
                    ON i.session_id = m.session_id 
                    AND m.artifact_type = 'strategy_template_mapping'
                LEFT JOIN agent_artifact_refs r 
                    ON i.session_id = r.session_id 
                    AND r.artifact_type = 'strategy_idea_rejected'
                WHERE i.artifact_type = 'strategy_idea'
                ORDER BY i.created_at DESC
            """)
        
        rows = cursor.fetchall()
        ideas = []
        
        for row in rows:
            # Parse extraction data
            extraction = {}
            if row["extraction_content"]:
                try:
                    extraction = json.loads(row["extraction_content"])
                except json.JSONDecodeError:
                    pass
            
            # Parse mapping data
            mapping = {}
            if row["mapping_content"]:
                try:
                    mapping = json.loads(row["mapping_content"])
                except json.JSONDecodeError:
                    pass
            
            # Parse rejection data
            rejection_data = {}
            if row["rejection_content"]:
                try:
                    rejection_data = json.loads(row["rejection_content"])
                except json.JSONDecodeError:
                    pass
            
            decision = "rejected" if row["rejection_content"] else "accepted"
            rejection_reason = rejection_data.get("rejection_reason", "unknown") if rejection_data else None
            
            ideas.append({
                "idea_id": row["idea_id"],
                "conversation_id": row["session_id"],
                "workflow_type": "strategy_idea",
                "original_message": row["original_message"] or "",
                "claimed_entry": extraction.get("claimed_entry", "未提取") if extraction else "未提取",
                "claimed_exit": extraction.get("claimed_exit", "未提取") if extraction else "未提取",
                "claimed_edge": extraction.get("claimed_edge", "未提取") if extraction else "未提取",
                "decision": decision,
                "path_type": mapping.get("path_type", "unknown") if mapping else "unknown",
                "rejection_reason": rejection_reason,
                "mapping_artifact_id": row["mapping_artifact_id"],
                "extraction_artifact_id": row["extraction_artifact_id"],
                "mapped_template_id": mapping.get("matched_template_id") if mapping else None,
                "template_version": mapping.get("template_version") if mapping else None,
                "considered_template_ids": mapping.get("considered_template_ids", []) if mapping else [],
                "mismatch_reasons": mapping.get("mismatch_reasons", {}) if mapping else {},
                "final_reason": mapping.get("final_reason") if mapping else None,
                "live_eligible": mapping.get("live_eligible", False) if mapping else False,
                "candidate_status": mapping.get("candidate_status") if mapping else None,
                "candidate_reason": mapping.get("candidate_reason") if mapping else None,
                "required_next_step": mapping.get("required_next_step") if mapping else None,
                "created_at": row["created_at"],
            })
        
        # Filter by candidate_status if provided
        if candidate_status:
            ideas = [idea for idea in ideas if idea.get("candidate_status") == candidate_status]
        
        return {"ideas": ideas}
        
    finally:
        conn.close()


@router.get("/{idea_id}")
def get_idea(idea_id: str):
    """
    Get strategy idea detail with full artifact chain.
    
    Returns: idea, extraction, mapping, rejection (if exists).
    """
    import sqlite3
    from pathlib import Path
    
    db_path = Path(__file__).parent.parent.parent / "data" / "research.db"
    
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database not found")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Get idea artifact
        cursor.execute("""
            SELECT artifact_id, session_id, content, created_at
            FROM agent_artifact_refs
            WHERE artifact_id = ? AND artifact_type = 'strategy_idea'
        """, (idea_id,))
        
        idea_row = cursor.fetchone()
        if not idea_row:
            raise HTTPException(status_code=404, detail="Strategy idea not found")
        
        session_id = idea_row["session_id"]
        created_at = idea_row["created_at"]
        
        # Get extraction
        cursor.execute("""
            SELECT artifact_id, content, created_at FROM agent_artifact_refs
            WHERE session_id = ? AND artifact_type = 'strategy_idea_extraction'
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        extraction_row = cursor.fetchone()
        extraction = json.loads(extraction_row["content"]) if extraction_row and extraction_row["content"] else None
        
        # Get mapping
        cursor.execute("""
            SELECT artifact_id, content, created_at FROM agent_artifact_refs
            WHERE session_id = ? AND artifact_type = 'strategy_template_mapping'
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        mapping_row = cursor.fetchone()
        mapping = json.loads(mapping_row["content"]) if mapping_row and mapping_row["content"] else None
        
        # Get rejection (if exists)
        cursor.execute("""
            SELECT artifact_id, content, created_at FROM agent_artifact_refs
            WHERE session_id = ? AND artifact_type = 'strategy_idea_rejected'
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        rejection_row = cursor.fetchone()
        rejection = json.loads(rejection_row["content"]) if rejection_row and rejection_row["content"] else None
        
        # Get original message
        cursor.execute("""
            SELECT content FROM agent_messages
            WHERE session_id = ? AND role = 'user'
            ORDER BY created_at ASC LIMIT 1
        """, (session_id,))
        message_row = cursor.fetchone()
        original_message = message_row["content"] if message_row else ""
        
        # Get agent reply
        cursor.execute("""
            SELECT content FROM agent_messages
            WHERE session_id = ? AND role = 'assistant'
            ORDER BY created_at DESC LIMIT 1
        """, (session_id,))
        reply_row = cursor.fetchone()
        agent_reply = reply_row["content"] if reply_row else ""
        
        # Extract artifact IDs
        extraction_artifact_id = extraction_row["artifact_id"] if extraction_row else None
        mapping_artifact_id = mapping_row["artifact_id"] if mapping_row else None
        rejection_artifact_id = rejection_row["artifact_id"] if rejection_row else None
        
        # Extract key fields from artifacts
        rejection_reason = rejection.get("rejection_reason") if rejection else None
        mapped_template_id = mapping.get("matched_template_id") if mapping else None
        template_version = mapping.get("template_version") if mapping else None
        path_type = mapping.get("path_type") if mapping else "unknown"
        mapping_reason = mapping.get("mapping_reason") if mapping else None
        
        return {
            "idea_id": idea_id,
            "conversation_id": session_id,
            "workflow_type": "strategy_idea",
            "original_message": original_message,
            "agent_reply": agent_reply,
            "extraction": extraction,
            "mapping": mapping,
            "rejection": rejection,
            "decision": "rejected" if rejection else "accepted",
            "rejection_reason": rejection_reason,
            "path_type": path_type,
            "mapping_reason": mapping_reason,
            "mapped_template_id": mapped_template_id,
            "template_version": template_version,
            "considered_template_ids": mapping.get("considered_template_ids", []) if mapping else [],
            "mismatch_reasons": mapping.get("mismatch_reasons", {}) if mapping else {},
            "final_reason": mapping.get("final_reason") if mapping else None,
            "live_eligible": mapping.get("live_eligible", False) if mapping else False,
            "candidate_status": mapping.get("candidate_status") if mapping else None,
            "candidate_reason": mapping.get("candidate_reason") if mapping else None,
            "required_next_step": mapping.get("required_next_step") if mapping else None,
            "extraction_artifact_id": extraction_artifact_id,
            "mapping_artifact_id": mapping_artifact_id,
            "rejection_artifact_id": rejection_artifact_id,
            "created_at": created_at,
        }
        
    finally:
        conn.close()


@router.post("/{idea_id}/validate")
def validate_idea(idea_id: str, request: ValidateIdeaRequest):
    """
    Trigger validation path (template mapping/candidate evaluation).
    
    Red line 3: Not direct approval, goes through validation.
    """
    # Placeholder - would trigger validation flow
    raise HTTPException(status_code=501, detail="Not implemented")
