"""
Strategy Templates API - Read-only access to approved template registry.

Red lines:
1. Read-only: no POST/PUT/DELETE endpoints
2. Returns only approved templates from library
3. No fake templates, empty list if none approved
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.services.strategy_template_library import StrategyTemplateLibrary

router = APIRouter(prefix="/api/strategy-templates", tags=["strategy_templates"])


@router.get("")
def list_templates(
    status: Optional[str] = None,
    hypothesis_type: Optional[str] = None,
):
    """
    List approved strategy templates.
    
    Returns: list of templates with minimal fields.
    """
    library = StrategyTemplateLibrary()
    templates = library.list_templates()
    
    result = []
    for template in templates:
        # Extract readable rule summaries from V1 PRD fields
        template_data = {
            "template_id": template.template_id,
            "version": template.version,
            "status": "approved",  # All templates in library are approved
            "hypothesis_types": list(template.hypothesis_types),
            "market_fit": template.market_fit,
            "entry_rules": template.entry_rules,
            "exit_rules": template.exit_rules,
            "risk_rules": template.risk_rules,
            "position_sizing_rules": template.position_sizing_rules,
            "validation_gate_profile": template.validation_gate_profile,
            "core_entry_rule_id": template.core_entry_rule_id,
            "supported_universe_rule_types": list(template.supported_universe_rule_types),
            "template_hash": template.template_hash,
        }
        
        # Filter by hypothesis type if requested
        if hypothesis_type and hypothesis_type not in template.hypothesis_types:
            continue
        
        result.append(template_data)
    
    return {"templates": result}


@router.get("/{template_id}")
def get_template(template_id: str):
    """
    Get strategy template detail.
    
    Returns: full template definition with config payload.
    """
    library = StrategyTemplateLibrary()
    
    # Get template from library
    try:
        template = library.get_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Return full template data
    return {
        "template_id": template.template_id,
        "version": template.version,
        "status": "approved",
        "hypothesis_types": list(template.hypothesis_types),
        "market_fit": template.market_fit,
        "entry_rules": template.entry_rules,
        "exit_rules": template.exit_rules,
        "risk_rules": template.risk_rules,
        "position_sizing_rules": template.position_sizing_rules,
        "validation_gate_profile": template.validation_gate_profile,
        "core_entry_rule_id": template.core_entry_rule_id,
        "supported_universe_rule_types": list(template.supported_universe_rule_types),
        "sample_split_rule_ids": list(template.sample_split_rule_ids),
        "benchmark_rule_id": template.benchmark_rule_id,
        "strategy_config_payload": dict(template.strategy_config_payload),
        "default_cost_model": template.default_cost_model,
        "default_fill_model": template.default_fill_model,
        "default_risk_rules": dict(template.default_risk_rules),
        "forbidden_fields": list(template.forbidden_fields),
        "forbidden_evidence_terms": list(template.forbidden_evidence_terms),
        "forbidden_market": list(template.forbidden_market),
        "template_hash": template.template_hash,
        "frozen_template_hash": template.frozen_template_hash,
    }
