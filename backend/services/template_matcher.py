"""
Deterministic Template Matcher

Evaluates strategy ideas against approved templates and records mismatch reasons.
No LLM, no fake matching - only rule-based evaluation.
"""

from typing import Optional
from backend.services.strategy_template_library import list_approved_templates


def evaluate_templates_for_idea(
    claimed_entry: str,
    claimed_exit: str,
    claimed_edge: Optional[str],
) -> dict:
    """
    Evaluate all approved templates against extracted claims.
    
    Returns:
        {
            "matched_template_id": None,  # Always None until we have real matcher
            "template_version": None,
            "considered_template_ids": ["template_id1", "template_id2", ...],
            "mismatch_reasons": {
                "template_id1": "reason1",
                "template_id2": "reason2",
            },
            "final_reason": "no_template_fit" or "no_approved_template",
        }
    """
    templates = list_approved_templates()
    
    if not templates:
        return {
            "matched_template_id": None,
            "template_version": None,
            "considered_template_ids": [],
            "mismatch_reasons": {},
            "final_reason": "no_approved_template",
        }
    
    considered_template_ids = []
    mismatch_reasons = {}
    
    for template in templates:
        considered_template_ids.append(template.template_id)
        
        # Deterministic mismatch detection (no LLM)
        # For now, all ideas mismatch because we don't have a real matcher
        # In the future, this would check:
        # - Entry rule compatibility
        # - Exit rule compatibility
        # - Risk rule compatibility
        # - Hypothesis type alignment
        
        reasons = []
        
        # Check if claimed rules are extractable
        if claimed_entry == "未提取" or not claimed_entry:
            reasons.append("入场条件未明确提取")
        
        if claimed_exit == "未提取" or not claimed_exit:
            reasons.append("出场条件未明确提取")
        
        # Check hypothesis type alignment (simple keyword matching)
        if "MACD" not in claimed_entry.upper() and "momentum" in template.hypothesis_types:
            if template.template_id == "theme_momentum_breakout_v1":
                reasons.append(f"策略描述未提及MACD指标，不符合{template.template_id}的MACD动量假设")
        
        if "突破" not in claimed_entry and "breakout" in template.template_id:
            reasons.append(f"策略描述未明确突破逻辑，不符合{template.template_id}的突破假设")
        
        if "相对强度" not in claimed_entry and "relative_strength" in template.hypothesis_types:
            reasons.append(f"策略描述未提及相对强度，不符合{template.template_id}的相对强度假设")
        
        # If no specific reasons found, use generic reason
        if not reasons:
            reasons.append(f"策略规则与{template.template_id}模板规则差异过大，无法自动映射")
        
        mismatch_reasons[template.template_id] = "; ".join(reasons)
    
    return {
        "matched_template_id": None,
        "template_version": None,
        "considered_template_ids": considered_template_ids,
        "mismatch_reasons": mismatch_reasons,
        "final_reason": "no_template_fit",
    }
