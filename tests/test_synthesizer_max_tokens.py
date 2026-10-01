"""Verify Synthesizer max_tokens value."""
from datetime import datetime
from backend.services.serenity_synthesizer import ResearchSynthesizer
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate, SerenityAgentAudit
from contracts.research import ThemeInput, ResearchSource


def test_synthesizer_sends_max_tokens_2048():
    """Synthesizer 当前发送 max_tokens=1024."""
    class RecordingClient:
        def __init__(self):
            self.last_max_tokens = None
        
        def create_message(self, **kwargs):
            self.last_max_tokens = kwargs.get("max_tokens")
            return {
                "model": "test",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "content": [{"type": "text", "text": '{"demand_driver":"test","value_chain_layers":[],"suspected_bottleneck_layers":[],"hypothesis_draft":[],"candidate_rationales":{},"evidence_gaps":[]}'}]
            }
    
    client = RecordingClient()
    synth = ResearchSynthesizer(client)
    
    ctx = SerenityRunContext()
    ctx.verified_candidates_by_symbol["T.SZ"] = VerifiedResearchCandidate(
        symbol="T.SZ", company_name="T", verification_id="v1", exchange="SZ",
        listing_status="listed", confidence="high", supporting_source_ids=["s:T.SZ:0"]
    )
    ctx.sources_by_id["s:T.SZ:0"] = ResearchSource(
        source_record_id="s:T.SZ:0", source_type="financial_report",
        source_quality="first_hand", title="T", summary="T", retrieved_at=datetime.now()
    )
    
    theme = ThemeInput(
        theme_id="t1", theme_name="测试", background="测试", research_mode="quick_scan",
        source_type="manual_theme", created_at=datetime.now(), updated_at=datetime.now()
    )
    audit = SerenityAgentAudit()
    
    synth.synthesize(theme, ctx, audit)
    
    assert client.last_max_tokens == 1024, f"Expected 1024, got {client.last_max_tokens}"
