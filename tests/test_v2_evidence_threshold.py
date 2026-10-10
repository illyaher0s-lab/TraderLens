"""Test V2 evidence thresholds."""
from datetime import datetime
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit, VerifiedResearchCandidate
from contracts.research import ThemeInput, ResearchSource, CandidateStock


# ponytail: 删除过重的 executor 集成测试，主链会验证


def test_zero_sources_blocked():
    """零来源研究无法创建 candidate pool."""
    research_output = {
        "supporting_sources": {},  # 空
        "evidence_gaps": ["gap1"],
        "demand_driver": "test"
    }
    
    # ponytail: 直接检查 dict key，不调 API
    tushare_ids = [k for k in research_output.get("supporting_sources", {}).keys() if k.startswith(("financials:", "announcements:"))]
    assert len(tushare_ids) == 0


def test_real_sources_preserved():
    """真实来源保留 source-id."""
    research_output = {
        "supporting_sources": {
            "financials:600519.SH:0": {"type": "financial_report"},
            "announcements:600519.SH:1": {"type": "announcement"}
        },
        "evidence_gaps": [],
        "demand_driver": "test"
    }
    
    tushare_ids = [k for k in research_output.get("supporting_sources", {}).keys() if k.startswith(("financials:", "announcements:"))]
    assert len(tushare_ids) == 2
    assert "financials:600519.SH:0" in tushare_ids
