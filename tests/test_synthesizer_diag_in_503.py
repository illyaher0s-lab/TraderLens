"""Test that Synthesizer failures expose only a safe failure classification."""

import json
from datetime import datetime

import pytest

from backend.services.serenity_agent import SerenityAgentAudit, SerenityRunContext
from backend.services.serenity_synthesizer import ResearchSynthesizer
from contracts.research import ThemeInput


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

    assert audit.call_diagnostics == [
        {
            "stage": "synthesizer",
            "failure_class": failure_class,
            **({"http_status": http_status} if http_status is not None else {}),
        }
    ]
    assert audit.errors == []
    assert "private" not in json.dumps(audit.call_diagnostics)
    assert capsys.readouterr().out == ""
