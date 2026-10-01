"""Test Synthesizer input boundary enforcement."""
import pytest
from datetime import datetime
from backend.services.serenity_synthesizer import ResearchSynthesizer
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate, SerenityAgentAudit
from contracts.research import ThemeInput, ResearchSource


def test_synthesizer_boundary_truncates_source_ids():
    """Synthesizer 限制每候选最多 10 个 source_ids."""
    # Mock LLM client
    class MockLLMClient:
        def create_message(self, **kwargs):
            # 返回最小有效 JSON
            return {
                "model": "test",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{
                    "type": "text",
                    "text": '{"demand_driver": "test", "value_chain_layers": [], "suspected_bottleneck_layers": [], "hypothesis_draft": [], "candidate_rationales": {}, "evidence_gaps": []}'
                }]
            }
    
    synthesizer = ResearchSynthesizer(MockLLMClient())
    
    # 创建候选，携带 15 个 source_ids
    context = SerenityRunContext()
    context.verified_candidates_by_symbol["TEST.SZ"] = VerifiedResearchCandidate(
        symbol="TEST.SZ",
        company_name="Test Company",
        verification_id="v1",
        exchange="SZ",
        listing_status="listed",
        confidence="high",
        supporting_source_ids=[f"financials:TEST.SZ:{i}" for i in range(15)],
    )
    
    # 添加对应的来源
    for i in range(15):
        sid = f"financials:TEST.SZ:{i}"
        context.sources_by_id[sid] = ResearchSource(
            source_record_id=sid,
            source_type="financial_report",
            source_quality="first_hand",
            title="Test Report",
            summary="Test",
            retrieved_at=datetime.now(),
        )
    
    theme = ThemeInput(
        theme_id="t1",
        theme_name="测试主题",
        background="测试背景",
        research_mode="quick_scan",
        source_type="manual_theme",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    audit = SerenityAgentAudit()
    
    # 调用 synthesize（会构建研究包）
    synthesis = synthesizer.synthesize(theme, context, audit)
    
    # 验证 evidence_gaps 包含截断信息
    assert any("source_ids omitted" in gap for gap in synthesis.evidence_gaps), \
        f"Expected truncation gap, got: {synthesis.evidence_gaps}"


def test_synthesizer_boundary_truncates_sources():
    """Synthesizer 限制最多 50 个来源摘要."""
    class MockLLMClient:
        def create_message(self, **kwargs):
            return {
                "model": "test",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{
                    "type": "text",
                    "text": '{"demand_driver": "test", "value_chain_layers": [], "suspected_bottleneck_layers": [], "hypothesis_draft": [], "candidate_rationales": {}, "evidence_gaps": []}'
                }]
            }
    
    synthesizer = ResearchSynthesizer(MockLLMClient())
    
    context = SerenityRunContext()
    context.verified_candidates_by_symbol["TEST.SZ"] = VerifiedResearchCandidate(
        symbol="TEST.SZ",
        company_name="Test Company",
        verification_id="v1",
        exchange="SZ",
        listing_status="listed",
        confidence="high",
        supporting_source_ids=["financials:TEST.SZ:0"],
    )
    
    # 添加 60 个来源
    for i in range(60):
        sid = f"financials:TEST.SZ:{i}"
        context.sources_by_id[sid] = ResearchSource(
            source_record_id=sid,
            source_type="financial_report",
            source_quality="first_hand",
            title="Test Report",
            summary="Test",
            retrieved_at=datetime.now(),
        )
    
    theme = ThemeInput(
        theme_id="t1",
        theme_name="测试主题",
        background="测试背景",
        research_mode="quick_scan",
        source_type="manual_theme",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    audit = SerenityAgentAudit()
    
    synthesis = synthesizer.synthesize(theme, context, audit)
    
    # 验证 evidence_gaps 包含截断信息
    assert any("sources omitted" in gap for gap in synthesis.evidence_gaps), \
        f"Expected source truncation gap, got: {synthesis.evidence_gaps}"
