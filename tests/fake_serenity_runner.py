"""
Fake SerenityRunner for testing friend-stock flow.
"""

from contracts.research import AgentHarnessConfig, CandidateStock, ThemeInput
from backend.services.serenity_agent import SerenityOutput
from datetime import datetime


class FakeSerenityRunner:
    """
    Fake SerenityRunner that returns valid SerenityOutput for testing.
    """
    
    def run(self, theme: ThemeInput, manual_candidates: list) -> SerenityOutput:
        """
        Return a fake SerenityOutput with minimal valid structure.
        """
        now = datetime.now()
        target = manual_candidates[0] if manual_candidates else None
        symbol = target.symbol if target else "600000.SH"
        company_name = target.company_name if target else "Test Company"
        candidate = CandidateStock(
            candidate_id=f"fake_cand_{theme.theme_id}",
            theme_id=theme.theme_id,
            symbol=symbol,
            company_name=company_name,
            source_type="manual_stock",
            chain_layer="banking",
            match_reason="Strong player in sector",
            match_confidence="high",
            status="raw",
            hard_filter_flags=[],
            created_at=now,
            supporting_source_ids=[f"financials:{symbol}:0"],
            counter_evidence=[],
        )

        return SerenityOutput(
            theme_id=theme.theme_id,
            demand_driver="Test demand driver",
            value_chain_layers=[
                {"layer": "upstream", "description": "suppliers"},
                {"layer": "midstream", "description": "manufacturers"},
                {"layer": "downstream", "description": "retailers"},
            ],
            suspected_bottleneck_layers=[{"layer": "midstream", "reason": "capacity constraint"}],
            hypothesis_draft=[{"hypothesis": "Test hypothesis"}],
            candidate_pool_raw=[candidate],
            candidate_shortlist=[],
            evidence_gaps=["Need more financial data"],
            harness=AgentHarnessConfig(
                execution_engine="two_phase",
                llm_provider="fake-provider",
                tool_whitelist=["fake_serenity"],
                max_steps=1,
                token_budget=1,
                replayable=True,
            ),
            created_at=now,
        )
