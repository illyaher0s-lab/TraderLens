import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from tests.fake_validator import FakeValidator


def _candidate(index):
    return {
        "symbol": f"600{index:03d}.SH",
        "score": 0.9 - index / 1000,
        "features": {
            "medium_relative_strength": {"raw": 0.1, "rank": index + 1},
            "short_trend": {"raw": 0.02, "rank": index + 1},
            "liquidity": {"raw": 1000000.0, "rank": index + 1},
            "volatility": {"raw": 0.01, "rank": index + 1},
        },
        "status": "watch" if index == 0 else "research_candidate",
        "reasons": ["fixed_daily_market_scout_rank"],
        "soft_risks": ["limit_reached"] if index == 0 else [],
    }


def _ok_result():
    return {
        "status": "ok",
        "reason": None,
        "as_of_date": "2026-07-31",
        "snapshot_path": "data/current_market_snapshots/as_of_date=2026-07-31/manifest.json",
        "snapshot_hash": "a" * 64,
        "candidate_count": 20,
        "candidates": [_candidate(index) for index in range(20)],
        "excluded_counts": {"stock_st": 2},
        "industry_breadth_status": "unknown",
        "candidate_is_signal": False,
    }


class FakeScout:
    result = _ok_result()

    def __init__(self, repo_root):
        self.repo_root = Path(repo_root)

    def scan(self):
        return self.result


def _client(monkeypatch, result=None, serenity_runner=None):
    FakeScout.result = result or _ok_result()
    monkeypatch.setattr("backend.services.daily_market_scout.DailyMarketScout", FakeScout)
    app_kwargs = {
        "db": ResearchDB(":memory:"),
        "conversation_mode": "deterministic" if serenity_runner is None else "real",
        "serenity_execution_mode": "stub" if serenity_runner is None else "two_phase",
        "validator": FakeValidator(),
        "market_data_provider": lambda symbol, as_of: {"close": 10.0, "trade_date": str(as_of)},
        "stock_resolver_fixture": {
            "603002.SH": {
                "ticker": "603002.SH",
                "company_name": "宏昌电子",
                "exchange": "SSE",
            }
        },
    }
    if serenity_runner is not None:
        app_kwargs.update({
            "serenity_runner": serenity_runner,
            "allow_test_serenity_runner": True,
        })
    app = create_research_app(**app_kwargs)
    return TestClient(app)



def _market_scan_payload(client, response):
    assert response.status_code == 200
    session = client.get(f"/api/agent/workbench/{response.json()['conversation_id']}")
    assert session.status_code == 200
    artifact = next(
        item["content"]
        for item in session.json()["timeline"]
        if item["type"] == "artifact_ref"
        and item["content"]["artifact_type"] == "market_scan_result"
    )
    return json.loads(artifact["artifact_content"])


@pytest.mark.parametrize("message", ["帮我选股", "看昨天市场", "今天关注什么"])
def test_unscoped_market_language_routes_to_market_scan(monkeypatch, message):
    client = _client(monkeypatch)
    response = client.post("/api/agent/workbench/message", json={"message": message})
    data = response.json()
    assert data["workflow_type"] == "market_scan"
    payload = _market_scan_payload(client, response)
    assert payload["candidate_count"] == 20
    assert len(payload["candidates"]) == 5
    assert payload["candidate_is_signal"] is False
    assert payload["as_of_date"] == "2026-07-31"
    assert all("reasons" in card and "soft_risks" in card for card in payload["candidates"])


def test_market_scan_hard_block_is_visible_and_not_a_signal(monkeypatch):
    result = _ok_result()
    result.update({"status": "hard_block", "reason": "hard_block:data_stale", "candidate_count": 0, "candidates": []})
    client = _client(monkeypatch, result)
    response = client.post("/api/agent/workbench/message", json={"message": "帮我选股"})
    assert response.json()["workflow_type"] == "market_scan"
    assert "hard_block:data_stale" in response.json()["agent_reply"]
    payload = _market_scan_payload(client, response)
    assert payload["status"] == "hard_block"
    assert payload["candidate_is_signal"] is False
    assert payload["candidates"] == []


def test_stock_message_keeps_existing_friend_stock_route(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/api/agent/workbench/message", json={"message": "603002"})
    assert response.status_code == 200
    assert response.json()["workflow_type"] == "friend_stock"
    session = client.get(f"/api/agent/workbench/{response.json()['conversation_id']}")
    assert not any(
        item["content"]["artifact_type"] == "market_scan_result"
        for item in session.json()["timeline"]
        if item["type"] == "artifact_ref"
    )


def test_existing_timeline_has_market_scan_card_rendering():
    source = (Path(__file__).parents[1] / "frontend/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    assert "market_scan_result" in source
    assert "candidate_is_signal" in source
    assert "support" in source
    assert "counter" in source
    assert "unknown" in source
    assert "scenarios" in source
    assert "confidence" in source


class ParallelLaneRunner:
    def __init__(self, *, failing_lane=None):
        self.failing_lane = failing_lane
        self.active = 0
        self.peak = 0
        self.calls = []
        self._lock = threading.Lock()
        self._barrier = threading.Barrier(2)

    def __call__(self, candidates, lane):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append(lane)
        try:
            self._barrier.wait(timeout=2)
            if lane == self.failing_lane:
                raise RuntimeError("lane unavailable")
            return {
                candidate["symbol"]: {
                    "status": "ok",
                    "source": f"fake_{lane}_source",
                    "fact_date": "2026-07-31",
                    "facts": [f"{lane} fact"],
                    "unknown": [],
                    "scenarios": {"bull": "known", "base": "known", "bear": "known"},
                    "confidence": "medium",
                }
                for candidate in candidates
            }
        finally:
            with self._lock:
                self.active -= 1


def _lane_client(monkeypatch, lane_runner):
    FakeScout.result = _ok_result()
    monkeypatch.setattr("backend.services.daily_market_scout.DailyMarketScout", FakeScout)
    app = create_research_app(
        db=ResearchDB(":memory:"),
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        validator=FakeValidator(),
        market_data_provider=lambda symbol, as_of: {"close": 10.0, "trade_date": str(as_of)},
        stock_resolver_fixture={},
        market_scan_lane_runner=lane_runner,
    )
    return TestClient(app)


def test_market_scan_runs_two_parallel_lanes_and_preserves_scanner_facts(monkeypatch):
    runner = ParallelLaneRunner()
    client = _lane_client(monkeypatch, runner)
    response = client.post("/api/agent/workbench/message", json={"message": "帮我选股"})
    payload = _market_scan_payload(client, response)
    card = payload["candidates"][0]
    original = _ok_result()["candidates"][0]
    assert runner.peak == 2
    assert set(runner.calls) == {"support", "counter"}
    for key in ("symbol", "score", "features", "status", "reasons", "soft_risks"):
        assert card[key] == original[key]
    assert card["support"]["source"] == "fake_support_source"
    assert card["counter"]["source"] == "fake_counter_source"
    assert card["support"]["fact_date"] == "2026-07-31"
    assert card["counter"]["scenarios"]["bear"] == "known"
    assert payload["candidate_is_signal"] is False
    timeline = client.get(f"/api/agent/workbench/{response.json()['conversation_id']}").json()["timeline"]
    assert any(item["type"] == "approval_card" for item in timeline)
    assert not any(
        item.get("content", {}).get("artifact_type") == "confirmed_candidate_pool"
        for item in timeline
    )
    assert any(theme.source_type == "market_scan" for theme in client.app.state.db.list_themes())


def test_market_scan_lane_failure_is_unknown_and_soft_risk_stays_watch(monkeypatch):
    runner = ParallelLaneRunner(failing_lane="counter")
    client = _lane_client(monkeypatch, runner)
    response = client.post("/api/agent/workbench/message", json={"message": "今天关注什么"})
    payload = _market_scan_payload(client, response)
    card = payload["candidates"][0]
    assert card["status"] == "watch"
    assert card["soft_risks"] == ["limit_reached"]
    assert card["counter"]["status"] == "unknown"
    assert card["counter"]["unknown"]
    assert card["counter"]["scenarios"]["bull"] == "unknown"


def test_default_market_scan_maps_one_serenity_output_to_both_lanes_without_changing_facts():
    from backend.api.workbench_handlers import _research_market_candidates
    from contracts.research import AgentHarnessConfig, CandidateStock, SerenityOutput
    from datetime import datetime

    candidates = [_candidate(index) for index in range(5)]
    runner_calls = []

    class FakeTwoPhaseRunner:
        def run(self, theme, manual_candidates):
            runner_calls.append([item.symbol for item in manual_candidates])
            assert len(manual_candidates) == 5
            output_candidates = []
            for index, item in enumerate(manual_candidates):
                output_candidates.append(CandidateStock(
                    candidate_id=f"research_{item.symbol}",
                    theme_id=theme.theme_id,
                    symbol=item.symbol,
                    source_type="market_scan",
                    match_reason=f"support fact {item.symbol}",
                    match_confidence="medium",
                    created_at=datetime.now(),
                    supporting_source_ids=[f"financials:{item.symbol}:0"],
                    counter_evidence=(
                        [{"description": f"counter fact {item.symbol}", "source_record_id": f"financials:{item.symbol}:0"}]
                        if index == 0 else []
                    ),
                    falsification_questions=([] if index == 0 else [f"verify {item.symbol}"]),
                    data_gaps=([] if index == 0 else [f"gap {item.symbol}"]),
                ))
            return SerenityOutput(
                theme_id=theme.theme_id,
                demand_driver="",
                value_chain_layers=[],
                suspected_bottleneck_layers=[],
                candidate_pool_raw=output_candidates,
                candidate_shortlist=output_candidates,
                hypothesis_draft=[],
                evidence_gaps=[],
                harness=AgentHarnessConfig(
                    execution_engine="two_phase",
                    llm_provider="fake",
                    tool_whitelist=["research_planner", "research_synthesizer"],
                    max_steps=2,
                    token_budget=1,
                ),
                created_at=datetime.now(),
            )

    support, counter = _research_market_candidates(
        candidates, lane_runner=None, serenity_runner=FakeTwoPhaseRunner(), evidence_runner=None
    )
    assert runner_calls == [[candidate["symbol"] for candidate in candidates]]
    assert set(support) == set(counter) == {candidate["symbol"] for candidate in candidates}
    assert support[candidates[0]["symbol"]]["status"] == "ok"
    assert counter[candidates[0]["symbol"]]["status"] == "ok"
    assert counter[candidates[1]["symbol"]]["status"] == "unknown"


def test_workbench_market_scan_maps_structured_serenity_batch_to_five_cards(monkeypatch):
    """真实 Workbench 入口把结构化 Serenity batch 映射为五卡双 lane。"""
    from contracts.research import AgentHarnessConfig, CandidateStock, CounterEvidence, SerenityOutput
    from datetime import datetime
    from tests.fake_serenity_runner import FakeSerenityRunner

    def structured_run(self, theme, manual_candidates):
        assert theme.source_type == "market_scan"
        assert len(manual_candidates) == 5
        output_candidates = [
            CandidateStock(
                candidate_id=f"structured_{candidate.symbol}",
                theme_id=theme.theme_id,
                symbol=candidate.symbol,
                source_type="market_scan",
                match_reason=f"support fact {candidate.symbol}",
                match_confidence="medium",
                created_at=datetime.now(),
                supporting_source_ids=[f"financials:{candidate.symbol}:0"],
                counter_evidence=[CounterEvidence(
                    description=f"counter fact {candidate.symbol}",
                    source_record_id=f"financials:{candidate.symbol}:0",
                )],
            )
            for candidate in manual_candidates
        ]
        return SerenityOutput(
            theme_id=theme.theme_id,
            demand_driver="",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            candidate_pool_raw=output_candidates,
            candidate_shortlist=output_candidates,
            hypothesis_draft=[],
            evidence_gaps=[],
            harness=AgentHarnessConfig(
                execution_engine="two_phase",
                llm_provider="fake",
                tool_whitelist=["structured_fake"],
                max_steps=2,
                token_budget=1,
            ),
            created_at=datetime.now(),
        )

    monkeypatch.setattr(FakeSerenityRunner, "run", structured_run)
    client = _client(monkeypatch, serenity_runner=FakeSerenityRunner())
    before_confirmed = client.app.state.db.conn.execute(
        "SELECT COUNT(*) FROM confirmed_candidates"
    ).fetchone()[0]

    response = client.post("/api/agent/workbench/message", json={"message": "帮我选股"})

    payload = _market_scan_payload(client, response)
    assert response.json()["workflow_type"] == "market_scan"
    assert [card["symbol"] for card in payload["candidates"]] == [
        card["symbol"] for card in _ok_result()["candidates"][:5]
    ]
    assert len(payload["candidates"]) == 5
    assert all(card["support"]["status"] == "ok" for card in payload["candidates"])
    assert all(card["counter"]["status"] == "ok" for card in payload["candidates"])
    assert all(card["support"]["facts"] for card in payload["candidates"])
    assert all(card["counter"]["facts"] for card in payload["candidates"])
    assert payload["candidate_is_signal"] is False
    after_confirmed = client.app.state.db.conn.execute(
        "SELECT COUNT(*) FROM confirmed_candidates"
    ).fetchone()[0]
    assert after_confirmed == before_confirmed
