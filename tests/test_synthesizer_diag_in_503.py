"""Test that Synthesizer failures expose only a safe failure classification."""

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from backend.services.serenity_agent import SerenityAgentAudit, SerenityRunContext
from backend.services.llm_client import LLMCallResult
from backend.services.serenity_synthesizer import ResearchSynthesizer
from contracts.research import ResearchSource, ThemeInput


class _HttpFailure(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FailingLLMClient:
    def __init__(self, cause: Exception):
        self.cause = cause

    def create_message(self, **_kwargs):
        raise ValueError("request failed") from self.cause


@pytest.mark.parametrize(
    ("cause", "failure_class", "http_status"),
    [
        (TimeoutError("private timeout details"), "timeout", None),
        (_HttpFailure(503), "http", 503),
        (RuntimeError("private prompt and response details"), "client_exception", None),
    ],
)
def test_synthesizer_failure_audit_is_minimal_and_classified(
    cause, failure_class, http_status, capsys,
):
    theme = ThemeInput(
        theme_id="t1",
        theme_name="private theme",
        background="private background",
        research_mode="quick_scan",
        source_type="manual_theme",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    audit = SerenityAgentAudit()
    synthesizer = ResearchSynthesizer(_FailingLLMClient(cause))

    with pytest.raises(ValueError, match="request failed"):
        synthesizer.synthesize(theme, SerenityRunContext(), audit)

    assert len(audit.call_diagnostics) == 1
    diagnostic = audit.call_diagnostics[0]
    assert diagnostic["stage"] == "synthesizer"
    assert diagnostic["failure_class"] == failure_class
    assert diagnostic["status"] == "failure"
    assert diagnostic["exception_class"] in {
        "TimeoutError", "_HttpFailure", "RuntimeError",
    }
    assert diagnostic["http_status"] == http_status
    assert diagnostic["provider_error_code"] is None
    assert diagnostic["timeout"] is (failure_class == "timeout")
    assert diagnostic["input_bytes"] > 0
    assert diagnostic["source_count"] == 0
    assert diagnostic["company_source_count"] == 0
    assert diagnostic["financial_source_count"] == 0
    assert diagnostic["announcement_source_count"] == 0
    assert diagnostic["response_received"] is False
    assert diagnostic["parse_reached"] is False
    assert diagnostic["duration_ms"] >= 0
    assert audit.errors == []
    assert "private" not in json.dumps(audit.call_diagnostics)
    assert capsys.readouterr().out == ""


def _audit_theme():
    now = datetime(2026, 10, 2, 9, 0)
    return ThemeInput(
        theme_id="audit-test",
        theme_name="audit test",
        background="",
        source_type="manual_theme",
        created_at=now,
        updated_at=now,
    )


def _audit_sources():
    now = datetime(2026, 10, 2, 9, 0)
    return {
        source.source_record_id: source
        for source in [
            ResearchSource(
                source_record_id="stock_company:603002.SH:0",
                source_type="unknown",
                title="company profile",
                retrieved_at=now,
            ),
            ResearchSource(
                source_record_id="financials:603002.SH:0",
                source_type="financial_report",
                title="income report",
                published_at=date(2026, 8, 15),
                retrieved_at=now,
            ),
            ResearchSource(
                source_record_id="announcements:603002.SH:0",
                source_type="announcement",
                title="announcement metadata",
                published_at=date(2026, 9, 12),
                source_url="https://static.sse.com.cn/example.pdf",
                retrieved_at=now,
            ),
        ]
    }


def _successful_llm_call(response_text):
    diagnostic = {
        "stage": "synthesizer",
        "provider": "cc-vibe",
        "model": "claude-sonnet-4-6",
        "duration_ms": 321.5,
        "status": "success",
        "exception_class": None,
        "http_status": None,
        "provider_code": None,
        "timeout": False,
        "input_bytes": 4567,
        "source_count": 3,
        "output_parse_reached": False,
    }
    payload = {
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "content": [{"type": "text", "text": response_text}],
    }

    class _Client:
        def create_message(self, **kwargs):
            self.kwargs = kwargs
            return LLMCallResult(payload, diagnostic)

    return _Client()


def test_synthesizer_success_audit_records_safe_metrics_and_source_counts():
    response_text = json.dumps({
        "demand_driver": "",
        "value_chain_layers": [],
        "suspected_bottleneck_layers": [],
        "hypothesis_draft": [],
        "candidate_rationales": {},
        "evidence_gaps": [],
    })
    client = _successful_llm_call(response_text)
    audit = SerenityAgentAudit()

    ResearchSynthesizer(client).synthesize(
        _audit_theme(),
        SerenityRunContext(sources_by_id=_audit_sources()),
        audit,
    )

    assert client.kwargs["timeout"] == 60.0
    assert client.kwargs["stage"] == "synthesizer"
    assert client.kwargs["source_count"] == 3
    diagnostic = audit.call_diagnostics[0]
    assert diagnostic["provider"] == "cc-vibe"
    assert diagnostic["model"] == "claude-sonnet-4-6"
    assert diagnostic["duration_ms"] == 321.5
    assert diagnostic["status"] == "success"
    assert diagnostic["input_bytes"] == 4567
    assert diagnostic["source_count"] == 3
    assert diagnostic["company_source_count"] == 1
    assert diagnostic["financial_source_count"] == 1
    assert diagnostic["announcement_source_count"] == 1
    assert diagnostic["timeout"] is False
    assert diagnostic["response_received"] is True
    assert diagnostic["parse_reached"] is True
    assert "text" not in diagnostic
    assert "messages" not in diagnostic


def test_synthesizer_parse_failure_preserves_response_diagnostic():
    client = _successful_llm_call("not valid json")
    audit = SerenityAgentAudit()

    with pytest.raises(ValueError):
        ResearchSynthesizer(client).synthesize(
            _audit_theme(),
            SerenityRunContext(sources_by_id=_audit_sources()),
            audit,
        )

    diagnostic = audit.call_diagnostics[0]
    assert diagnostic["status"] == "failure"
    assert diagnostic["exception_class"] == "JSONDecodeError"
    assert diagnostic["response_received"] is True
    assert diagnostic["parse_reached"] is True
    assert diagnostic["timeout"] is False
    assert diagnostic["source_count"] == 3
    assert diagnostic["input_bytes"] == 4567
    assert "not valid json" not in json.dumps(audit.call_diagnostics)


def test_synthesizer_failure_keeps_only_safe_existing_provider_fields():
    cause = RuntimeError("private response detail")
    cause.call_diagnostic = {
        "stage": "synthesizer",
        "provider": "cc-vibe",
        "model": "claude-sonnet-4-6",
        "duration_ms": 987.0,
        "status": "error",
        "exception_class": "RuntimeError",
        "http_status": 429,
        "provider_code": "rate_limit_error",
        "timeout": False,
        "input_bytes": 4567,
        "source_count": 99,
        "raw_response": "private response detail",
    }
    audit = SerenityAgentAudit()

    with pytest.raises(ValueError):
        ResearchSynthesizer(_FailingLLMClient(cause)).synthesize(
            _audit_theme(),
            SerenityRunContext(sources_by_id=_audit_sources()),
            audit,
        )

    diagnostic = audit.call_diagnostics[0]
    assert diagnostic["provider"] == "cc-vibe"
    assert diagnostic["model"] == "claude-sonnet-4-6"
    assert diagnostic["duration_ms"] == 987.0
    assert diagnostic["http_status"] == 429
    assert diagnostic["provider_error_code"] == "rate_limit_error"
    assert diagnostic["source_count"] == 3
    assert diagnostic["company_source_count"] == 1
    assert diagnostic["financial_source_count"] == 1
    assert diagnostic["announcement_source_count"] == 1
    assert "raw_response" not in diagnostic
    assert "private response detail" not in json.dumps(diagnostic)
