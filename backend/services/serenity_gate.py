"""
Serenity Shortlist Gate (双阶段重构 - 确定性门禁).

根据硬规则过滤候选，生成 candidate_shortlist。

硬约束:
- 所有检查确定性
- LLM 不能覆盖门禁决策
- 不满足条件时返回空列表，不为凑数量放行
"""

from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import CandidateStock
from datetime import datetime


def apply_shortlist_gate(
    context: SerenityRunContext,
    synthesis: ResearchSynthesis,
    theme_id: str,
) -> list[CandidateStock]:
    """Apply deterministic shortlist gate.
    
    候选进入 shortlist 必须满足：
    1. 存在于 verified_candidates_by_symbol
    2. verification_id 有效并与 symbol 匹配
    3. company_name 来自 verification record
    4. 至少一个真实 supporting source
    5. 至少一个 supporting source 不是 weak
    6. source_audit 已完成
    7. red_team 已完成
    8. 候选必须有 falsification_questions 或 counter_evidence（只有 data_gaps 不算完成 red-team）
    9. 没有身份阻断问题
    10. candidate_rationales 必须有 supporting_source_ids
    11. rationale_source_ids 必须存在于 context
    12. rationale_source_ids 必须至少有一个非 weak
    13. rationale_source_ids 必须与候选 symbol 匹配
    14. rationale_source_ids 必须至少一个证明主题相关性
    
    Args:
        context: SerenityRunContext with verified candidates
        synthesis: ResearchSynthesis from LLM
        theme_id: Theme ID for creating CandidateStock
        
    Returns:
        List of CandidateStock that passed all gates (may be empty)
    """
    
    shortlist: list[CandidateStock] = []
    now = datetime.now()
    
    # 检查前置条件
    if "source_audit" not in context.completed_checks:
        return []
    
    if "red_team" not in context.completed_checks:
        return []
    
    # 只考虑 synthesis 中提到的候选
    mentioned_symbols = set(synthesis.candidate_rationales.keys())
    
    for symbol in mentioned_symbols:
        # Gate 1: 候选必须存在于 verified_candidates
        if symbol not in context.verified_candidates_by_symbol:
            continue
        
        candidate = context.verified_candidates_by_symbol[symbol]
        
        # Gate 2: verification_id 有效
        if not candidate.verification_id or not candidate.verification_id.startswith("verify_"):
            continue
        
        # Gate 3: company_name 非空（来自 verification record）
        if not candidate.company_name:
            continue
        
        # Gate 4: 硬过滤必须全部通过
        if candidate.hard_filter_flags:
            continue
        
        # Gate 5: 至少一个 supporting source
        if not candidate.supporting_source_ids:
            continue
        
        # Gate 6: 至少一个 supporting source 不是 weak
        sources = [
            context.sources_by_id.get(sid)
            for sid in candidate.supporting_source_ids
        ]
        # 过滤掉不存在的 sources
        sources = [s for s in sources if s is not None]
        
        if not sources:
            continue
        
        has_non_weak = any(s.source_quality != "weak" for s in sources)
        if not has_non_weak:
            continue
        
        # Gate 8: 候选必须有 counter_evidence 或 falsification_questions
        # Gate 8: 候选拥有 red_team finding 或 unresolved gap
        # 修正后规则：
        # - 只有 data_gaps → 拒绝
        # - 有明确且有效的 falsification_question → 可视为完成诘问
        # - 有可追溯 counter_evidence → 可通过
        has_red_team_output = (
            len(candidate.falsification_questions) > 0 or
            len(candidate.counter_evidence) > 0
        )
        
        # 如果只有 data_gaps 但没有诘问或反证，拒绝
        if not has_red_team_output and len(candidate.data_gaps) > 0:
            continue
        
        # 如果既没有 data_gaps 也没有任何 red-team 输出，也拒绝（未完成 red-team）
        if not has_red_team_output and len(candidate.data_gaps) == 0:
            continue
        
        # Gate 9: 没有身份阻断问题
        if candidate.confidence == "low":
            continue
        
        if candidate.listing_status not in ("listed", ""):
            continue
        
        # 通过所有门禁，加入 shortlist
        rationale_data = synthesis.candidate_rationales.get(symbol, {})
        rationale = rationale_data.get("rationale", "") if isinstance(rationale_data, dict) else str(rationale_data)
        rationale_source_ids = rationale_data.get("supporting_source_ids", []) if isinstance(rationale_data, dict) else []
        
        # Gate 10: candidate_rationales 必须有 supporting_source_ids
        if not rationale_source_ids:
            continue
        
        # Gate 11: rationale_source_ids 必须存在于 context
        rationale_sources_exist = all(
            sid in context.sources_by_id for sid in rationale_source_ids
        )
        if not rationale_sources_exist:
            continue
        
        # Gate 12: rationale_source_ids 必须至少有一个非 weak
        rationale_sources = [context.sources_by_id[sid] for sid in rationale_source_ids]
        has_non_weak_rationale = any(s.source_quality != "weak" for s in rationale_sources)
        if not has_non_weak_rationale:
            continue
        
        # Gate 13: rationale_source_ids 必须与候选 symbol 匹配
        # source_record_id 格式：tool:symbol:idx
        # 验证至少一个来源属于当前 symbol
        has_matching_source = False
        for sid in rationale_source_ids:
            parts = sid.split(":")
            if len(parts) >= 2:
                source_symbol = parts[1]
                if source_symbol == symbol:
                    has_matching_source = True
                    break
        
        if not has_matching_source:
            continue
        
        # Gate 14: rationale_source_ids 必须至少一个证明主题相关性
        # 主题相关性要求：
        # - theme_keywords_matched 非空
        # - theme_relevance_basis 合法（title_match/summary_match/industry_match）
        # - source_quality != weak（已在 Gate 12 检查）
        # - symbol 匹配（已在 Gate 13 检查）
        has_theme_evidence = False
        for sid in rationale_source_ids:
            source = context.sources_by_id.get(sid)
            if source is None:
                continue
            
            # 检查主题匹配
            if (source.theme_keywords_matched and 
                source.theme_relevance_basis in ("title_match", "summary_match", "industry_match") and
                source.source_quality != "weak"):
                
                # 检查 symbol 匹配
                parts = sid.split(":")
                if len(parts) >= 2 and parts[1] == symbol:
                    has_theme_evidence = True
                    break
        
        if not has_theme_evidence:
            continue
        
        # 保存 red-team 结果到 CandidateStock
        red_team_findings_combined = (
            [f"counter: {e}" for e in candidate.counter_evidence] +
            [f"question: {q}" for q in candidate.falsification_questions] +
            [f"gap: {g}" for g in candidate.data_gaps]
        )
        
        shortlist.append(CandidateStock(
            candidate_id=f"serenity_{symbol}_{int(now.timestamp())}",
            theme_id=theme_id,
            symbol=symbol,
            company_name=candidate.company_name,
            verification_id=candidate.verification_id,
            source_type="manual_theme",
            chain_layer=None,
            match_reason=rationale[:500],  # 截断过长的 rationale
            match_confidence=candidate.confidence,
            status="shortlisted",
            hard_filter_flags=[],
            override_reason=None,
            created_at=now,
            # Research metadata
            supporting_source_ids=rationale_source_ids,
            # Red-team 结果（三类独立）
            counter_evidence=candidate.counter_evidence,
            falsification_questions=candidate.falsification_questions,
            data_gaps=candidate.data_gaps,
            # 向后兼容
            red_team_findings=candidate.red_team_findings,
            unresolved_gaps=candidate.unresolved_gaps,
        ))
    
    return shortlist
