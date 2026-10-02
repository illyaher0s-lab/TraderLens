from datetime import datetime
from types import SimpleNamespace

from backend.services.llm_client import LLMClient
from backend.services.serenity_agent import SerenityAgentAudit, SerenityRunContext
from backend.services.serenity_synthesizer import ResearchSynthesizer
from contracts.research import ThemeInput


def _provider_response():
    return SimpleNamespace(
        id="msg_test",
        model="test-model",
        role="assistant",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        content=[SimpleNamespace(type="text", text="ok")],
    )


def test_llm_client_timeout_override_is_per_request_and_default_is_preserved(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return _provider_response()

    provider = SimpleNamespace(messages=SimpleNamespace(create=create))
    constructor_kwargs = {}

    def make_provider(**kwargs):
        constructor_kwargs.update(kwargs)
        return provider

    monkeypatch.setattr("backend.services.llm_client.Anthropic", make_provider)
    client = LLMClient(api_key="test-key", base_url="https://api.anthropic.com", model="test-model")

    client.create_message(messages=[{"role": "user", "content": "test"}], timeout=60.0)
    client.create_message(messages=[{"role": "user", "content": "test"}])

    assert constructor_kwargs["timeout"] == 30.0
    assert calls[0]["timeout"] == 60.0
    assert "timeout" not in calls[1]


def test_synthesizer_requests_sixty_second_timeout():
    class CapturingLLM:
        def create_message(self, **kwargs):
            self.kwargs = kwargs
            return {
                "model": "test-model",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [{
                    "type": "text",
                    "text": (
                        '{"demand_driver":"","value_chain_layers":[],'
                        '"suspected_bottleneck_layers":[],"hypothesis_draft":[],'
                        '"candidate_rationales":{},"evidence_gaps":[]}'
                    ),
                }],
            }

    llm = CapturingLLM()
    theme = ThemeInput(
        theme_id="synth-timeout-test",
        theme_name="timeout test",
        background="",
        source_type="manual_theme",
        created_at=datetime(2026, 10, 2),
        updated_at=datetime(2026, 10, 2),
    )

    ResearchSynthesizer(llm).synthesize(theme, SerenityRunContext(), SerenityAgentAudit())

    assert llm.kwargs["timeout"] == 60.0
