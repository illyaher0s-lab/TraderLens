"""Workbench -> ResearchCase -> Serenity integration contract."""

import json
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.app.tushare.config import TushareConfig
from backend.db.research import ResearchDB
from backend.db.agent_workbench import init_agent_workbench_db
from backend.services.research_validation import (
    HardFilterSnapshot,
    ResearchValidator,
    TickerVerificationResult,
    ValidationResult,
)
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.serenity_tools import SerenityTools
from backend.services.stock_identity_resolver import StockIdentityResolution
from contracts.research import ResearchSource, SerenityToolResult
from tests.fake_serenity_runner import FakeSerenityRunner


class _UnavailableLLM:
    """Deterministic external-boundary failure; no research data is synthesized."""

    def __init__(self):
        self.calls = 0

    def create_message(self, **_kwargs):
        self.calls += 1
        raise ValueError("llm_unavailable: test boundary has no configured provider")


class _SentinelRaisingLLM:
    """Local-only failure boundary; the sentinel is synthetic, never a credential."""

    def __init__(self, sentinel):
        self.sentinel = sentinel
        self.calls = 0

    def get_provider_name(self):
        return "fixture-provider"

    def get_model_name(self):
        return "fixture-model"

    def create_message(self, **_kwargs):
        self.calls += 1
        raise RuntimeError(f"provider diagnostic {self.sentinel}")


class _SentinelRaisingTushare:
    """Local-only identity lookup failure; never calls Tushare."""

    def __init__(self, sentinel):
        self.sentinel = sentinel

    def query(self, *_args, **_kwargs):
        raise RuntimeError(f"Tushare diagnostic {self.sentinel}")


class _MacroHongIdentityFixture:
    """Identity-only fixture: 宏昌电子=603002.SH; never supplies research facts."""

    def resolve(self, company_name, stock_code):
        assert company_name == "宏昌电子"
        assert stock_code is None
        return StockIdentityResolution(
            status="verified",
            ticker="603002.SH",
            company_name="宏昌电子",
            exchange="SSE",
            list_status="L",
            data_source="deterministic_fixture",
        )


class _TwoPhaseLLM:
    """Deterministic LLM boundary; the Serenity orchestration remains real."""

    def __init__(
        self, transaction_probe=None, *, verdict="research_watch",
        synthesis_payload=None, response_ids=None,
    ):
        self.calls = 0
        self.requests = []
        self.transaction_probe = transaction_probe
        self.verdict = verdict
        self.synthesis_payload = synthesis_payload
        self.response_ids = response_ids or []

    def get_provider_name(self):
        return "fixture-provider"

    def get_model_name(self):
        return "fixture-model"

    def create_message(self, **_kwargs):
        if self.transaction_probe is not None:
            self.transaction_probe()
        self.calls += 1
        self.requests.append(_kwargs)
        if self.calls == 1:
            text = json.dumps({
                "keywords": ["宏昌电子"],
                "seed_symbols": ["603002.SH"],
                "sectors_to_check": [],
                "start_date": None,
                "end_date": None,
                "falsification_questions": [],
            }, ensure_ascii=False)
        else:
            synthesis_payload = self.synthesis_payload or {
                "demand_driver": "fixture demand boundary",
                "value_chain_layers": [{
                    "layer": "fixture",
                    "description": "fixture source only",
                    "supporting_source_ids": ["financials:603002.SH:0"],
                }],
                "suspected_bottleneck_layers": [],
                "hypothesis_draft": [{
                    "hypothesis": "fixture hypothesis",
                    "rationale": "fixture rationale",
                    "confidence": "medium",
                    "supporting_source_ids": ["financials:603002.SH:0"],
                }],
                "candidate_rationales": {
                    "603002.SH": {
                        "rationale": "603002.SH 宏昌电子 fixture rationale",
                        "supporting_source_ids": ["financials:603002.SH:0"],
                        "falsification_questions": ["603002.SH 宏昌电子产能是否落实？"],
                        "counter_evidence": [{
                            "description": "fixture counter risk",
                            "source_record_id": "financials:603002.SH:0",
                        }],
                    }
                },
                "candidate_verdicts": {
                    "603002.SH": {
                        "verdict": self.verdict,
                        "reason": (
                            "fixture missing-data reason"
                            if self.verdict == "research_unavailable"
                            else "fixture verdict reason"
                        ),
                        "supporting_source_ids": (
                            [] if self.verdict == "research_unavailable"
                            else ["financials:603002.SH:0"]
                        ),
                        "counter_evidence": (
                            [] if self.verdict == "research_unavailable" else [{
                                "description": "fixture counter risk",
                                "source_record_id": "financials:603002.SH:0",
                            }]
                        ),
                        "invalidation_conditions": (
                            [] if self.verdict == "research_unavailable" else [
                                "603002.SH 宏昌电子产能是否落实？"
                            ]
                        ),
                        "evidence_gaps": (
                            ["fixture unavailable gap"]
                            if self.verdict == "research_unavailable"
                            else ["fixture verdict evidence gap"]
                        ),
                    }
                },
                "evidence_gaps": ["fixture evidence boundary"],
            }
            text = (
                synthesis_payload
                if isinstance(synthesis_payload, str)
                else json.dumps(synthesis_payload, ensure_ascii=False)
            )
        return {
            "id": (
                self.response_ids[self.calls - 1]
                if self.calls <= len(self.response_ids)
                else f"fixture-request-{self.calls}"
            ),
            "model": "fixture-model",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


class _DeterministicValidator:
    """Identity/data boundary for Serenity tests; no production data is read."""

    tushare_client = None

    def verify_ticker(self, symbol):
        return TickerVerificationResult(
            verification_id="verify_fixture_603002",
            company_name="宏昌电子",
            ticker=symbol,
            exchange="SSE",
            status="listed",
            confidence="high",
            source="deterministic_fixture",
            notes="fixture identity only",
            verified_at=datetime.now(),
        )

    def get_hard_filter_snapshot(self, symbol, verified_status):
        return HardFilterSnapshot(
            is_listed=True,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=2_000_000.0,
            source="deterministic_fixture",
            retrieved_at=datetime.now(),
            gaps=[],
        )

    def validate_candidate(self, **_kwargs):
        return ValidationResult(flags=[], is_valid=True)


class _DeterministicSerenityTools(SerenityTools):
    """Real Serenity tool boundary with optional source absence."""

    def __init__(self, validator, *, with_source):
        super().__init__(validator=validator)
        self.with_source = with_source

    def retrieve_supply_chain(self, **_kwargs):
        if not self.with_source:
            return SerenityToolResult(
                tool_name="retrieve_supply_chain",
                records=[],
                total_found=0,
                gaps=["fixture_source_unavailable"],
                errors=[],
                retrieved_at=datetime.now(),
            )
        return SerenityToolResult(
            tool_name="retrieve_supply_chain",
            records=[ResearchSource(
                source_record_id="financials:603002.SH:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="宏昌电子 fixture financial source",
                summary="宏昌电子 fixture evidence boundary",
                retrieved_at=datetime.now(),
            )],
            total_found=1,
            gaps=[],
            errors=[],
            retrieved_at=datetime.now(),
        )


def _real_two_phase_runner(
    db, *, with_source=True, transaction_probe=None, llm_client=None,
):
    validator = _DeterministicValidator()
    return SerenityAgentRunner(
        llm_client=llm_client or _TwoPhaseLLM(transaction_probe=transaction_probe),
        validator=validator,
        tools=_DeterministicSerenityTools(validator, with_source=with_source),
        mode="real",
        db=db,
        execution_mode="two_phase",
    )


def _workbench_app(db, runner, validator):
    return create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=validator,
        serenity_runner=runner,
        allow_test_serenity_runner=True,
        stock_resolver_override=_MacroHongIdentityFixture(),
    )


def test_workbench_runs_real_serenity_and_persists_unavailable_gap(tmp_path):
    """One Workbench message must execute real Serenity and durably expose its gap."""

    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = ResearchValidator(tushare_config=TushareConfig(token=None))
    unavailable_llm = _UnavailableLLM()
    serenity_runner = SerenityAgentRunner(
        llm_client=unavailable_llm,
        validator=validator,
        tools=SerenityTools(validator=validator),
        mode="real",
        db=db,
        execution_mode="two_phase",
    )
    app = create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=validator,
        serenity_runner=serenity_runner,
        allow_test_serenity_runner=True,
        stock_resolver_override=_MacroHongIdentityFixture(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow_type"] == "friend_stock"
    assert body["stage"] == "stopped"
    assert "research_unavailable" in body["agent_reply"]
    assert unavailable_llm.calls == 1

    conversation_id = body["conversation_id"]
    timeline = client.get(f"/api/agent/workbench/{conversation_id}").json()["timeline"]
    research_artifacts = [
        item["content"]
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    ]
    assert len(research_artifacts) == 1
    research_artifact = json.loads(research_artifacts[0]["artifact_content"])
    assert research_artifact["research_status"] == "research_unavailable"
    assert research_artifact["ticker"] == "603002.SH"
    assert research_artifact["identity_source"] == "deterministic_fixture"
    assert research_artifact["evidence_gaps"]

    research_id = research_artifact["research_case_id"]
    theme = client.get(f"/api/research/themes/{research_id}")
    assert theme.status_code == 200
    persisted = theme.json()["research_output"]
    assert persisted["research_status"] == "research_unavailable"
    assert persisted["research_verdict"] == "research_unavailable"
    assert persisted["ticker"] == "603002.SH"
    assert persisted["identity_source"] == "deterministic_fixture"
    assert persisted["supporting_evidence"] == []
    assert persisted["counter_evidence"] == []
    assert persisted["falsification_conditions"] == []

    # Durable assertions use a new connection, not the app's in-memory state.
    with sqlite3.connect(db_path) as check:
        theme_row = check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (research_id,),
        ).fetchone()
        assert theme_row is not None
        assert json.loads(theme_row[0])["research_status"] == "research_unavailable"
        assert check.execute(
            "SELECT COUNT(*) FROM research_candidates WHERE theme_id = ?",
            (research_id,),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM agent_approval_cards WHERE session_id = ?",
            (conversation_id,),
        ).fetchone()[0] == 0


def test_workbench_real_two_phase_accepts_traceable_fixture_evidence(tmp_path):
    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db)
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow_type"] == "friend_stock"
    assert body["stage"] == "observing"
    assert "research_watch" in body["agent_reply"]
    assert runner.llm_client.calls == 2

    timeline = client.get(f"/api/agent/workbench/{body['conversation_id']}").json()["timeline"]
    result = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    assert result["research_status"] == "research_watch"
    assert result["research_verdict"] == "research_watch"
    assert result["supporting_evidence"] == ["financials:603002.SH:0"]
    assert result["counter_evidence"]
    assert result["falsification_conditions"]
    assert result["evidence_gaps"] == [
        "fixture evidence boundary", "fixture verdict evidence gap"
    ]

    with sqlite3.connect(db_path) as check:
        assert check.execute(
            "SELECT COUNT(*) FROM research_candidates WHERE theme_id = ?",
            (result["research_case_id"],),
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("verdict", "expected_status", "expected_stage", "approval_count"),
    [
        ("research_positive", "research_positive", "waiting_for_approval", 1),
        ("research_watch", "research_watch", "observing", 0),
        ("research_reject", "research_reject", "completed", 0),
        ("research_unavailable", "research_unavailable", "stopped", 0),
    ],
)
def test_workbench_persists_synthesizer_verdict_and_two_stage_trace(
    tmp_path, verdict, expected_status, expected_stage, approval_count,
):
    db_path = tmp_path / f"research-{verdict}.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    delegate = _TwoPhaseLLM(verdict=verdict)
    from backend.services.llm_client import LLMCallResult

    class _DiagnosticLLM:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def create_message(self, **kwargs):
            response = delegate.create_message(**kwargs)
            diagnostic = {
                "stage": kwargs.get("stage"),
                "provider": delegate.get_provider_name(),
                "model": delegate.get_model_name(),
                "request_started_at": datetime.now().astimezone().isoformat(),
                "duration_ms": 0.0,
                "status": "success",
                "exception_class": None,
                "http_status": None,
                "provider_code": None,
                "timeout": False,
                "input_bytes": len(
                    json.dumps(kwargs, ensure_ascii=False, default=str).encode("utf-8")
                ),
                "source_count": kwargs.get("source_count"),
                "output_parse_reached": False,
            }
            return LLMCallResult(response, diagnostic)

    llm = _DiagnosticLLM()
    runner = _real_two_phase_runner(db, llm_client=llm)
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == expected_stage
    assert llm.calls == 2
    if verdict == "research_positive":
        assert body["approval_card"] is not None
        assert body["approval_card"]["allowed_decisions"] == [
            "continue", "stop", "downgrade_to_observation"
        ]
    else:
        assert body["approval_card"] is None

    timeline = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    ).json()["timeline"]
    result = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    diagnostics = result["serenity_call_diagnostics"]
    assert len(diagnostics) == 1
    synthesizer_diagnostic = diagnostics[0]
    assert synthesizer_diagnostic["stage"] == "synthesizer"
    assert synthesizer_diagnostic["provider"] == "fixture-provider"
    assert synthesizer_diagnostic["model"] == "fixture-model"
    assert synthesizer_diagnostic["status"] == "success"
    assert synthesizer_diagnostic["input_bytes"] > 0
    assert synthesizer_diagnostic["source_count"] == 1
    assert synthesizer_diagnostic["company_source_count"] == 0
    assert synthesizer_diagnostic["financial_source_count"] == 1
    assert synthesizer_diagnostic["announcement_source_count"] == 0
    assert synthesizer_diagnostic["response_received"] is True
    assert synthesizer_diagnostic["parse_reached"] is True
    assert result["research_verdict"] == verdict
    assert result["research_status"] == expected_status
    expected_reason = (
        "fixture missing-data reason"
        if verdict == "research_unavailable"
        else "fixture verdict reason"
    )
    assert result["research_reason"] == expected_reason
    if verdict == "research_unavailable":
        assert result["supporting_evidence"] == []
        assert result["counter_evidence"] == []
        assert result["invalidation_conditions"] == []
        assert result["evidence_gaps"] == [
            "fixture evidence boundary", "fixture unavailable gap"
        ]
    else:
        assert result["supporting_evidence"] == ["financials:603002.SH:0"]
        assert result["counter_evidence"] == [{
            "description": "fixture counter risk",
            "source_record_id": "financials:603002.SH:0",
        }]
        assert result["invalidation_conditions"] == [
            "603002.SH 宏昌电子产能是否落实？"
        ]
        assert result["evidence_gaps"] == [
            "fixture evidence boundary", "fixture verdict evidence gap"
        ]
    assert [
        (call["stage"], call["sequence"], call["status"])
        for call in result["serenity_stage_trace"]
    ] == [("planner", 1, "success"), ("synthesizer", 2, "success")]
    for call in result["serenity_stage_trace"]:
        assert call["called_at"]
        assert call["provider"] == "fixture-provider"
        assert call["model"] == "fixture-model"
        assert "request_id" not in call
        assert not ({"prompt", "messages", "authorization", "token"} & set(call))

    # Verify durable outcome and approval behavior through a fresh SQLite connection.
    with sqlite3.connect(db_path) as check:
        theme_row = check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (result["research_case_id"],),
        ).fetchone()
        persisted = json.loads(theme_row[0])
        assert persisted["serenity_call_diagnostics"] == diagnostics
        assert persisted["research_verdict"] == verdict
        assert persisted["serenity_stage_trace"] == result["serenity_stage_trace"]
        for field in (
            "research_status", "research_reason", "supporting_evidence",
            "counter_evidence", "invalidation_conditions", "evidence_gaps",
            "serenity_stage_trace",
        ):
            assert persisted[field] == result[field]
        session_state = check.execute(
            "SELECT workflow_state FROM agent_sessions WHERE session_id = ?",
            (body["conversation_id"],),
        ).fetchone()[0]
        assert session_state == expected_stage
        assert check.execute(
            "SELECT COUNT(*) FROM agent_approval_cards WHERE session_id = ?",
            (body["conversation_id"],),
        ).fetchone()[0] == approval_count
        if approval_count:
            card_row = check.execute(
                "SELECT card_data FROM agent_approval_cards WHERE session_id = ?",
                (body["conversation_id"],),
            ).fetchone()
            assert card_row is not None
            card = json.loads(card_row[0])
            assert card["allowed_decisions"] == [
                "continue", "stop", "downgrade_to_observation"
            ]
            assert card["artifact_ids"] == [
                f"research_result_{result['research_case_id']}"
            ]
            assert card["decision"] is None
            assert card["decided_by"] is None
        assert check.execute(
            "SELECT COUNT(*) FROM research_candidates WHERE theme_id = ?",
            (result["research_case_id"],),
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "synthesis_payload",
    [
        {
            "demand_driver": "fixture demand",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": [],
        },
        {
            "demand_driver": "fixture demand",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": [],
            "candidate_verdicts": {"603002.SH": {
                "verdict": "buy",
                "reason": "fixture reason",
                "supporting_source_ids": ["financials:603002.SH:0"],
                "counter_evidence": [],
                "invalidation_conditions": ["603002.SH demand fails"],
                "evidence_gaps": [],
            }},
        },
        {
            "demand_driver": "fixture demand",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": [],
            "candidate_verdicts": {"603002.SH": {
                "verdict": "research_positive",
                "reason": "fixture reason",
                "supporting_source_ids": ["financials:600000.SH:0"],
                "counter_evidence": [],
                "invalidation_conditions": ["603002.SH demand fails"],
                "evidence_gaps": [],
            }},
        },
        "not valid JSON",
    ],
)
def test_workbench_invalid_or_missing_synthesizer_verdict_is_unavailable(
    tmp_path, synthesis_payload,
):
    db_path = tmp_path / "research-invalid-verdict.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    llm = _TwoPhaseLLM(synthesis_payload=synthesis_payload)
    runner = _real_two_phase_runner(db, llm_client=llm)
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "stopped"
    assert body["approval_card"] is None
    assert llm.calls == 2
    timeline = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    ).json()["timeline"]
    result = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    assert result["research_status"] == "research_unavailable"
    assert result["research_verdict"] == "research_unavailable"
    assert result["serenity_stage_trace"][-1]["stage"] == "synthesizer"
    assert result["serenity_stage_trace"][-1]["status"] == "failure"

    with sqlite3.connect(db_path) as check:
        assert check.execute(
            "SELECT COUNT(*) FROM agent_approval_cards WHERE session_id = ?",
            (body["conversation_id"],),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM research_candidates WHERE theme_id = ?",
            (result["research_case_id"],),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM evidence_snapshots WHERE candidate_id LIKE ?",
            (f"cand_{result['research_case_id']}%",),
        ).fetchone()[0] == 0
        persisted = check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (result["research_case_id"],),
        ).fetchone()[0]
        persisted_result = json.loads(persisted)
        assert persisted_result["serenity_stage_trace"][-1]["status"] == "failure"
        assert check.execute(
            "SELECT COUNT(*) FROM agent_approval_cards WHERE session_id = ?",
            (body["conversation_id"],),
        ).fetchone()[0] == 0


def test_secret_shaped_response_id_is_not_persisted_or_returned(tmp_path):
    sentinel = "sk-FAKE_RESPONSE_METADATA_SENTINEL_NOT_A_CREDENTIAL"
    db_path = tmp_path / "research-secret-shaped-id.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    llm = _TwoPhaseLLM(response_ids=[sentinel, "fixture-request-2"])
    runner = _real_two_phase_runner(db, llm_client=llm)
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert response.status_code == 200
    assert llm.calls == 2
    body = response.json()
    timeline_response = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    )
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["timeline"]
    artifact = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    with sqlite3.connect(db_path) as check:
        stored = check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (artifact["research_case_id"],),
        ).fetchone()[0]

    surfaces = (
        response.text,
        timeline_response.text,
        json.dumps(artifact, ensure_ascii=False),
        stored,
        json.dumps(artifact["serenity_stage_trace"], ensure_ascii=False),
    )
    escaped = any(sentinel in surface for surface in surfaces)
    assert not escaped, "credential-shaped provider metadata escaped a Workbench surface"
    assert all("request_id" not in call for call in artifact["serenity_stage_trace"])


def test_workbench_research_result_persists_readable_company_financial_and_sse_sources(
    tmp_path,
):
    from datetime import date, timedelta

    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    retrieved_at = datetime.now()
    financial_date = retrieved_at.date() - timedelta(days=45)
    announcement_date = retrieved_at.date() - timedelta(days=10)
    announcement_title = "宏昌电子第七届董事会第四次会议决议公告"
    announcement_url = (
        "https://static.sse.com.cn/disclosure/listedinfo/announcement/"
        f"c/new/{announcement_date.isoformat()}/603002_"
        f"{announcement_date.strftime('%Y%m%d')}_FIXTURE.pdf"
    )
    financial_summary = (
        f"报告期: {financial_date.strftime('%Y%m%d')}; "
        f"披露日: {financial_date.strftime('%Y%m%d')}; 营业总收入: 123.0"
    )
    announcement_summary = (
        f"{announcement_date.isoformat()} 披露《{announcement_title}》"
    )

    class SourceFixtureSerenityTools(SerenityTools):
        def __init__(self):
            super().__init__(validator=validator)

        def retrieve_supply_chain(self, **_kwargs):
            records = [
                ResearchSource(
                    source_record_id="financials:603002.SH:0",
                    source_type="financial_report",
                    source_quality="first_hand",
                    title="宏昌电子 2026 年报表",
                    published_at=financial_date,
                    retrieved_at=retrieved_at,
                    summary=financial_summary,
                ),
                ResearchSource(
                    source_record_id="stock_company:603002.SH:0",
                    source_type="unknown",
                    source_quality="weak",
                    title="公司主营业务: 宏昌电子",
                    retrieved_at=retrieved_at,
                    summary="主营业务: 电子元器件的研发、生产和销售。",
                ),
                ResearchSource(
                    source_record_id="announcements:603002.SH:0",
                    source_type="announcement",
                    source_quality="first_hand",
                    title=announcement_title,
                    published_at=announcement_date,
                    retrieved_at=retrieved_at,
                    summary=announcement_summary,
                    source_url=announcement_url,
                    announcement_code="603002.SH",
                    gaps=["full_text_unavailable"],
                ),
            ]
            return SerenityToolResult(
                tool_name="retrieve_supply_chain",
                records=records,
                total_found=len(records),
                gaps=[],
                errors=[],
                retrieved_at=retrieved_at,
            )

    runner = SerenityAgentRunner(
        llm_client=_TwoPhaseLLM(),
        validator=validator,
        tools=SourceFixtureSerenityTools(),
        mode="real",
        db=db,
        execution_mode="two_phase",
    )
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "observing"
    timeline = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    ).json()["timeline"]
    research_result = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )

    source_records = research_result.get("research_sources")
    assert isinstance(source_records, list)
    sources_by_id = {
        source["source_record_id"]: source for source in source_records
    }
    assert set(sources_by_id) == {
        "financials:603002.SH:0",
        "stock_company:603002.SH:0",
        "announcements:603002.SH:0",
    }
    assert sources_by_id["financials:603002.SH:0"]["summary"] == financial_summary
    assert sources_by_id["stock_company:603002.SH:0"]["summary"] == (
        "主营业务: 电子元器件的研发、生产和销售。"
    )
    announcement = sources_by_id["announcements:603002.SH:0"]
    assert announcement["title"] == announcement_title
    assert announcement["published_at"] == announcement_date.isoformat()
    assert announcement["source_url"] == announcement_url
    assert "full_text_unavailable" in announcement["gaps"]
    assert any(
        "full_text_unavailable" in gap
        for gap in research_result["evidence_gaps"]
    )

    with sqlite3.connect(db_path) as independent_check:
        stored_row = independent_check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (research_result["research_case_id"],),
        ).fetchone()
    assert stored_row is not None
    stored_output = json.loads(stored_row[0])
    assert stored_output["research_sources"] == source_records
    assert any(
        "full_text_unavailable" in gap
        for gap in stored_output["evidence_gaps"]
    )


def test_friend_stock_case_output_and_artifacts_rollback_on_result_write_failure(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    init_agent_workbench_db(db.conn)
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db)
    identity = _MacroHongIdentityFixture().resolve("宏昌电子", None)
    route_decision = SimpleNamespace(route_reason="fixture")

    from backend.api import workbench_handlers
    from backend.api.workbench_handlers import handle_friend_stock

    original_attach = workbench_handlers.attach_artifact_ref

    def fail_research_result_write(
        conn, artifact_ref, content=None, *, commit=True
    ):
        if artifact_ref.artifact_type == "research_result":
            raise RuntimeError("injected research_result write failure")
        return original_attach(
            conn, artifact_ref, content=content, commit=commit
        )

    monkeypatch.setattr(
        workbench_handlers, "attach_artifact_ref", fail_research_result_write
    )

    with pytest.raises(RuntimeError, match="injected research_result write failure"):
        handle_friend_stock(
            db.conn,
            "sess_failure_fixture",
            "朋友推荐了宏昌电子，帮我看看值不值得买",
            identity,
            route_decision,
            datetime.now(),
            validator=validator,
            serenity_runner=runner,
            market_data_provider=None,
            research_db=db,
        )

    with sqlite3.connect(db_path) as check:
        assert check.execute(
            "SELECT COUNT(*) FROM research_themes WHERE theme_id LIKE 'case_%'"
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM research_candidates"
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM evidence_snapshots"
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM agent_artifact_refs WHERE session_id = ?",
            ("sess_failure_fixture",),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM agent_timeline_items WHERE session_id = ?",
            ("sess_failure_fixture",),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM agent_approval_cards WHERE session_id = ?",
            ("sess_failure_fixture",),
        ).fetchone()[0] == 0


def test_friend_stock_runs_external_research_before_sqlite_transaction(tmp_path):
    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    init_agent_workbench_db(db.conn)
    observed_transaction_states = []
    runner = _real_two_phase_runner(
        db,
        transaction_probe=lambda: observed_transaction_states.append(
            db.conn.in_transaction
        ),
    )

    from backend.api.workbench_handlers import handle_friend_stock

    result = handle_friend_stock(
        db.conn,
        "sess_transaction_boundary",
        "朋友推荐了宏昌电子，帮我看看值不值得买",
        _MacroHongIdentityFixture().resolve("宏昌电子", None),
        SimpleNamespace(route_reason="fixture"),
        datetime.now(),
        validator=_DeterministicValidator(),
        serenity_runner=runner,
        market_data_provider=None,
        research_db=db,
    )

    assert result.workflow_state == "observing"
    assert observed_transaction_states
    assert all(state is False for state in observed_transaction_states)


def test_friend_stock_rejects_research_db_connection_mismatch_without_partial_state(
    tmp_path,
):
    workbench_db_path = tmp_path / "workbench.sqlite"
    research_db_path = tmp_path / "research.sqlite"
    workbench_db = ResearchDB(db_path=str(workbench_db_path))
    research_db = ResearchDB(db_path=str(research_db_path))
    init_agent_workbench_db(workbench_db.conn)

    from backend.api.workbench_handlers import handle_friend_stock

    with pytest.raises(RuntimeError, match="research_db_connection_mismatch"):
        handle_friend_stock(
            workbench_db.conn,
            "sess_connection_mismatch",
            "朋友推荐了宏昌电子，帮我看看值不值得买",
            _MacroHongIdentityFixture().resolve("宏昌电子", None),
            SimpleNamespace(route_reason="fixture"),
            datetime.now(),
            validator=None,
            serenity_runner=None,
            market_data_provider=None,
            research_db=research_db,
        )

    with sqlite3.connect(workbench_db_path) as check:
        assert check.execute(
            "SELECT COUNT(*) FROM agent_artifact_refs WHERE session_id = ?",
            ("sess_connection_mismatch",),
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM agent_timeline_items WHERE session_id = ?",
            ("sess_connection_mismatch",),
        ).fetchone()[0] == 0

    with sqlite3.connect(research_db_path) as check:
        assert check.execute(
            "SELECT COUNT(*) FROM research_themes"
        ).fetchone()[0] == 0


def test_workbench_zero_source_real_runner_is_unavailable(tmp_path):
    db = ResearchDB(db_path=str(tmp_path / "research.sqlite"))
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db, with_source=False)
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "stopped"
    assert "research_unavailable" in response.json()["agent_reply"]
    timeline = client.get(f"/api/agent/workbench/{response.json()['conversation_id']}").json()["timeline"]
    result = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    assert result["research_status"] == "research_unavailable"
    assert result["evidence_gaps"]


def test_workbench_stub_and_fake_runner_are_unavailable(tmp_path):
    fixture = _MacroHongIdentityFixture()

    stub_db = ResearchDB(db_path=str(tmp_path / "stub.sqlite"))
    stub_app = create_research_app(
        db=stub_db,
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        validator=ResearchValidator(tushare_config=TushareConfig(token=None)),
        stock_resolver_override=fixture,
    )
    stub_response = TestClient(stub_app).post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert stub_response.json()["stage"] == "stopped"
    assert "research_unavailable" in stub_response.json()["agent_reply"]

    fake_db = ResearchDB(db_path=str(tmp_path / "fake.sqlite"))
    fake_app = create_research_app(
        db=fake_db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=_DeterministicValidator(),
        serenity_runner=FakeSerenityRunner(),
        allow_test_serenity_runner=True,
        stock_resolver_override=fixture,
    )
    fake_response = TestClient(fake_app).post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert fake_response.json()["stage"] == "stopped"
    assert "research_unavailable" in fake_response.json()["agent_reply"]


def test_workbench_no_runner_is_unavailable_and_persisted(tmp_path):
    db = ResearchDB(db_path=str(tmp_path / "research.sqlite"))
    init_agent_workbench_db(db.conn)
    from backend.api.workbench_handlers import handle_friend_stock

    result = handle_friend_stock(
        db.conn,
        "sess_fixture",
        "朋友推荐了宏昌电子，帮我看看值不值得买",
        _MacroHongIdentityFixture().resolve("宏昌电子", None),
        SimpleNamespace(route_reason="fixture"),
        datetime.now(),
        validator=None,
        serenity_runner=None,
        market_data_provider=None,
        research_db=db,
    )

    assert result.workflow_state == "stopped"
    assert result.artifact_ids
    case_id = result.artifact_ids[0]
    output = db.get_theme(case_id).research_output
    assert output["research_status"] == "research_unavailable"
    assert output["evidence_gaps"]


def test_run_research_theme_route_accepts_traceable_two_phase_fixture(tmp_path):
    db = ResearchDB(db_path=str(tmp_path / "research.sqlite"))
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db)
    client = TestClient(_workbench_app(db, runner, validator), raise_server_exceptions=False)

    theme_response = client.post(
        "/api/research/themes",
        json={
            "theme_name": "宏昌电子研究",
            "background": "朋友推荐宏昌电子",
            "source_type": "manual_stock",
        },
    )
    assert theme_response.status_code == 200
    theme_id = theme_response.json()["theme_id"]

    response = client.post(
        f"/api/research/themes/{theme_id}/run-research",
        json={"ticker": "603002.SH", "company_name": "宏昌电子"},
    )

    assert response.status_code == 200, response.text
    output = response.json()
    assert output["candidate_rationales"]["603002.SH"]["supporting_source_ids"] == [
        "financials:603002.SH:0"
    ]


def test_default_real_two_phase_factory_enables_sse_announcement_transport(
    tmp_path, monkeypatch,
):
    import backend.services.data_tools as data_tools_module
    import backend.services.llm_client as llm_client_module
    import pandas as pd
    from zoneinfo import ZoneInfo

    monkeypatch.setenv("RESEARCH_LLM_API_KEY", "fixture-only")
    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-only")

    tushare_calls = []

    class NoNetworkTushare:
        def query(self, api_name, **kwargs):
            tushare_calls.append((api_name, kwargs))
            if api_name == "income":
                return pd.DataFrame([{
                    "ts_code": "603002.SH",
                    "end_date": today.strftime("%Y%m%d"),
                    "ann_date": today.strftime("%Y%m%d"),
                    "total_revenue": 1000000,
                    "n_income": 100000,
                    "n_income_attr_p": 90000,
                    "basic_eps": 0.1,
                }])
            return []

    validator = _DeterministicValidator()
    validator.tushare_client = NoNetworkTushare()
    fake_llm = _TwoPhaseLLM()
    monkeypatch.setattr(llm_client_module, "LLMClient", lambda: fake_llm)

    transport_calls = []
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    announcement_date = today.isoformat()
    compact_date = today.strftime("%Y%m%d")
    announcement_url = (
        "https://static.sse.com.cn/disclosure/listedinfo/announcement/"
        f"c/new/{announcement_date}/603002_{compact_date}_FIXTURE.pdf"
    )
    pdf_text_sentinel = "PDF_TEXT_SENTINEL_MUST_NOT_ENTER_SYNTHESIS"
    response_body = json.dumps({
        "result": [{
            "security_Code": "603002",
            "SSEDate": announcement_date,
            "title": "宏昌电子公告元数据fixture",
            "URL": announcement_url,
            "fullText": pdf_text_sentinel,
        }],
        "pageHelp": {"pageSize": 20},
    }, ensure_ascii=False)

    original_data_tools = data_tools_module.DataToolsService

    def local_sse_transport(self, url, *, headers, timeout):
        transport_calls.append((url, headers, timeout))
        return 200, "application/json; charset=UTF-8", response_body

    monkeypatch.setattr(
        original_data_tools, "_fetch_sse_response", local_sse_transport,
    )

    created_data_tools = []

    class RecordingDataToolsService(original_data_tools):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_data_tools.append(self)

    monkeypatch.setattr(
        data_tools_module, "DataToolsService", RecordingDataToolsService,
    )

    def forbid_real_network(*_args, **_kwargs):
        raise AssertionError("test must not perform an SSE network request")

    monkeypatch.setattr(data_tools_module, "urlopen", forbid_real_network)

    db = ResearchDB(db_path=str(tmp_path / "two-phase-assembly.sqlite"))
    app = create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=validator,
        market_data_provider=lambda *_args: {},
        stock_resolver_override=_MacroHongIdentityFixture(),
    )

    assert app.state.db is db
    assert len(created_data_tools) == 1
    result = created_data_tools[0].get_announcements("603002.SH")

    assert result.source == "sse_company_announcements"
    assert result.raw_data[0]["code"] == "603002.SH"
    assert result.raw_data[0]["url"] == announcement_url
    assert len(transport_calls) == 1
    assert tushare_calls == []
    assert fake_llm.calls == 0

    client = TestClient(app)
    workbench_response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert workbench_response.status_code == 200, workbench_response.text
    assert workbench_response.json()["stage"] == "observing"
    assert fake_llm.calls == 2
    assert len(fake_llm.requests) == 2
    synthesis_pack = fake_llm.requests[1]["messages"][0]["content"]
    assert "宏昌电子公告元数据fixture" in synthesis_pack
    assert announcement_date in synthesis_pack
    assert announcement_url in synthesis_pack
    assert "announcement_list_metadata_only" in synthesis_pack
    assert "full_text_unavailable" in synthesis_pack
    assert pdf_text_sentinel not in synthesis_pack
    assert len(transport_calls) == 2
    assert not any(api_name == "anns_d" for api_name, _kwargs in tushare_calls)


def test_provider_exception_sentinel_does_not_escape_researchcase_surfaces(
    tmp_path, capsys, monkeypatch,
):
    import backend.services.llm_client as llm_client_module

    failure = {"message": ""}

    def raise_timeout(**_kwargs):
        raise TimeoutError(failure["message"])

    provider = SimpleNamespace(messages=SimpleNamespace(create=raise_timeout))
    monkeypatch.setattr(llm_client_module, "Anthropic", lambda **_kwargs: provider)

    class _RealLLMClient:
        def __new__(cls, sentinel):
            failure["message"] = sentinel
            return llm_client_module.LLMClient(
                api_key=fake_bearer,
                base_url="https://api.anthropic.com",
                model="test-model",
            )

    _SentinelRaisingLLM = _RealLLMClient
    sentinel = "FAKE_PROVIDER_SENTINEL_NOT_A_CREDENTIAL"
    fake_bearer = "FAKE_BEARER_TOKEN_FOR_TEST_ONLY"
    fake_authorization_header = f"Authorization: Bearer {fake_bearer}"
    db_path = tmp_path / "research.sqlite"
    db = ResearchDB(db_path=str(db_path))
    validator = _DeterministicValidator()
    llm = _SentinelRaisingLLM(
        f"{sentinel}; {fake_authorization_header}"
    )
    runner = SerenityAgentRunner(
        llm_client=llm,
        validator=validator,
        tools=_DeterministicSerenityTools(validator, with_source=False),
        mode="real",
        db=db,
        execution_mode="two_phase",
    )
    client = TestClient(_workbench_app(db, runner, validator))

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    timeline_response = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    )
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["timeline"]
    result_artifact = next(
        json.loads(item["content"]["artifact_content"])
        for item in timeline
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "research_result"
    )
    research_id = result_artifact["research_case_id"]
    theme_response = client.get(f"/api/research/themes/{research_id}")
    assert theme_response.status_code == 200
    run_response = client.post(
        f"/api/research/themes/{research_id}/run-research",
        json={"ticker": "603002.SH", "company_name": "宏昌电子"},
    )
    assert run_response.status_code == 503
    assert run_response.json()["detail"] == (
        "research_unavailable: serenity_execution_failed"
    )
    assert result_artifact["evidence_gaps"] == [
        "research_unavailable: serenity_execution_failed"
    ]
    assert result_artifact["serenity_stage_trace"] == [{
        "stage": "planner",
        "sequence": 1,
        "called_at": result_artifact["serenity_stage_trace"][0]["called_at"],
        "provider": llm.get_provider_name(),
        "model": llm.get_model_name(),
        "status": "failure",
    }]

    with sqlite3.connect(db_path) as check:
        stored = check.execute(
            "SELECT research_output FROM research_themes WHERE theme_id = ?",
            (research_id,),
        ).fetchone()
    assert stored is not None
    persisted_output = json.loads(stored[0])
    diagnostics = persisted_output.get("serenity_call_diagnostics")
    assert diagnostics == []
    assert json.loads(stored[0])["evidence_gaps"] == [
        "research_unavailable: serenity_execution_failed"
    ]
    captured = capsys.readouterr()
    surfaces = {
        "Workbench response": response.text,
        "timeline response": timeline_response.text,
        "timeline artifact": json.dumps(result_artifact, ensure_ascii=False),
        "ResearchCase response": theme_response.text,
        "durable ResearchCase": stored[0],
        "run-research 503 response": run_response.text,
        "stdout": captured.out,
        "stderr": captured.err,
        "stage trace": json.dumps(result_artifact["serenity_stage_trace"]),
    }
    forbidden_values = (sentinel, fake_authorization_header, fake_bearer)
    leaking_surfaces = [
        f"{name}: {value}"
        for name, content in surfaces.items()
        for value in forbidden_values
        if value in content
    ]
    assert not leaking_surfaces, f"sentinel escaped to: {leaking_surfaces}"


def test_tushare_identity_exception_sentinel_does_not_escape_workbench(
    tmp_path, capsys,
):
    from backend.services.stock_identity_resolver import StockIdentityResolver

    sentinel = "FAKE_TUSHARE_SENTINEL_NOT_A_CREDENTIAL"
    db = ResearchDB(db_path=str(tmp_path / "identity.sqlite"))
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db)
    resolver = StockIdentityResolver(
        tushare_client=_SentinelRaisingTushare(sentinel),
    )
    app = create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=validator,
        serenity_runner=runner,
        allow_test_serenity_runner=True,
        stock_resolver_override=resolver,
    )
    client = TestClient(app)

    response = client.post(
        "/api/agent/workbench/message",
        json={"message": "朋友推荐了宏昌电子，帮我看看值不值得买"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    timeline_response = client.get(
        f"/api/agent/workbench/{body['conversation_id']}"
    )
    assert timeline_response.status_code == 200
    captured = capsys.readouterr()

    assert sentinel not in response.text
    assert sentinel not in timeline_response.text
    assert sentinel not in captured.out
    assert sentinel not in captured.err


def test_run_research_no_traceable_sources_does_not_echo_evidence_gaps(
    tmp_path, monkeypatch,
):
    from backend.services import friend_stock_flow

    sentinel = "FAKE_EVIDENCE_GAP_SENTINEL_ONLY"
    fake_bearer = "FAKE_EVIDENCE_GAP_BEARER_ONLY"
    db = ResearchDB(db_path=str(tmp_path / "no-traceable-source.sqlite"))
    validator = _DeterministicValidator()
    runner = _real_two_phase_runner(db)
    app = _workbench_app(db, runner, validator)
    client = TestClient(app, raise_server_exceptions=False)

    theme_response = client.post(
        "/api/research/themes",
        json={
            "theme_name": "fixture research case",
            "background": "fixture only",
            "source_type": "manual_stock",
        },
    )
    assert theme_response.status_code == 200
    theme_id = theme_response.json()["theme_id"]
    research_output = {
        "candidate_rationales": {
            "603002.SH": {
                "rationale": "fixture rationale",
                "supporting_source_ids": [],
            }
        },
        "evidence_gaps": [
            sentinel,
            f"Authorization: Bearer {fake_bearer}",
        ],
    }
    monkeypatch.setattr(
        friend_stock_flow.FriendStockFlowService,
        "run_industry_research",
        lambda self, **_kwargs: research_output,
    )
    monkeypatch.setattr(
        friend_stock_flow,
        "validate_serenity_research_output",
        lambda *_args, **_kwargs: {},
    )

    response = client.post(
        f"/api/research/themes/{theme_id}/run-research",
        json={"ticker": "603002.SH", "company_name": "fixture company"},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    leaking_fields = [
        field for field, value in (
            ("evidence-gap sentinel", sentinel),
            ("Authorization bearer", fake_bearer),
        ) if value in detail
    ]
    assert not leaking_fields, f"synthetic evidence gap escaped: {leaking_fields}"
    assert detail == "research_unavailable: traceable_sources_unavailable"
