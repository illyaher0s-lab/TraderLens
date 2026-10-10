import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.api.research import _safe_research_sentence
from backend.db.research import ResearchDB
from backend.services.data_tools import (
    DataToolsService,
    _is_510880_dividend_valuation,
    _trailing_yield_valuation_label,
)
from backend.services.discipline_review import DisciplineReviewService
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.llm_client import LLMCallResult
from contracts.live_trade import ExecutionObservationLog, TradeType


class QuoteClient:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def query(self, api, **kwargs):
        self.calls.append((api, kwargs))
        if api == "fund_daily":
            return pd.DataFrame(self.rows)
        return pd.DataFrame()


def test_fund_quote_uses_real_endpoint_and_filters_code_and_future_rows():
    client = QuoteClient([
        {"ts_code": "510880.SH", "trade_date": "20261007", "close": 3.368},
        {"ts_code": "510880.SH", "trade_date": "20261009", "close": 3.999},
        {"ts_code": "510300.SH", "trade_date": "20261008", "close": 4.0},
    ])

    result = DataToolsService(tushare_client=client).get_security_quote_snapshot(
        "510880.SH", "fund", as_of=date(2026, 10, 8), lookback_days=10,
    )

    assert result.source == "tushare_fund_daily"
    assert result.raw_data == [{
        "ts_code": "510880.SH",
        "trade_date": "2026-10-07",
        "close": 3.368,
    }]
    assert result.gaps == []
    assert result.errors == []
    assert [call[0] for call in client.calls] == ["fund_daily"]
    assert client.calls[0][1]["ts_code"] == "510880.SH"
    assert client.calls[0][1]["end_date"] == "20261008"


def _review_inputs():
    buy = ExecutionObservationLog(
        log_id="buy_008", draft_id=None, execution_card_id=None,
        signal_id=None, action_plan_id=None, capital_context_id=None,
        market_snapshot_id=None, confirmed_action="buy",
        confirmed_execution_status="executed_full", confirmed_price=10,
        confirmed_quantity=100, reason="分批布局", confirmed_by_user=True,
        broker_verified=False, confirmed_at=datetime(2026, 10, 1),
        trade_type=TradeType.actual, record_source="autonomous_manual",
        operation_id="buy-operation-008", operation_fingerprint="buy-fingerprint-008",
    )
    sell = ExecutionObservationLog(
        log_id="sell_008", draft_id=None, execution_card_id=None,
        signal_id=None, action_plan_id=None, capital_context_id=None,
        market_snapshot_id=None, confirmed_action="sell",
        confirmed_execution_status="executed_full", confirmed_price=11,
        confirmed_quantity=100, reason=None, confirmed_by_user=True,
        broker_verified=False, confirmed_at=datetime(2026, 10, 2),
        trade_type=TradeType.actual, record_source="autonomous_manual",
        operation_id="sell-operation-008", operation_fingerprint="sell-fingerprint-008",
    )
    review = DisciplineReviewService().create_review(
        position_id="pos_008", execution_card_id=None, signal_id=None,
        daily_signal_ids=[], buy_log=buy, sell_log=sell,
        execution_rule_status="actual_recorded",
    )
    return review, buy, sell


@pytest.mark.parametrize(
    ("response", "expected_reason"),
    [
        ({"content": []}, "response_structure_invalid"),
        ({"content": [{"type": "text", "text": "建议下次记录理由。"}], "stop_reason": "max_tokens"}, "response_truncated"),
        ({"content": [{"type": "text", "text": "建议以后补充费用字段。"}], "stop_reason": "end_turn"}, "text_rejected"),
    ],
)
def test_ai_review_diagnostics_distinguish_output_failures(response, expected_reason):
    review, buy, sell = _review_inputs()

    class Client:
        def create_message(self, **kwargs):
            return response

    text, status, diagnostic = DisciplineReviewService().generate_ai_review_with_diagnostic(
        review, buy, sell, Client(),
    )

    assert text is None
    assert status == "unavailable"
    assert diagnostic["failure_reason"] == expected_reason
    model_text = response["content"][0]["text"] if response.get("content") else ""
    if model_text:
        assert model_text not in json.dumps(diagnostic, ensure_ascii=False)


def test_ai_review_diagnostics_keep_provider_exception_metadata_without_message():
    review, buy, sell = _review_inputs()

    class Client:
        def create_message(self, **kwargs):
            error = RuntimeError("secret=do-not-retain")
            error.call_diagnostic = {
                "stage": None,
                "status": "error",
                "exception_class": "RuntimeError",
                "http_status": 503,
                "provider_code": "overloaded_error",
                "timeout": False,
            }
            raise error

    text, status, diagnostic = DisciplineReviewService().generate_ai_review_with_diagnostic(
        review, buy, sell, Client(),
    )

    assert text is None
    assert status == "unavailable"
    assert diagnostic["failure_reason"] == "provider_request_failed"
    assert diagnostic["provider_diagnostic"]["exception_class"] == "RuntimeError"
    assert diagnostic["provider_diagnostic"]["http_status"] == 503
    assert "do-not-retain" not in json.dumps(diagnostic)


class ResearchLLM:
    def __init__(
        self,
        call_diagnostic=None,
        reason="基金持仓和跟踪资料未获取，暂无法形成可靠判断。",
        verdict="research_unavailable",
        supporting_source_id="fund_daily:510880.SH:0",
        evidence_gaps=None,
    ):
        self.calls = []
        self.call_diagnostic = call_diagnostic
        self.reason = reason
        self.verdict = verdict
        self.supporting_source_id = supporting_source_id
        self.evidence_gaps = evidence_gaps or ["基金持仓与跟踪资料未获取。"]

    def get_provider_name(self):
        return "test"

    def get_model_name(self):
        return "test-model"

    def create_message(self, **kwargs):
        self.calls.append(kwargs)
        payload = {
            "demand_driver": "基金资料仍待核验",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "candidate_verdicts": {
                "510880.SH": {
                    "verdict": self.verdict,
                    "reason": self.reason,
                    "supporting_source_ids": [self.supporting_source_id],
                    "counter_evidence": [],
                    "invalidation_conditions": ["基金持仓及基准资料可核验后重新评估。"],
                    "evidence_gaps": self.evidence_gaps,
                },
            },
            "evidence_gaps": [],
        }
        response = {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "model": "test-model",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }
        if self.call_diagnostic is not None:
            return LLMCallResult(response, self.call_diagnostic)
        return response


class IdentityAndQuoteClient:
    def __init__(self):
        self.calls = []

    def query(self, api, **kwargs):
        self.calls.append((api, kwargs))
        if api == "fund_basic":
            return pd.DataFrame([{
                "ts_code": "510880.SH", "name": "上证红利ETF", "market": "E",
            }])
        if api == "fund_daily":
            return pd.DataFrame([{
                "ts_code": "510880.SH", "trade_date": "20261007", "close": 3.368,
            }])
        return pd.DataFrame()


def test_single_security_etf_research_is_transient_and_source_bound(monkeypatch):
    tushare = IdentityAndQuoteClient()
    llm = ResearchLLM()

    class Validator:
        tushare_client = tushare

    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    db = ResearchDB(db_path=":memory:")
    app = create_research_app(
        db=db, conversation_mode="real", serenity_execution_mode="two_phase",
        validator=Validator(), serenity_runner=runner, allow_test_serenity_runner=True,
    )
    client = TestClient(app)

    response = client.post("/api/research/single-security", json={"code": "510880"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["security_type"] == "fund"
    assert result["verdict"] == "等待更多证据"
    assert result["research_reference_only"] is True
    assert len(result["numeric_facts"]) <= 3
    assert result["numeric_facts"][0] == {
        "label": "最近收盘价",
        "value": 3.368,
        "unit": "元/份",
        "symbol": "510880.SH",
        "source": "Tushare-compatible",
        "endpoint": "fund_daily",
        "date": "2026-10-07",
        "retrieved_at": result["numeric_facts"][0]["retrieved_at"],
    }
    assert "公司财报不适用于基金研究。" in result["not_applicable"]
    assert not any("公司财报" in gap or "公司画像" in gap for gap in result["evidence_gaps"])
    assert len(result["narrative_sentences"]) == 4
    assert len(llm.calls) == 1
    assert llm.calls[0]["stage"] == "synthesizer"
    diagnostic = result["research_diagnostic"]
    assert diagnostic["llm_call_count"] == 1
    assert diagnostic["calls"][0]["stage"] == "synthesizer"
    assert diagnostic["calls"][0]["status"] == "success"
    assert diagnostic["calls"][0]["response_received"] is True
    assert diagnostic["calls"][0]["parse_reached"] is True
    assert diagnostic["candidate_verdict_parsed"] is True
    assert diagnostic["candidate_verdict"] == "research_unavailable"
    assert diagnostic["failure_reason"] is None
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "fund_daily:510880.SH:0" in prompt
    assert "3.368" in prompt
    assert db.list_themes() == []


def test_single_security_verified_etf_uses_bundle_and_observable_invalidation(monkeypatch):
    tushare = ETFBundleClient()
    get_etf_research_bundle = DataToolsService.get_etf_research_bundle
    fixed_now = datetime(2026, 10, 9, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    def get_bundle_at_fixed_time(service, symbol, **kwargs):
        kwargs.setdefault("now", fixed_now)
        return get_etf_research_bundle(service, symbol, **kwargs)

    monkeypatch.setattr(DataToolsService, "get_etf_research_bundle", get_bundle_at_fixed_time)
    llm = ResearchLLM(
        verdict="research_positive",
        reason="基金持仓和跟踪资料未获取，暂无法形成可靠判断。",
        evidence_gaps=[
            "跟踪指数估值分位数与PE/PB无法核验。",
            "底层指数股息收益率暂无法获取。",
        ],
    )

    class Validator:
        tushare_client = tushare

    class Monitor:
        def trade_calendar_rows_between(self, start_date, end_date):
            return tushare.calendar

    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: Monitor(),
    )
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    response = TestClient(app).post("/api/research/single-security", json={"code": "510880"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["security_type"] == "fund"
    assert result["status"] == "research_completed"
    assert result["verdict"] == "值得研究"
    assert "区间报告收盘价变化" in result["rationale"]
    assert "近期成交额" in result["rationale"]
    assert "已实施现金派息" in result["rationale"]
    assert "跟踪指数估值" in result["rationale"]
    assert "仅核验基金身份和有日期的行情" not in result["rationale"]
    assert "不构成买入或执行许可" in result["rationale"]
    assert result["research_diagnostic"]["rationale_source"] == "deterministic_etf_valuation"
    assert result["research_diagnostic"]["model_reason_filtered"] is True
    assert not any("公司财报" in gap or "公司画像" in gap for gap in result["evidence_gaps"])
    assert not any("格式不合规" in gap or "未授权数字" in gap for gap in result["evidence_gaps"])
    assert "公司财报不适用于基金研究。" in result["not_applicable"]
    assert result["etf_research"]["endpoint_statuses"]["index_dailybasic"] == "empty_no_rows"
    index_bundle_gaps = [
        gap for gap in result["etf_research"]["gaps"]
        if "指数" in gap or "index_dailybasic" in gap
    ]
    assert len(index_bundle_gaps) == 1
    assert "ETF自身现金分红收益率历史分位" in index_bundle_gaps[0]
    assert "不等同于指数估值" in index_bundle_gaps[0]
    assert "Tushare index_dailybasic 返回空结果，相关指标无法核验。" not in index_bundle_gaps
    index_response_gaps = [
        gap for gap in result["evidence_gaps"]
        if "指数" in gap or "股息收益率" in gap or "估值分位数" in gap
    ]
    assert len(index_response_gaps) == 1
    assert "ETF自身现金分红收益率历史分位" in index_response_gaps[0]
    assert result["etf_research"]["metrics"]["trailing_cash_dividend_per_share"]["value"] == pytest.approx(0.143)
    assert result["etf_research"]["metrics"]["price_coverage_1y"]["coverage_complete"] is True
    assert result["etf_research"]["metrics"]["index_valuation_coverage"]["window_start"] == "2016-10-09"
    assert any(row[0] == "etf_basic" for row in tushare.calls)
    assert sum(row[0] == "fund_daily" for row in tushare.calls) == 1
    daily_call = next(row[1] for row in tushare.calls if row[0] == "fund_daily")
    assert daily_call["start_date"] == "20161009"
    assert any(row[0] == "index_dailybasic" and row[1]["ts_code"] == "000015.SH" for row in tushare.calls)
    assert [fact["endpoint"] for fact in result["numeric_facts"][:3]] == [
        "fund_daily", "fund_daily", "fund_div",
    ]
    fact_labels = {fact["label"] for fact in result["numeric_facts"]}
    assert {"资产净值", "基金份额规模", "管理费率", "托管费率", "估值参考"}.issubset(fact_labels)
    assert next(fact for fact in result["numeric_facts"] if fact["label"] == "管理费率")["unit"] == "%/年"
    assert all(fact["window"] and fact["field"] for fact in result["numeric_facts"])
    assert result["investment_assumption"]["kind"] == "trailing_cash_dividend_baseline"
    assert result["investment_assumption"]["baseline_value"] == pytest.approx(0.143)
    assert "滚动20个SSE交易日" not in result["invalidation_condition"]
    assert "历史分位降至80%以下" in result["invalidation_condition"]
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "etf_basic:510880.SH:0" in prompt
    assert "fund_share:510880.SH:0" in prompt
    assert "index_dailybasic" in prompt
    assert str(result["numeric_facts"][1]["value"]) in prompt
    assert "中文单句" in prompt
    assert "不得含数字" in prompt


def test_single_security_etf_dividend_reason_uses_verified_payout_baseline(monkeypatch):
    tushare = ETFBundleClient()
    llm = ResearchLLM(reason="近一年实际现金分红仍需要继续跟踪。")

    class Validator:
        tushare_client = tushare

    class Monitor:
        def trade_calendar_rows_between(self, start_date, end_date):
            return tushare.calendar

    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: Monitor(),
    )
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    result = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    ).json()

    assert result["investment_assumption"]["kind"] == "trailing_cash_dividend_baseline"
    assert result["investment_assumption"]["baseline_value"] == pytest.approx(0.143)
    assert "分红" in result["investment_assumption"]["condition"]
    assert "0.143元/份" in result["investment_assumption"]["condition"]
    assert "不代表分红稳定或保证" in result["investment_assumption"]["condition"]
    assert "完整十年分位" in result["invalidation_condition"]


def test_single_security_stock_keeps_stock_identity_and_quote_path(monkeypatch):
    class StockOnlyClient:
        def __init__(self):
            self.calls = []

        def query(self, api, **kwargs):
            self.calls.append((api, kwargs))
            if api == "fund_basic":
                return pd.DataFrame()
            if api == "stock_basic":
                return pd.DataFrame([{
                    "ts_code": "600519.SH", "name": "贵州茅台", "list_status": "L",
                }])
            if api == "daily":
                return pd.DataFrame([{
                    "ts_code": "600519.SH", "trade_date": "20261007", "close": 1500.0,
                }])
            return pd.DataFrame()

    tushare = StockOnlyClient()

    class Validator:
        tushare_client = tushare

    from backend.services.friend_stock_flow import FriendStockFlowService
    from backend.services.data_tools import DataToolsService

    def stop_stock_research(*args, **kwargs):
        raise RuntimeError("synthetic stock research unavailable")

    def reject_etf_lookup(*args, **kwargs):
        raise AssertionError("ETF route used for stock")

    monkeypatch.setattr(FriendStockFlowService, "run_industry_research", stop_stock_research)
    monkeypatch.setattr(
        DataToolsService,
        "get_etf_research_bundle",
        reject_etf_lookup,
    )
    runner = SerenityAgentRunner(
        llm_client=ResearchLLM(), validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    response = TestClient(app).post(
        "/api/research/single-security", json={"code": "600519"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["symbol"] == "600519.SH"
    assert result["security_type"] == "stock"
    assert result["numeric_facts"][0]["endpoint"] == "daily"
    assert result["numeric_facts"][0]["value"] == 1500.0
    assert [call[0] for call in tushare.calls].count("daily") == 1
    assert "etf_basic" not in [call[0] for call in tushare.calls]


def test_single_security_etf_does_not_fill_missing_dividend_baseline(monkeypatch):
    class DividendMissingClient(ETFBundleClient):
        def query(self, api, **kwargs):
            if api == "fund_div":
                raise ValueError("积分不足，接口权限不满足")
            return super().query(api, **kwargs)

    tushare = DividendMissingClient()
    llm = ResearchLLM(reason="近一年现金分红是本次研究理由的一部分。")

    class Validator:
        tushare_client = tushare

    class Monitor:
        def trade_calendar_rows_between(self, start_date, end_date):
            return tushare.calendar

    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: Monitor(),
    )
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    result = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    ).json()

    assert result["investment_assumption"] is None
    assert "完整十年分位" in result["invalidation_condition"]
    assert "0.143" not in result["invalidation_condition"]
    assert any("fund_div" in gap and "权限不足" in gap for gap in result["evidence_gaps"])


def test_single_security_response_preserves_safe_timeout_attempts():
    llm = ResearchLLM(call_diagnostic={
        "provider": "cc-vibe",
        "model": "test-model",
        "stage": "synthesizer",
        "status": "success",
        "exception_class": None,
        "http_status": None,
        "provider_code": None,
        "timeout": False,
        "response_received": True,
        "attempt_count": 3,
        "retry_count": 2,
        "retry_stop_reason": None,
        "exception_chain": [],
        "response_error_text": None,
        "attempts": [
            {
                "attempt": 1, "status": "timeout", "duration_ms": 10.0,
                "http_status": None, "provider_code": None, "timeout": True,
                "response_received": False,
                "exception_chain": [{"type": "APITimeoutError", "message": "request timed out"}],
                "response_error_text": None,
            },
            {
                "attempt": 2, "status": "timeout", "duration_ms": 12.0,
                "http_status": None, "provider_code": None, "timeout": True,
                "response_received": False,
                "exception_chain": [{"type": "APITimeoutError", "message": "request timed out"}],
                "response_error_text": None,
            },
            {
                "attempt": 3, "status": "success", "duration_ms": 15.0,
                "http_status": None, "provider_code": None, "timeout": False,
                "response_received": True, "exception_chain": [],
                "response_error_text": None,
            },
        ],
        "request_headers": {"Authorization": "must-not-pass"},
    })
    tushare = IdentityAndQuoteClient()

    class Validator:
        tushare_client = tushare

    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )
    result = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    ).json()

    diagnostic = result["research_diagnostic"]["calls"][0]
    assert diagnostic["attempt_count"] == 3
    assert diagnostic["retry_count"] == 2
    assert [attempt["status"] for attempt in diagnostic["attempts"]] == [
        "timeout", "timeout", "success",
    ]
    assert "request_headers" not in json.dumps(result)


def test_single_security_failure_is_labeled_unavailable_with_safe_diagnostic():
    tushare = IdentityAndQuoteClient()

    class Validator:
        tushare_client = tushare

    class FailedLLM(ResearchLLM):
        def create_message(self, **kwargs):
            error = RuntimeError("private provider response text")
            error.call_diagnostic = {
                "stage": "synthesizer",
                "status": "error",
                "exception_class": "RuntimeError",
                "http_status": 503,
                "provider_code": "overloaded_error",
                "timeout": False,
            }
            raise error

    runner = SerenityAgentRunner(
        llm_client=FailedLLM(), validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    result = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    ).json()

    assert result["status"] == "research_unavailable"
    assert result["verdict"] == "等待更多证据"
    assert result["numeric_facts"][0]["endpoint"] == "fund_daily"
    assert result["research_diagnostic"]["llm_call_count"] == 1
    assert result["research_diagnostic"]["calls"][0]["status"] == "failure"
    assert result["research_diagnostic"]["calls"][0]["http_status"] == 503
    assert result["research_diagnostic"]["failure_reason"] == "http"
    assert "private provider response text" not in json.dumps(result)


def test_model_numeric_guard_preserves_verified_code_but_rejects_market_numbers():
    assert _safe_research_sentence("510880.SH 的基金资料仍有缺口。", "510880.SH") == "510880.SH 的基金资料仍有缺口。"
    assert _safe_research_sentence("最近收盘为 3.368 元。", "510880.SH") is None
    assert _safe_research_sentence("2026-10-07 行情仍需复核。", "510880.SH") is None
    assert _safe_research_sentence("510880元的价格需要复核。", "510880.SH") is None


def test_single_security_rejects_non_six_digit_codes_before_lookup():
    client = IdentityAndQuoteClient()

    class Validator:
        tushare_client = client

    llm = ResearchLLM()
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    responses = [
        TestClient(app).post("/api/research/single-security", json={"code": code})
        for code in ("510880.SH", "18880")
    ]

    assert all(response.status_code == 422 for response in responses)
    assert client.calls == []
    assert llm.calls == []


@pytest.mark.parametrize(
    ("code", "category", "expected_status", "expected_verdict"),
    [
        (
            "512010", "industry", "valuation_unavailable",
            "跟踪指数的估值数据未覆盖，暂不提供估值判断",
        ),
        (
            "518880", "other", "valuation_not_supported",
            "该类型暂不提供估值判断",
        ),
    ],
)
def test_unsupported_etf_valuation_templates_do_not_call_model(
    monkeypatch, code, category, expected_status, expected_verdict,
):
    canonical_symbol = f"{code}.SH"

    class IdentityClient:
        def __init__(self):
            self.calls = []

        def query(self, api, **kwargs):
            self.calls.append((api, kwargs))
            if api == "fund_basic":
                return pd.DataFrame([{
                    "ts_code": canonical_symbol,
                    "name": "测试ETF",
                    "market": "E",
                }])
            return pd.DataFrame()

    bundle = {
        "symbol": canonical_symbol,
        "is_etf": True,
        "category": category,
        "as_of": "2026-10-09",
        "retrieved_at": "2026-10-09T19:00:00+08:00",
        "metrics": {
            "latest_price": {
                "value": 5.12, "unit": "元/份", "source": "Tushare-compatible",
                "endpoint": "fund_daily", "field": "close", "as_of": "2026-10-09",
                "window": "最近报告收盘价",
            },
        },
        "sources": [],
        "gaps": [expected_verdict],
        "endpoint_statuses": {},
        "investment_assumption": None,
        "valuation_conclusion": {
            "status": "data_gap" if category == "industry" else "not_supported",
            "verdict": "research_unavailable",
            "message": expected_verdict,
            "basis": None,
            "invalidation_condition": expected_verdict,
        },
    }
    client = IdentityClient()
    llm = ResearchLLM(verdict="research_positive")

    class Validator:
        tushare_client = client

    monkeypatch.setattr(
        DataToolsService,
        "get_etf_research_bundle",
        lambda service, symbol, **kwargs: bundle,
    )
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    response = TestClient(app).post(
        "/api/research/single-security", json={"code": code},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == expected_status
    assert result["verdict"] == expected_verdict
    assert result["llm_call_count"] == 0
    assert result["research_diagnostic"]["calls"] == []
    assert result["research_diagnostic"]["failure_reason"] is None
    assert llm.calls == []
    assert result["identity_source"]["symbol"] == canonical_symbol
    assert all(fact["symbol"] == canonical_symbol for fact in result["numeric_facts"])
    assert any(fact["label"] == "最近收盘价" for fact in result["numeric_facts"])


def test_deterministic_core_verdict_overrides_model_verdict(monkeypatch):
    client = IdentityAndQuoteClient()
    llm = ResearchLLM(
        verdict="research_reject",
        reason="基金持仓和跟踪资料未获取，暂无法形成可靠判断。",
    )
    bundle = {
        "symbol": "510880.SH",
        "is_etf": True,
        "category": "dividend",
        "as_of": "2026-10-09",
        "retrieved_at": "2026-10-09T19:00:00+08:00",
        "metrics": {
            "latest_price": {
                "value": 3.431, "unit": "元/份", "source": "Tushare-compatible",
                "endpoint": "fund_daily", "field": "close", "as_of": "2026-10-09",
                "window": "最近报告收盘价",
            },
        },
        "sources": [
            {
                "source_record_id": "etf_basic:510880.SH:0",
                "endpoint": "etf_basic",
                "title": "测试ETF身份和基准",
                "as_of": "2026-10-09",
                "summary": "经核验的场内ETF身份和跟踪指数映射。",
                "gaps": [],
            },
            {
                "source_record_id": "fund_daily:510880.SH:0",
                "endpoint": "fund_daily",
                "title": "测试ETF收盘行情",
                "as_of": "2026-10-09",
                "summary": "有日期的测试收盘行情。",
                "gaps": [],
            },
        ],
        "gaps": [],
        "endpoint_statuses": {},
        "investment_assumption": None,
        "valuation_conclusion": {
            "status": "conclusive",
            "verdict": "research_positive",
            "label": "相对偏便宜",
            "basis": "own_dividend_yield",
            "message": "510880自身已派付现金分红收益率历史分位相对偏便宜；不等同于指数估值。",
            "invalidation_condition": "若同口径历史分位低于80，撤回相对偏便宜判断并重评。",
        },
    }

    class Validator:
        tushare_client = client

    monkeypatch.setattr(
        DataToolsService,
        "get_etf_research_bundle",
        lambda service, symbol, **kwargs: bundle,
    )
    runner = SerenityAgentRunner(
        llm_client=llm, validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    response = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verdict"] == "值得研究"
    assert result["invalidation_condition"] == bundle["valuation_conclusion"]["invalidation_condition"]
    assert result["research_diagnostic"]["deterministic_basis"] == "own_dividend_yield"
    assert result["research_diagnostic"]["candidate_verdict"] == "research_reject", result["research_diagnostic"]
    assert len(llm.calls) == 1


class ETFBundleClient:
    def __init__(self):
        self.calls = []
        daily_dates = pd.bdate_range(start="2016-10-10", end="2026-10-08")
        self.daily = []
        for index, day in enumerate(daily_dates):
            trade_date = day.strftime("%Y%m%d")
            close = 100.0 if index == 0 or trade_date == "20251008" else 90.0 if index == 2 else 110.0
            self.daily.append({
                "ts_code": "510880.SH",
                "trade_date": trade_date,
                "close": close,
                "high": 115.0 if index == 0 or trade_date == "20251008" else close + 2.0,
                "vol": 100.0,
                "amount": float(index + 1),
            })
        self.daily.extend([
            {"ts_code": "510880.SH", "trade_date": "20261009", "close": 999.0, "high": 999.0, "vol": 100.0, "amount": 999.0},
            {"ts_code": "510300.SH", "trade_date": "20261008", "close": 888.0, "high": 888.0, "vol": 100.0, "amount": 888.0},
        ])
        self.calendar = []
        calendar_day = date(2016, 10, 8)
        calendar_end = date(2026, 10, 9)
        while calendar_day <= calendar_end:
            self.calendar.append({
                "exchange": "SSE",
                "cal_date": calendar_day.strftime("%Y%m%d"),
                "is_open": int(calendar_day.weekday() < 5),
                "pretrade_date": None,
            })
            calendar_day += pd.Timedelta(days=1).to_pytimedelta()

    def query(self, api, **kwargs):
        self.calls.append((api, kwargs))
        records = {
            "etf_basic": [{
                "ts_code": "510880.SH", "csname": "上证红利ETF",
                "index_code": "000015.SH", "index_name": "上证红利",
                "setup_date": "20061117", "list_date": "20070118", "mgt_fee": 0.5,
                "custod_name": "招商银行", "list_status": "L",
            }],
            "fund_basic": [{
                "ts_code": "510880.SH", "name": "上证红利ETF",
                "found_date": "20061117", "m_fee": 0.5,
                "c_fee": 0.1, "fund_type": "股票型", "benchmark": "上证红利指数",
            }],
            "fund_nav": [
                {
                    "ts_code": "510880.SH", "nav_date": "20260813",
                    "net_asset": 25054247796.02, "total_netasset": 25177624140.25,
                },
                {
                    "ts_code": "510880.SH", "nav_date": "20250630",
                    "net_asset": 19086808965.54, "total_netasset": 19086808965.54,
                },
            ],
            "fund_share": [
                {"ts_code": "510880.SH", "trade_date": "20260930", "fd_share": 123.45},
                {"ts_code": "510880.SH", "trade_date": "20261009", "fd_share": 999.0},
            ],
            "fund_daily": self.daily,
            "fund_div": [
                {
                    "ts_code": "510880.SH", "div_proc": "实施",
                    "ann_date": "20100108", "imp_anndate": "20100108",
                    "ex_date": "20100120", "pay_date": "20100125",
                    "div_cash": 0.1, "base_date": "20091231",
                },
                {
                    "ts_code": "510880.SH", "div_proc": "实施",
                    "ann_date": "20260116", "imp_anndate": "20260116",
                    "ex_date": "20260121", "pay_date": "20260126",
                    "div_cash": 0.143, "base_date": "20251231",
                    "base_unit": None, "net_ex_date": None,
                },
                {
                    "ts_code": "510880.SH", "div_proc": "实施",
                    "ann_date": "20260116", "imp_anndate": "20260116",
                    "ex_date": "20260121", "pay_date": "20260126",
                    "div_cash": 0.143, "base_date": "20251231",
                    "base_unit": 618.0, "net_ex_date": "20260121",
                },
                {
                    "ts_code": "510880.SH", "div_proc": "预案",
                    "ann_date": "20260320", "imp_anndate": None,
                    "ex_date": "20260401", "pay_date": "20260410",
                    "div_cash": 0.9, "base_date": "20260301",
                },
                {
                    "ts_code": "510880.SH", "div_proc": "实施",
                    "ann_date": "20250920", "imp_anndate": "20250929",
                    "ex_date": "20251001", "pay_date": "20251005",
                    "div_cash": 0.2, "base_date": "20250901",
                },
            ],
            "index_dailybasic": [],
        }
        return pd.DataFrame(records.get(api, []))


def test_etf_bundle_uses_exact_mapping_and_deterministic_asof_metrics():
    client = ETFBundleClient()

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["is_etf"] is True
    assert bundle["metrics"]["underlying_index"]["value"] == "000015.SH"
    assert bundle["metrics"]["latest_price"]["value"] == 110.0
    assert bundle["metrics"]["latest_price"]["as_of"] == "2026-10-08"
    assert bundle["metrics"]["price_change_1y"]["value"] == pytest.approx(10.0)
    assert bundle["metrics"]["price_change_1y"]["window"].startswith("报告收盘价")
    assert bundle["metrics"]["distance_from_1y_high_pct"]["value"] == pytest.approx(-4.34782609)
    assert bundle["metrics"]["distance_from_1y_high_pct"]["field"] == "high"
    assert bundle["metrics"]["distance_from_1y_high_pct"]["label"] == "距近一年已观察到的最高价"
    latest_amount_rows = sorted(
        (row for row in client.daily if row["ts_code"] == "510880.SH" and row["trade_date"] <= "20261008"),
        key=lambda row: row["trade_date"],
    )[-20:]
    expected_avg = sum(row["amount"] for row in latest_amount_rows) / 20 * 1000
    assert bundle["metrics"]["average_amount_20d"]["value"] == pytest.approx(expected_avg)
    assert bundle["metrics"]["fund_size_shares"]["value"] == 123.45
    assert bundle["metrics"]["fund_size_shares"]["as_of"] == "2026-09-30"
    assert bundle["metrics"]["asset_scale"]["value"] == pytest.approx(25177624140.25)
    assert bundle["metrics"]["asset_scale"]["unit"] == "元"
    assert bundle["metrics"]["asset_scale"]["as_of"] == "2026-08-13"
    assert bundle["metrics"]["management_fee"]["value"] == pytest.approx(0.5)
    assert bundle["metrics"]["management_fee"]["unit"] == "%/年"
    assert bundle["metrics"]["custody_fee"]["value"] == pytest.approx(0.1)
    assert bundle["metrics"]["custody_fee"]["unit"] == "%/年"
    assert bundle["metrics"]["trailing_cash_dividend_per_share"]["value"] == pytest.approx(0.143)
    assert bundle["metrics"]["trailing_dividend_yield"]["value"] == pytest.approx(0.13)
    assert bundle["metrics"]["trailing_dividend_yield_percentile_10y"]["value"] >= 80
    assert bundle["metrics"]["trailing_dividend_yield_valuation"]["value"] == "相对历史偏便宜"
    assert bundle["metrics"]["trailing_dividend_yield"]["as_of"] == bundle["metrics"]["latest_price"]["as_of"]
    assert bundle["metrics"]["trailing_dividend_yield_coverage_10y"]["window_end"] == bundle["metrics"]["latest_price"]["as_of"]
    assert bundle["metrics"]["trailing_dividend_yield_coverage_10y"]["sample_points"] > 2000
    assert bundle["metrics"]["trailing_dividend_yield_coverage_10y"]["coverage_complete"] is True
    assert bundle["investment_assumption"]["baseline_value"] == pytest.approx(0.143)
    assert bundle["investment_assumption"]["endpoint"] == "fund_div"
    assert "低于本次核验的0.143元/份" in bundle["investment_assumption"]["condition"]
    assert "不代表分红稳定或保证" in bundle["investment_assumption"]["condition"]
    assert bundle["endpoint_statuses"]["index_dailybasic"] == "empty_no_rows"
    assert bundle["endpoint_statuses"]["trade_cal"] == "allowed_with_data"
    assert bundle["metrics"]["price_coverage_1y"]["coverage_complete"] is True
    assert bundle["metrics"]["index_valuation_coverage"]["expected_open_days"] > 2000
    assert bundle["metrics"]["index_valuation_coverage"]["pe_sample_points"] == 0
    assert bundle["metrics"]["index_valuation_coverage"]["pe_sample_start"] is None
    assert bundle["endpoint_statuses"]["fund_div"] == "allowed_with_data"
    assert not any("单位" in gap and "费" in gap for gap in bundle["gaps"])
    index_gaps = [gap for gap in bundle["gaps"] if "指数" in gap or "index_dailybasic" in gap]
    assert len(index_gaps) == 1
    assert "ETF自身现金分红收益率历史分位" in index_gaps[0]
    assert "不等同于指数估值" in index_gaps[0]
    assert "Tushare index_dailybasic 返回空结果，相关指标无法核验。" not in index_gaps
    assert any(call[0] == "index_dailybasic" and call[1]["ts_code"] == "000015.SH" for call in client.calls)
    assert bundle["category"] == "dividend"
    assert bundle["valuation_conclusion"]["status"] == "conclusive"
    assert bundle["valuation_conclusion"]["basis"] == "own_dividend_yield"


@pytest.mark.parametrize(
    ("code", "index_code", "fund_type", "benchmark", "category", "valuation_status"),
    [
        (
            "512010.SH", "000913.SH", "股票型", "沪深300医药卫生指数×100%",
            "industry", "data_gap",
        ),
        (
            "518880.SH", "Au99.99.SGE", "其他", "国内黄金现货价格收益率(Au99.99合约)×100%",
            "other", "not_supported",
        ),
    ],
)
def test_etf_bundle_uses_exact_template_and_never_borrows_unsupported_index_data(
    code, index_code, fund_type, benchmark, category, valuation_status,
):
    class ExactETFClient(ETFBundleClient):
        def query(self, api, **kwargs):
            frame = super().query(api, **kwargs)
            if api == "etf_basic":
                frame = pd.DataFrame([{
                    "ts_code": code, "index_code": index_code, "index_name": "测试指数",
                    "setup_date": "20190101", "list_date": "20190101", "list_status": "L",
                }])
            elif api == "fund_basic":
                frame = pd.DataFrame([{
                    "ts_code": code, "name": "测试ETF", "fund_type": fund_type,
                    "benchmark": benchmark, "found_date": "20190101", "m_fee": 0.5,
                    "c_fee": 0.1,
                }])
            elif not frame.empty and "ts_code" in frame:
                frame["ts_code"] = code
            return frame

    client = ExactETFClient()
    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        code, as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["is_etf"] is True
    assert bundle["category"] == category
    assert bundle["valuation_conclusion"]["status"] == valuation_status
    assert bundle["valuation_conclusion"]["verdict"] == "research_unavailable"
    index_calls = [call for call in client.calls if call[0] == "index_dailybasic"]
    if category == "other":
        assert index_calls == []
        assert bundle["endpoint_statuses"]["index_dailybasic"] == "not_applicable"
        assert bundle["valuation_conclusion"]["message"] == "该类型暂不提供估值判断"
    else:
        assert len(index_calls) == 1
        assert index_calls[0][1]["ts_code"] == "000913.SH"
        assert bundle["endpoint_statuses"]["index_dailybasic"] == "empty_no_rows"
        assert bundle["valuation_conclusion"]["message"] == (
            "跟踪指数的估值数据未覆盖，暂不提供估值判断"
        )


def test_etf_bundle_calculates_observed_high_when_an_open_day_is_missing():
    client = ETFBundleClient()
    client.daily = [
        row for row in client.daily
        if row.get("trade_date") != "20260601"
    ]

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["metrics"]["price_change_1y"]["value"] == pytest.approx(10.0)
    assert bundle["metrics"]["price_change_1y"]["baseline_date"] == "2025-10-08"
    assert bundle["metrics"]["distance_from_1y_high_pct"]["value"] == pytest.approx(-4.34782609)
    assert bundle["metrics"]["distance_from_1y_high_pct"]["field"] == "high"
    assert "观察到" in bundle["metrics"]["distance_from_1y_high_pct"]["label"]
    assert bundle["metrics"]["price_coverage_1y"]["coverage_complete"] is False
    assert bundle["metrics"]["price_coverage_1y"]["missing_dates"] == ["2026-06-01"]
    assert bundle["metrics"]["price_coverage_1y"]["missing_session_details"][0]["date"] == "2026-06-01"


def test_etf_bundle_uses_close_label_when_high_coverage_is_incomplete():
    client = ETFBundleClient()
    for row in client.daily:
        if row.get("trade_date") == "20260601":
            row["high"] = None

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    distance = bundle["metrics"]["distance_from_1y_high_pct"]
    assert distance["field"] == "high"
    assert distance["value"] == pytest.approx(-4.34782609)
    assert bundle["metrics"]["price_coverage_1y"]["missing_high_dates"] == ["2026-06-01"]


def test_etf_bundle_uses_expected_published_close_by_shanghai_time():
    client = ETFBundleClient()
    daytime = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH",
        now=datetime(2026, 10, 9, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        calendar_rows=client.calendar,
    )
    after_close = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH",
        now=datetime(2026, 10, 9, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        calendar_rows=client.calendar,
    )

    assert daytime["metrics"]["price_coverage_1y"]["expected_publish_date"] == "2026-10-08"
    assert daytime["metrics"]["latest_price"]["as_of"] == "2026-10-08"
    assert daytime["metrics"]["latest_price"]["stale"] is False
    assert after_close["metrics"]["price_coverage_1y"]["expected_publish_date"] == "2026-10-09"
    assert after_close["metrics"]["latest_price"]["as_of"] == "2026-10-09"
    assert after_close["metrics"]["latest_price"]["stale"] is False


def test_etf_bundle_uses_exchange_calendar_for_holiday_cutoff():
    client = ETFBundleClient()
    for row in client.calendar:
        if "20261001" <= row["cal_date"] <= "20261007":
            row["is_open"] = 0

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH",
        now=datetime(2026, 10, 8, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        calendar_rows=client.calendar,
    )

    assert bundle["metrics"]["price_coverage_1y"]["expected_publish_date"] == "2026-09-30"
    assert bundle["metrics"]["latest_price"]["as_of"] == "2026-09-30"


def test_etf_bundle_lists_zero_volume_session_and_does_not_call_it_a_close():
    client = ETFBundleClient()
    row = next(item for item in client.daily if item["trade_date"] == "20260601")
    row.update(close=None, high=None, vol=0.0)

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )
    coverage = bundle["metrics"]["price_coverage_1y"]

    assert coverage["missing_dates"] == ["2026-06-01"]
    assert coverage["missing_session_details"] == [{
        "date": "2026-06-01", "category": "zero_volume_no_trade_or_suspension",
    }]
    assert bundle["metrics"]["distance_from_1y_high_pct"] is not None


def test_etf_bundle_marks_leading_history_truncation_without_calling_it_a_year():
    client = ETFBundleClient()
    client.daily = [row for row in client.daily if row["trade_date"] >= "20260601"]

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )
    coverage = bundle["metrics"]["price_coverage_1y"]
    distance = bundle["metrics"]["distance_from_1y_high_pct"]

    assert coverage["coverage_complete"] is False
    assert coverage["leading_missing_dates"]
    assert distance is not None
    assert "完整SSE交易日" not in distance["window"]
    assert distance["sample_sessions"] < coverage["expected_sessions"]


def test_etf_bundle_marks_price_stale_only_when_older_than_expected_publish_date():
    client = ETFBundleClient()
    client.daily = [row for row in client.daily if row["trade_date"] != "20261008"]

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["metrics"]["latest_price"]["as_of"] == "2026-10-07"
    assert bundle["metrics"]["latest_price"]["expected_as_of"] == "2026-10-08"
    assert bundle["metrics"]["latest_price"]["stale"] is True
    assert any("早于预期公布日" in gap for gap in bundle["gaps"])


def test_etf_dividend_yield_is_point_in_time_and_not_applied_to_other_etfs():
    client = ETFBundleClient()

    class FutureDividendClient(ETFBundleClient):
        def query(self, api, **kwargs):
            if api != "fund_div":
                return super().query(api, **kwargs)
            rows = super().query(api, **kwargs).to_dict("records")
            rows.append({
                "ts_code": "510880.SH", "div_proc": "实施",
                "ann_date": "20261009", "imp_anndate": "20261009",
                "ex_date": "20261012", "pay_date": "20261016", "div_cash": 1.0,
                "base_date": "20260930",
            })
            return pd.DataFrame(rows)

    future_client = FutureDividendClient()
    bundle = DataToolsService(tushare_client=future_client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=future_client.calendar,
    )

    assert bundle["metrics"]["trailing_cash_dividend_per_share"]["value"] == pytest.approx(0.143)
    assert all(event["cash_per_share"] < 1.0 for event in bundle["metrics"]["trailing_cash_dividend_per_share"]["events"])
    assert bundle["metrics"]["trailing_dividend_yield_valuation"]["value"] == "相对历史偏便宜"


def test_510880_dividend_yield_valuation_is_not_applied_to_arbitrary_etfs():
    assert _is_510880_dividend_valuation("510880.SH", "000015.SH") is True
    assert _is_510880_dividend_valuation("510300.SH", "000300.SH") is False
    assert _is_510880_dividend_valuation("510880.SH", "000300.SH") is False


def test_510880_yield_percentile_rule_has_frozen_boundaries():
    assert _trailing_yield_valuation_label(80.0) == "相对历史偏便宜"
    assert _trailing_yield_valuation_label(20.0) == "相对历史偏贵"
    assert _trailing_yield_valuation_label(50.0) == "中性"


def test_etf_bundle_withholds_twenty_day_amount_when_calendar_session_is_missing():
    client = ETFBundleClient()
    latest_twenty = sorted({
        row["trade_date"] for row in client.daily
        if row["trade_date"] <= "20261008"
    })[-20:]
    missing_day = latest_twenty[-2]
    for row in client.daily:
        if row.get("trade_date") == missing_day:
            row["amount"] = None

    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["metrics"]["average_amount_20d"] is None
    assert bundle["metrics"]["latest_price"] is not None
    assert bundle["metrics"]["price_change_1y"] is not None
    assert any(missing_day[0:4] in gap and "成交额" in gap for gap in bundle["gaps"])


def test_etf_bundle_requires_complete_ten_year_index_series_for_percentiles():
    class IndexSeriesClient(ETFBundleClient):
        def query(self, api, **kwargs):
            if api != "index_dailybasic":
                return super().query(api, **kwargs)
            rows = [
                {
                    "ts_code": "000015.SH",
                    "trade_date": row["cal_date"],
                    "pe": float(index + 1),
                    "pb": float(index + 2),
                }
                for index, row in enumerate(self.calendar)
                if row["is_open"] == 1
            ]
            if getattr(self, "missing_index_day", None):
                rows = [row for row in rows if row["trade_date"] != self.missing_index_day]
            self.calls.append((api, kwargs))
            return pd.DataFrame(rows)

    client = IndexSeriesClient()
    full = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert full["metrics"]["index_valuation_coverage"]["pe_coverage_complete"] is True
    assert full["metrics"]["index_valuation_coverage"]["pe_sample_points"] == full["metrics"]["index_valuation_coverage"]["expected_open_days"]
    assert full["metrics"]["index_valuation_coverage"]["pe_sample_start"] == "2016-10-10"
    assert full["metrics"]["index_valuation_coverage"]["pe_sample_end"] == "2026-10-08"
    assert full["metrics"]["underlying_pe_percentile_10y"]["value"] == pytest.approx(100.0)

    client.missing_index_day = "20200601"
    incomplete = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert incomplete["metrics"]["index_valuation_coverage"]["pe_coverage_complete"] is False
    assert incomplete["metrics"]["underlying_pe_percentile_10y"] is None


def test_etf_bundle_keeps_no_data_permission_unsupported_timeout_and_provider_error_distinct():
    class CategorizedClient(ETFBundleClient):
        def query(self, api, **kwargs):
            self.calls.append((api, kwargs))
            if api == "etf_basic":
                return pd.DataFrame([{
                    "ts_code": "510880.SH", "index_code": "000015.SH",
                    "index_name": "上证红利", "setup_date": "20061117",
                }])
            if api == "fund_basic":
                return pd.DataFrame([{
                    "ts_code": "510880.SH", "name": "上证红利ETF", "fund_type": "股票型",
                    "benchmark": "上证红利指数", "market": "E",
                }])
            if api == "fund_nav":
                raise ValueError("积分不足，接口权限不满足")
            if api == "fund_share":
                return pd.DataFrame()
            if api == "fund_daily":
                raise ValueError("unknown api: fund_daily")
            if api == "fund_div":
                raise TimeoutError("upstream timed out")
            if api == "index_dailybasic":
                raise ValueError("temporary connection reset")
            return pd.DataFrame()

    client = CategorizedClient()
    bundle = DataToolsService(tushare_client=client).get_etf_research_bundle(
        "510880.SH", as_of=date(2026, 10, 8), calendar_rows=client.calendar,
    )

    assert bundle["endpoint_statuses"]["fund_basic"] == "allowed_with_data"
    assert bundle["endpoint_statuses"]["fund_nav"] == "permission_denied"
    assert bundle["endpoint_statuses"]["fund_share"] == "empty_no_rows"
    assert bundle["endpoint_statuses"]["fund_daily"] == "unsupported_endpoint"
    assert bundle["endpoint_statuses"]["fund_div"] == "timeout"
    assert bundle["endpoint_statuses"]["index_dailybasic"] == "provider_error"
    assert "积分不足" not in json.dumps(bundle, ensure_ascii=False)
    assert "temporary connection reset" not in json.dumps(bundle, ensure_ascii=False)


def test_single_security_ai_failure_keeps_deterministic_etf_facts_and_call_id(monkeypatch):
    tushare = ETFBundleClient()
    fixed_now = datetime(2026, 10, 9, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    get_bundle = DataToolsService.get_etf_research_bundle

    def get_bundle_at_fixed_time(service, symbol, **kwargs):
        kwargs.setdefault("now", fixed_now)
        return get_bundle(service, symbol, **kwargs)

    monkeypatch.setattr(DataToolsService, "get_etf_research_bundle", get_bundle_at_fixed_time)

    class Validator:
        tushare_client = tushare

    class Monitor:
        def trade_calendar_rows_between(self, start_date, end_date):
            return tushare.calendar

    monkeypatch.setattr("backend.api.observations.get_position_market_monitor", lambda: Monitor())

    class FailedLLM(ResearchLLM):
        def create_message(self, **kwargs):
            self.calls.append(kwargs)
            error = RuntimeError("provider request failed")
            error.call_diagnostic = {
                "call_id": "0123456789abcdef0123456789abcdef",
                "stage": "synthesizer",
                "provider": "cc-vibe",
                "model": "test-model",
                "status": "failure",
                "exception_class": "APIConnectionError",
                "http_status": None,
                "provider_code": None,
                "timeout": False,
                "response_received": False,
                "attempt_count": 1,
                "retry_count": 0,
                "retry_stop_reason": "not_timeout",
                "exception_chain": [{"type": "APIConnectionError", "message": "Connection error."}],
                "response_error_text": None,
                "attempts": [{
                    "attempt": 1,
                    "status": "error",
                    "duration_ms": 1.0,
                    "http_status": None,
                    "provider_code": None,
                    "timeout": False,
                    "response_received": False,
                    "exception_chain": [{"type": "APIConnectionError", "message": "Connection error."}],
                    "response_error_text": None,
                }],
            }
            raise error

    runner = SerenityAgentRunner(
        llm_client=FailedLLM(), validator=Validator(), mode="real", execution_mode="two_phase",
    )
    app = create_research_app(
        db=ResearchDB(db_path=":memory:"), conversation_mode="real",
        serenity_execution_mode="two_phase", validator=Validator(),
        serenity_runner=runner, allow_test_serenity_runner=True,
    )

    result = TestClient(app).post(
        "/api/research/single-security", json={"code": "510880"},
    ).json()

    assert result["status"] == "research_unavailable"
    assert result["verdict"] == "值得研究"
    assert result["research_diagnostic"]["rationale_source"] == "deterministic_etf_valuation"
    assert result["research_diagnostic"]["calls"][0]["call_id"] == "0123456789abcdef0123456789abcdef"
    facts = {fact["label"]: fact for fact in result["numeric_facts"]}
    assert {
        "最近收盘价",
        "近一年报告收盘价变化",
        "距近一年已观察最高价回撤",
        "近20个SSE交易日平均成交额",
        "近12个月已实施现金分红",
        "近12个月现金分红收益率",
        "ETF自身现金分红收益率历史分位",
        "资产净值",
        "基金份额规模",
        "管理费率",
        "托管费率",
    }.issubset(facts)
    assert facts["距近一年已观察最高价回撤"]["value"] == pytest.approx(-4.34782609)
    assert facts["资产净值"]["value"] == 25177624140.25
    assert facts["基金份额规模"]["value"] == 123.45
    assert all(fact["date"] and fact["source"] and fact["field"] for fact in facts.values())
    assert any("基金当前成分明细与行业权重未获取" in gap for gap in result["evidence_gaps"])
