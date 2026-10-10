"""Test V2 single-target constraint."""
import pytest
from datetime import datetime
from backend.services.serenity_planner import ResearchPlanner, ResearchPlan
from backend.services.serenity_executor import DeterministicExecutor
from backend.services.serenity_synthesizer import ResearchSynthesizer
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit
from contracts.research import ThemeInput, ResearchSource, CandidateStock


def test_planner_no_seed_symbols():
    """V2 Planner 不输出 seed_symbols."""
    class MockClient:
        def create_message(self, **kwargs):
            return {
                "model": "test",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "content": [{"type": "text", "text": '{"keywords":["a"],"seed_symbols":[],"sectors_to_check":["电气"],"start_date":"20230101","end_date":"20260624","falsification_questions":["q1"]}'}]
            }
    
    planner = ResearchPlanner(MockClient())
    theme = ThemeInput(
        theme_id="t1", theme_name="测试", background="测试", research_mode="quick_scan",
        source_type="manual_theme", created_at=datetime.now(), updated_at=datetime.now()
    )
    
    plan = planner.plan(theme, [])
    assert plan.seed_symbols == [], f"Expected empty, got {plan.seed_symbols}"


def test_executor_single_target_only():
    """V2 Executor 只检索 target_symbol."""
    class MockTools:
        def __init__(self):
            self.calls = []
        
        def retrieve_supply_chain(self, **kwargs):
            self.calls.append(kwargs)
            from contracts.tushare import SupplyChainResult
            return SupplyChainResult(records=[], gaps=[], errors=[], total_found=0)
    
    tools = MockTools()
    executor = DeterministicExecutor(tools, None, None)
    
    plan = ResearchPlan(keywords=["a"], seed_symbols=["999.SZ"], sectors_to_check=[], start_date=None, end_date=None, falsification_questions=[])
    ctx = SerenityRunContext()
    audit = SerenityAgentAudit()
    
    executor.execute(plan, ctx, audit, target_symbol="600519.SH")
    
    # 只有一次调用，且是目标标的
    assert len(tools.calls) == 1
    assert tools.calls[0]["symbols"] == ["600519.SH"]


def test_synthesizer_single_candidate():
    """V2 Synthesizer 只综合第一个候选."""
    class MockClient:
        def create_message(self, **kwargs):
            prompt = kwargs.get("messages", [{}])[0].get("content", "")
            # 验证只有一个候选
            assert prompt.count('"symbol":') == 1, "Expected 1 candidate"
            return {
                "model": "test",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "content": [{"type": "text", "text": '{"demand_driver":"test","value_chain_layers":[],"suspected_bottleneck_layers":[],"hypothesis_draft":[],"candidate_rationales":{},"evidence_gaps":[]}'}]
            }
    
    synth = ResearchSynthesizer(MockClient())
    
    ctx = SerenityRunContext()
    # 添加 2 个候选
    from backend.services.serenity_agent import VerifiedResearchCandidate
    ctx.verified_candidates_by_symbol["A.SZ"] = VerifiedResearchCandidate(
        symbol="A.SZ", company_name="A", verification_id="v1", exchange="SZ",
        listing_status="listed", confidence="high", supporting_source_ids=[]
    )
    ctx.verified_candidates_by_symbol["B.SH"] = VerifiedResearchCandidate(
        symbol="B.SH", company_name="B", verification_id="v2", exchange="SH",
        listing_status="listed", confidence="high", supporting_source_ids=[]
    )
    
    theme = ThemeInput(
        theme_id="t1", theme_name="测试", background="测试", research_mode="quick_scan",
        source_type="manual_theme", created_at=datetime.now(), updated_at=datetime.now()
    )
    audit = SerenityAgentAudit()
    
    synth.synthesize(theme, ctx, audit)  # 断言在 MockClient 内
