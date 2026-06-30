"""
Fake SerenityRunner for testing friend-stock flow.
"""

from contracts.research import ThemeInput
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
            candidate_pool_raw=[
                {
                    "symbol": "600000.SH",
                    "company_name": "Test Company",
                    "rationale": "Strong player in sector",
                    "supporting_source_ids": ["src_001"],
                    "counter_evidence": [],
                }
            ],
            candidate_shortlist=[],
            evidence_gaps=["Need more financial data"],
            harness={},
            run_id=f"run_{theme.theme_id}",
            created_at=datetime.now(),
        )
