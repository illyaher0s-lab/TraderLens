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


def test_synthesizer_audit_preserves_safe_attempt_diagnostics():
    diagnostic = {
        "provider": "cc-vibe",
        "model": "claude-sonnet-5-5",
        "duration_ms": 37.5,
        "input_bytes": 128,
        "status": "error",
        "exception_class": "APIConnectionError",
        "http_status": 502,
        "provider_code": "api_error",
        "timeout": False,
        "response_received": True,
        "attempt_count": 1,
        "retry_count": 0,
        "retry_stop_reason": None,
        "exception_chain": [{"type": "APIConnectionError", "message": "upstream unavailable"}],
        "response_error_text": '{"error":"upstream unavailable"}',
        "attempts": [{
            "attempt": 1,
            "status": "error",
            "duration_ms": 37.5,
            "http_status": 502,
            "provider_code": "api_error",
            "timeout": False,
            "exception_chain": [{"type": "APIConnectionError", "message": "upstream unavailable"}],
            "response_error_text": '{"error":"upstream unavailable"}',
        }],
        "request_headers": {"Authorization": "must-not-pass"},
    }
    synthesizer = ResearchSynthesizer(object())
    pack_meta = {
        "source_count": 0,
        "company_source_count": 0,
        "financial_source_count": 0,
        "announcement_source_count": 0,
    }

    audited = synthesizer._call_audit_diagnostic(
        diagnostic,
        pack_meta,
        {"provider": "cc-vibe", "model": "claude-sonnet-5-5", "duration_ms": 0.0, "input_bytes": 128},
        status="failure",
        response_received=False,
        parse_reached=False,
        failure_class="http",
    )

    assert audited["response_received"] is True
    assert audited["attempt_count"] == 1
    assert audited["retry_count"] == 0
    assert audited["exception_chain"] == diagnostic["exception_chain"]
    assert audited["response_error_text"] == diagnostic["response_error_text"]
    assert audited["attempts"] == diagnostic["attempts"]
    assert "request_headers" not in audited


def test_discipline_review_projection_keeps_safe_retry_history():
    from backend.services.discipline_review import DisciplineReviewService

    source = {
        "stage": None,
        "status": "error",
        "exception_class": "APITimeoutError",
        "http_status": None,
        "provider_code": None,
        "timeout": True,
        "output_parse_reached": False,
        "attempt_count": 2,
        "retry_count": 1,
        "retry_stop_reason": None,
        "response_received": False,
        "exception_chain": [{"type": "APITimeoutError", "message": "request timed out"}],
        "response_error_text": None,
        "attempts": [
            {
                "attempt": 1,
                "status": "timeout",
                "duration_ms": 15.0,
                "http_status": None,
                "provider_code": None,
                "timeout": True,
                "exception_chain": [{"type": "APITimeoutError", "message": "request timed out"}],
                "response_error_text": None,
            },
            {
                "attempt": 2,
                "status": "success",
                "duration_ms": 22.0,
                "http_status": None,
                "provider_code": None,
                "timeout": False,
                "exception_chain": [],
                "response_error_text": None,
            },
        ],
        "environment": {"RESEARCH_LLM_API_KEY": "must-not-pass"},
    }

    projected = DisciplineReviewService._project_ai_provider_diagnostic(source)

    assert projected["attempt_count"] == 2
    assert projected["retry_count"] == 1
    assert projected["response_received"] is False
    assert projected["exception_chain"] == source["exception_chain"]
    assert projected["attempts"] == source["attempts"]
    assert "environment" not in projected
