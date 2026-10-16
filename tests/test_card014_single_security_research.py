import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.api.research import SingleSecurityResearchRequest, create_research_app
from backend.db.research import ResearchDB
from backend.services.serenity_agent import SerenityAgentAudit
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.serenity_synthesizer import ResearchSynthesizer
from backend.services.data_tools import DataToolsService


SNAPSHOT_SHA256 = "a" * 64


def make_snapshot():
    sources = [
        {
            "id": "snapshot:510880.SH:q1-2026",
            "entity": "510880.SH",
            "kind": "fund_report",
            "published_at": "2026-04-22",
            "as_of": "2026-03-31",
            "title": "上交所 510880 2026 年第一季度报告",
            "url": "https://www.sse.com.cn/fund-q1.pdf",
            "sha256": "1" * 64,
        },
        {
            "id": "snapshot:000015.SH:factsheet-20260930",
            "entity": "000015.SH",
            "kind": "index_factsheet",
            "published_at": "2026-09-30",
            "as_of": "2026-09-30",
            "title": "中证指数 上证红利指数事实表",
            "url": "https://oss-ch.csindex.com.cn/factsheet.pdf",
            "sha256": "2" * 64,
        },
        {
            "id": "snapshot:601919.SH:financials-2026H1",
            "entity": "601919.SH",
            "kind": "issuer_financial_report",
            "published_at": "2026-08-29",
            "as_of": "2026-06-30",
            "title": "中远海控 2026 年半年度报告",
            "url": "https://static.cninfo.com.cn/company-h1.pdf",
            "sha256": "3" * 64,
        },
    ]
    facts = [
        {
            "id": "index.pe",
            "value": 8.9,
            "unit": "倍",
            "as_of": "2026-09-30",
            "subject": "000015.SH",
            "scope": "index_metric",
            "source_id": sources[1]["id"],
        },
        {
            "id": "index.pb",
            "value": 0.76,
            "unit": "倍",
            "as_of": "2026-09-30",
            "subject": "000015.SH",
            "scope": "index_metric",
            "source_id": sources[1]["id"],
        },
        {
            "id": "index.dividend_yield",
            "value": 4.0,
            "unit": "%",
            "as_of": "2026-09-30",
            "subject": "000015.SH",
            "scope": "index_metric",
            "source_id": sources[1]["id"],
        },
        {
            "id": "index.sector_energy",
            "value": 33.7,
            "unit": "%指数权重",
            "as_of": "2026-09-30",
            "subject": "000015.SH",
            "scope": "index_sector_weight",
            "source_id": sources[1]["id"],
        },
        {
            "id": "index.cosco_weight",
            "value": 5.23,
            "unit": "%指数权重",
            "as_of": "2026-09-30",
            "subject": "601919.SH",
            "scope": "index_constituent_weight",
            "source_id": sources[1]["id"],
        },
        {
            "id": "issuer.601919.net_profit_yoy",
            "value": -23.48,
            "unit": "%",
            "as_of": "2026-06-30",
            "subject": "601919.SH",
            "scope": "issuer_financial",
            "source_id": sources[2]["id"],
        },
        {
            "id": "fund.q1.return_spread",
            "value": 0.12,
            "unit": "百分点",
            "as_of": "2026-03-31",
            "subject": "510880.SH",
            "scope": "fund_product",
            "source_id": sources[0]["id"],
        },
        {
            "id": "fund.q1.cosco_holding",
            "value": 4.86,
            "unit": "%基金净资产",
            "as_of": "2026-03-31",
            "subject": "601919.SH",
            "scope": "fund_holding",
            "source_id": sources[0]["id"],
        },
        {
            "id": "issuer.601919.operating_cash_flow_yoy",
            "value": -9.49,
            "unit": "%",
            "as_of": "2026-06-30",
            "subject": "601919.SH",
            "scope": "issuer_financial",
            "source_id": sources[2]["id"],
        },
        {
            "id": "issuer.601919.interim_dividend_plan",
            "value": 0.43,
            "unit": "元/股，董事会审议方案",
            "as_of": "2026-06-30",
            "subject": "601919.SH",
            "scope": "issuer_financial",
            "source_id": sources[2]["id"],
        },
    ]
    for fact in facts:
        fact["source_pages"] = ["p.1"]
    return {
        "version": "510880-v21-2026-10-14-test1",
        "created_at": "2026-10-14",
        "target_symbol": "510880.SH",
        "target_name": "华泰柏瑞上证红利ETF",
        "benchmark_symbol": "000015.SH",
        "sources": sources,
        "facts": facts,
        "relationships": [
            {
                "kind": "tracks_index",
                "from": "510880.SH",
                "to": "000015.SH",
                "source_id": sources[0]["id"],
            },
            {
                "kind": "index_constituent",
                "from": "000015.SH",
                "to": "601919.SH",
                "as_of": "2026-09-30",
                "weight_fact_id": "index.cosco_weight",
            },
            {
                "kind": "issuer_report",
                "from": "601919.SH",
                "to": "financial_report:2026H1",
                "as_of": "2026-06-30",
                "source_id": sources[2]["id"],
            },
        ],
        "limitations": [
            "指数权重不是 ETF 实际持仓比例。",
            "当前行情未由固定历史快照提供。",
        ],
    }


def valid_v21_response():
    return {
        "layers": [
            {
                "layer_id": "underlying_assets",
                "adequacy": "limited",
                "judgment": "红利筛选带来现金收益暴露，但长期结果仍取决于成分企业盈利与现金流能否持续。",
                "evidence_level": "medium",
                "supporting_evidence": [{
                    "text": "指数事实表披露了成分股现金收益率及行业构成。",
                    "fact_ids": ["index.dividend_yield"],
                    "evidence_level": "high",
                    "claim_kind": "observation",
                }],
                "counter_evidence": [{
                    "text": "最大样本公司报告期净利润明显下降，削弱了派息持续性的把握。",
                    "fact_ids": ["issuer.601919.net_profit_yoy"],
                    "evidence_level": "medium",
                    "claim_kind": "economic_inference",
                }],
                "risks": [{
                    "text": "行业权重偏向能源，组合表现可能受行业盈利变化影响。",
                    "fact_ids": ["index.sector_energy"],
                    "evidence_level": "medium",
                    "claim_kind": "economic_inference",
                }],
                "thesis_changers": [{
                    "text": "若主要成分企业盈利与现金流继续转弱，应重新评估派息来源的可持续性。",
                    "fact_ids": ["issuer.601919.net_profit_yoy"],
                    "evidence_level": "medium",
                    "claim_kind": "conditional_inference",
                }],
                "missing_evidence": ["其余成分的同期财务与完整派息持续性尚未核实。"],
            },
            {
                "layer_id": "etf_product",
                "adequacy": "limited",
                "judgment": "基金以跟踪上证红利指数为目标，已披露的季度跟踪结果只能说明该历史区间。",
                "evidence_level": "medium",
                "supporting_evidence": [{
                    "text": "季度报告披露基金与基准的同区间表现。",
                    "fact_ids": ["fund.q1.return_spread"],
                    "evidence_level": "high",
                    "claim_kind": "observation",
                }],
                "counter_evidence": [],
                "risks": [],
                "thesis_changers": [{
                    "text": "后续同口径基金与基准表现若持续偏离，需要重新评估产品跟踪质量。",
                    "fact_ids": ["fund.q1.return_spread"],
                    "evidence_level": "low",
                    "claim_kind": "conditional_inference",
                }],
                "missing_evidence": [
                    "较新的基金持仓和跟踪结果尚未核实。",
                    "报告时点较当前滞后，不能证明目前的跟踪状态。",
                ],
            },
            {
                "layer_id": "current_timing",
                "adequacy": "insufficient",
                "judgment": "固定快照不含当前成交价格和溢价折价，暂时无法判断此时的介入吸引力。",
                "evidence_level": "data_insufficient",
                "supporting_evidence": [],
                "counter_evidence": [],
                "risks": [],
                "thesis_changers": [],
                "missing_evidence": ["需要可核验的当前行情和溢价折价资料。"],
            },
        ],
        "core_reason": "底层有可核验的红利暴露，但成分盈利变化和当前时点资料限制了判断强度。",
        "summary_fact_ids": ["index.pe", "index.pb", "index.cosco_weight"],
        "next_step": "等待具体条件",
        "next_step_reason": "补齐当前行情并观察主要成分盈利变化后再评估。",
    }


class FakeV21LLM:
    api_key = "fake-test-key"
    base_url = "https://llm.invalid/v1"
    model = "fake-card014"

    def __init__(self, response=None, error=None):
        self.response = response or valid_v21_response()
        self.error = error
        self.calls = []

    def create_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {
            "model": self.model,
            "usage": {"input_tokens": 100, "output_tokens": 400},
            "content": [{
                "type": "text",
                "text": json.dumps(self.response, ensure_ascii=False),
            }],
        }


# Regression wording and fact IDs below are transcribed from preserved model outputs.
# claim_kind is an explicit human test annotation; no prose classifier is implied.
def claim_aware_v21_response():
    """Annotate evidence items with narrow claim classes for boundary tests."""
    response = valid_v21_response()
    for layer in response["layers"]:
        for item in layer["supporting_evidence"]:
            item["claim_kind"] = "observation"
        for item in layer["counter_evidence"]:
            item["claim_kind"] = "economic_inference"
        for item in layer["risks"]:
            item["claim_kind"] = "economic_inference"
        for item in layer["thesis_changers"]:
            item["claim_kind"] = "conditional_inference"
    return response


def test_single_security_request_accepts_target_exchange_suffix_only():
    assert SingleSecurityResearchRequest(code="510880").code == "510880"
    assert SingleSecurityResearchRequest(code="510880.SH", research_version="v2.1").code == "510880.SH"
    assert SingleSecurityResearchRequest(code="510880.SH", research_version="v2.1").research_version == "v2.1"
    with pytest.raises(ValidationError):
        SingleSecurityResearchRequest(code="510880.SZ")


def test_packaged_card014_snapshot_passes_exact_identity_chain_and_contains_official_source_metadata():
    snapshot_path = Path(__file__).resolve().parents[1] / "backend" / "research_snapshots" / "510880_v21_20261014.json"
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    client = FakeV21LLM()

    result = ResearchSynthesizer(client).synthesize_single_security_v21(
        target_symbol="510880.SH",
        snapshot=snapshot,
        snapshot_sha256=__import__("hashlib").sha256(snapshot_bytes).hexdigest(),
        runtime_facts=[],
        audit=SerenityAgentAudit(),
    )

    assert result["snapshot"]["version"] == "510880-v21-2026-10-14.1"
    assert result["snapshot"]["source_count"] == 3
    assert result["layers"][0]["counter_evidence"][0]["fact_refs"][0]["scope"] == "issuer_financial"
    assert result["summary_facts"][0]["label"]
    assert all(source["sha256"] and source["url"].startswith("https://") for source in snapshot["sources"])


@pytest.mark.parametrize(
    ("model_error", "expected_status"),
    [(None, "success"), (RuntimeError("api key=do-not-return"), "unavailable")],
)
def test_v21_api_runs_research_when_deterministic_valuation_has_a_data_gap(monkeypatch, model_error, expected_status):
    llm = FakeV21LLM(error=model_error)

    class IdentityClient:
        def query(self, api, **kwargs):
            if api == "fund_basic":
                return pd.DataFrame([{
                    "ts_code": "510880.SH", "name": "华泰柏瑞上证红利ETF", "market": "E",
                }])
            return pd.DataFrame()

    class Validator:
        tushare_client = IdentityClient()

    bundle = {
        "symbol": "510880.SH",
        "is_etf": True,
        "as_of": "2026-10-14",
        "retrieved_at": datetime.now().astimezone().isoformat(),
        "metrics": {
            "underlying_index": {
                "value": "000015.SH", "endpoint": "etf_basic", "field": "index_code",
            },
            "latest_price": None,
            "average_amount_20d": None,
            "trailing_cash_dividend_per_share": None,
            "price_change_1y": None,
            "distance_from_1y_high_pct": None,
            "trailing_dividend_yield": None,
            "trailing_dividend_yield_percentile_10y": None,
            "trailing_dividend_yield_valuation": None,
            "asset_scale": None,
            "fund_size_shares": None,
            "management_fee": None,
            "custody_fee": None,
            "underlying_pe": None,
            "underlying_pb": None,
            "underlying_dividend_yield": None,
        },
        "sources": [],
        "gaps": ["跟踪指数估值数据未覆盖。"],
        "category": "dividend",
        "fund_type": "ETF",
        "benchmark": "上证红利指数",
        "investment_assumption": None,
        "valuation_conclusion": {
            "status": "data_gap", "verdict": "research_unavailable", "label": None,
            "basis": None, "message": "跟踪指数的估值数据未覆盖，暂不提供估值判断",
        },
    }
    monkeypatch.setattr(DataToolsService, "get_etf_research_bundle", lambda _service, _symbol: bundle)
    validator = Validator()
    runner = SerenityAgentRunner(
        llm_client=llm, validator=validator, mode="real", execution_mode="two_phase",
    )
    db = ResearchDB(db_path=":memory:")
    app = create_research_app(
        db=db, conversation_mode="real", serenity_execution_mode="two_phase",
        validator=validator, serenity_runner=runner, allow_test_serenity_runner=True,
    )

    response = TestClient(app).post(
        "/api/research/single-security",
        json={"code": "510880.SH", "research_version": "v2.1"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == ("research_completed" if expected_status == "success" else "research_unavailable")
    assert result["research_v2_1"]["status"] == expected_status
    assert result["research_v2_1"]["snapshot"]["version"] == "510880-v21-2026-10-14.1"
    assert len(result["research_v2_1"]["snapshot"]["sha256"]) == 64
    assert result["research_v2_1"]["llm"]["status"] == ("success" if expected_status == "success" else "failure")
    assert len(llm.calls) == 1
    assert llm.calls[0]["max_tokens"] >= 3072
    if expected_status == "success":
        assert result["research_v2_1"]["layers"][2]["adequacy"] == "insufficient"
    else:
        assert "core_reason" not in result["research_v2_1"]
        assert "do-not-return" not in response.text
    assert db.list_themes() == []


def test_v21_synthesis_binds_model_output_to_snapshot_facts_and_uses_full_token_budget():
    client = FakeV21LLM()
    audit = SerenityAgentAudit()

    result = ResearchSynthesizer(client).synthesize_single_security_v21(
        target_symbol="510880.SH",
        snapshot=make_snapshot(),
        snapshot_sha256=SNAPSHOT_SHA256,
        runtime_facts=[],
        audit=audit,
    )

    assert result["status"] == "success"
    assert result["snapshot"]["version"] == "510880-v21-2026-10-14-test1"
    assert result["snapshot"]["sha256"] == SNAPSHOT_SHA256
    assert len(result["summary_facts"]) == 3
    assert all(isinstance(item["value"], (int, float)) for item in result["summary_facts"])
    assert result["summary_facts"][0]["source_id"] == "snapshot:000015.SH:factsheet-20260930"
    assert result["summary_facts"][0]["source_pages"] == ["p.1"]
    assert result["layers"][0]["counter_evidence"][0]["fact_refs"][0]["id"] == "issuer.601919.net_profit_yoy"
    assert "510880-v21-2026-10-14-test1" in client.calls[0]["messages"][0]["content"]
    assert SNAPSHOT_SHA256 in client.calls[0]["messages"][0]["content"]
    assert '"summary_fact_ids"' in client.calls[0]["system"]
    assert '"underlying_assets"' in client.calls[0]["system"]
    assert client.calls[0]["max_tokens"] >= 3072


def test_v21_synthesis_rejects_unbound_issuer_and_index_relationship():
    snapshot = make_snapshot()
    snapshot["relationships"][1]["to"] = "600256.SH"
    client = FakeV21LLM()

    with pytest.raises(ValueError, match="constituent|relationship|issuer"):
        ResearchSynthesizer(client).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=snapshot,
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )

    assert client.calls == []


def test_v21_latest_close_without_iopv_remains_insufficient_for_current_timing():
    client = FakeV21LLM()
    runtime_facts = [{
        "id": "market.latest_price",
        "source_id": "fund_daily:510880.SH:0",
        "value": 3.4,
        "unit": "元/份",
        "as_of": "2026-10-13",
        "scope": "current_market",
        "stale": False,
        "source": {
            "source_record_id": "fund_daily:510880.SH:0",
            "title": "ETF报告收盘价、日内高点与成交额",
        },
    }]

    result = ResearchSynthesizer(client).synthesize_single_security_v21(
        target_symbol="510880.SH",
        snapshot=make_snapshot(),
        snapshot_sha256=SNAPSHOT_SHA256,
        runtime_facts=runtime_facts,
        audit=SerenityAgentAudit(),
    )

    timing = next(layer for layer in result["layers"] if layer["layer_id"] == "current_timing")
    assert timing["adequacy"] == "insufficient"
    assert timing["evidence_level"] == "data_insufficient"
    assert "market.latest_price" in client.calls[0]["messages"][0]["content"]


def test_v21_rejects_non_insufficient_timing_without_iopv_premium():
    response = valid_v21_response()
    response["layers"][2]["adequacy"] = "limited"
    response["layers"][2]["evidence_level"] = "low"
    client = FakeV21LLM(response=response)
    runtime_facts = [{
        "id": "market.latest_price",
        "source_id": "fund_daily:510880.SH:0",
        "value": 3.4,
        "unit": "元/份",
        "as_of": "2026-10-13",
        "scope": "current_market",
        "stale": False,
        "source": {"source_record_id": "fund_daily:510880.SH:0"},
    }]

    with pytest.raises(ValueError, match="current timing"):
        ResearchSynthesizer(client).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=runtime_facts,
            audit=SerenityAgentAudit(),
        )


def test_v21_synthesis_rejects_missing_data_as_counter_evidence():
    response = valid_v21_response()
    response["layers"][0]["counter_evidence"][0]["fact_ids"] = ["gap.index_dailybasic_empty"]

    with pytest.raises(ValueError, match="fact|reference|source"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_synthesis_rejects_more_than_three_summary_values():
    response = valid_v21_response()
    response["summary_fact_ids"] = [
        "index.pe", "index.pb", "index.cosco_weight", "index.dividend_yield",
    ]

    with pytest.raises(ValueError, match="schema|summary|three|3"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_tracking_error_claim_from_three_month_return_spread():
    response = claim_aware_v21_response()
    spread = response["layers"][1]["supporting_evidence"][0]
    spread.update({
        "text": "基金规模较大且跟踪误差小。",
        "fact_ids": ["fund.q1.return_spread"],
        "claim_kind": "tracking_error",
    })

    with pytest.raises(ValueError, match="tracking error.*fact|fact.*tracking error"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_stability_claim_from_one_dividend_yield_snapshot():
    response = claim_aware_v21_response()
    evidence = response["layers"][0]["supporting_evidence"][0]
    evidence.update({
        "text": "指数估值处于较低水平且具备稳定股息收益。",
        "fact_ids": ["index.pe", "index.pb", "index.dividend_yield"],
        "claim_kind": "historical_pattern",
    })

    with pytest.raises(ValueError, match="historical pattern.*comparable|comparable.*historical pattern"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_synchronous_dividend_decline_from_one_ocf_change_and_one_plan():
    response = claim_aware_v21_response()
    counter = response["layers"][0]["counter_evidence"][0]
    counter.update({
        "text": "成份股经营现金流与分红能力同步下降，股息可持续性存疑。",
        "fact_ids": [
            "issuer.601919.operating_cash_flow_yoy",
            "issuer.601919.interim_dividend_plan",
        ],
        "claim_kind": "historical_pattern",
    })

    with pytest.raises(ValueError, match="historical pattern.*comparable|comparable.*historical pattern"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_index_wide_dividend_sustainability_claim_from_one_issuer():
    response = claim_aware_v21_response()
    counter = response["layers"][0]["counter_evidence"][0]
    counter.update({
        "text": "单个成份公司的现金流变化证明指数整体股息可持续性下降。",
        "fact_ids": [
            "issuer.601919.operating_cash_flow_yoy",
            "issuer.601919.interim_dividend_plan",
        ],
        "claim_kind": "population_generalization",
    })

    with pytest.raises(ValueError, match="index-scope"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_index_claim_that_mixes_one_issuer_with_unrelated_index_metric():
    response = claim_aware_v21_response()
    counter = response["layers"][0]["counter_evidence"][0]
    counter.update({
        "text": "单个成份公司的现金流变化与指数估值证明指数整体股息可持续性下降。",
        "fact_ids": ["issuer.601919.operating_cash_flow_yoy", "index.pe"],
        "claim_kind": "population_generalization",
    })

    with pytest.raises(ValueError, match="index-scope"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_population_claim_that_mixes_constituent_weight_with_index_metric():
    response = claim_aware_v21_response()
    risk = response["layers"][0]["risks"][0]
    risk.update({
        "text": "单个成份股权重与指数估值证明指数整体分红可持续性下降。",
        "fact_ids": ["index.cosco_weight", "index.pe"],
        "claim_kind": "population_generalization",
    })

    with pytest.raises(ValueError, match="index-scope"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_replication_quality_inference_from_mismatched_holding_measures():
    response = claim_aware_v21_response()
    comparison = {
        "text": "基金实际持仓接近指数成份权重，说明复制质量较高。",
        "fact_ids": ["fund.q1.cosco_holding", "index.cosco_weight"],
        "evidence_level": "high",
        "claim_kind": "cross_measure_comparison",
    }
    response["layers"][1]["risks"] = [comparison]

    with pytest.raises(ValueError, match="cross-measure.*comparable|comparable.*cross-measure"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_comparison_that_repeats_the_same_fact_id():
    response = claim_aware_v21_response()
    comparison = response["layers"][1]["supporting_evidence"][0]
    comparison.update({
        "text": "季度收益差与同一项季度收益差相同。",
        "fact_ids": ["fund.q1.return_spread", "fund.q1.return_spread"],
        "claim_kind": "cross_measure_comparison",
    })

    with pytest.raises(ValueError, match="cross-measure.*distinct|distinct.*cross-measure"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_rejects_reporting_period_limit_as_economic_counter_evidence():
    response = claim_aware_v21_response()
    response["layers"][1]["counter_evidence"] = [{
        "text": "上述收益差仅覆盖报告期，不能证明其后期间的跟踪效果或当前交易品质。",
        "fact_ids": ["fund.q1.return_spread"],
        "evidence_level": "medium",
        "claim_kind": "evidence_limitation",
    }]

    with pytest.raises(ValueError, match="limitation.*counter-evidence|counter-evidence.*limitation"):
        ResearchSynthesizer(FakeV21LLM(response=response)).synthesize_single_security_v21(
            target_symbol="510880.SH",
            snapshot=make_snapshot(),
            snapshot_sha256=SNAPSHOT_SHA256,
            runtime_facts=[],
            audit=SerenityAgentAudit(),
        )


def test_v21_allows_careful_period_scoped_and_issuer_scoped_statements():
    response = claim_aware_v21_response()
    response["layers"][0]["supporting_evidence"][0].update({
        "text": "指数股息率为该事实表时点的单期观测。",
        "fact_ids": ["index.dividend_yield"],
        "claim_kind": "observation",
    })
    response["layers"][0]["counter_evidence"][0].update({
        "text": "该公司的经营现金流走弱可能压缩其自身分配能力，但不足以代表指数整体。",
        "fact_ids": ["issuer.601919.operating_cash_flow_yoy"],
        "claim_kind": "conditional_inference",
    })
    response["layers"][1]["supporting_evidence"][0].update({
        "text": "基金与基准的三个月收益差可作为该报告期的单期记录。",
        "fact_ids": ["fund.q1.return_spread"],
        "claim_kind": "observation",
    })
    response["layers"][1]["risks"] = []
    response["layers"][1]["missing_evidence"].extend([
        "该指数股息率为单期数据，历史稳定性和相对历史位置尚无多期证据。",
        "单个成份公司的现金流变化和中期分红方案不足以判断指数整体分红可持续性。",
        "基金持仓与指数权重的时点和计量口径不同，不能据此判断当前复制质量。",
        "三个月收益差只覆盖一季度报告期，后续跟踪表现与当前交易品质尚未核实。",
        "目前尚无统计跟踪误差事实。",
    ])
    response["layers"][1]["thesis_changers"] = [{
        "text": "若后续同口径跟踪结果持续偏离，应重新评估产品层观点。",
        "fact_ids": ["fund.q1.return_spread"],
        "evidence_level": "low",
        "claim_kind": "conditional_inference",
    }]
    response["next_step"] = "纳入模拟研究候选"

    client = FakeV21LLM(response=response)
    result = ResearchSynthesizer(client).synthesize_single_security_v21(
        target_symbol="510880.SH",
        snapshot=make_snapshot(),
        snapshot_sha256=SNAPSHOT_SHA256,
        runtime_facts=[],
        audit=SerenityAgentAudit(),
    )

    assert result["status"] == "success"
    assert result["next_step"] == "纳入模拟研究候选"
    assert result["layers"][1]["adequacy"] == "limited"
    assert result["layers"][1]["supporting_evidence"][0]["evidence_level"] == "high"
    assert json.loads(client.calls[0]["messages"][0]["content"])["rules"][
        "period_fact_confidence_not_reduced_for_age_alone"
    ] is True
    assert "单一日期的估值/股息率不能推出稳定性" in client.calls[0]["system"]
    assert all(
        "claim_kind" not in item
        for layer in result["layers"]
        for group in ("supporting_evidence", "counter_evidence", "risks", "thesis_changers")
        for item in layer[group]
    )
