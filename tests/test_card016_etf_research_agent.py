import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.research import SingleSecurityResearchRequest, create_research_app
from backend.db.research import ResearchDB
from backend.services.data_tools import DataToolsService
from backend.services.serenity_agent import SerenityAgentAudit, SerenityAgentRunner
from backend.services.serenity_synthesizer import ResearchSynthesizer


def test_card016_accepts_explicit_v22_request_for_510880():
    request = SingleSecurityResearchRequest(code="510880", research_version="v2.2")
    assert request.research_version == "v2.2"
    with pytest.raises(ValidationError):
        SingleSecurityResearchRequest(code="600519", research_version="v2.2")


class NewsClient:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = []

    def query(self, api_name, **kwargs):
        self.calls.append((api_name, kwargs))
        if self.error:
            raise self.error
        return pd.DataFrame(self.rows or [])


def _recent_news_window():
    end = datetime.now(ZoneInfo("Asia/Shanghai")).replace(second=0, microsecond=0) - timedelta(minutes=1)
    start = end - timedelta(minutes=30)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def test_news_feed_uses_fixed_sources_and_returns_only_bounded_untrusted_excerpts():
    method = getattr(DataToolsService, "get_news_feed", None)
    assert callable(method), "the existing DataToolsService must expose the news feed read tool"
    start, end = _recent_news_window()
    start_at = datetime.fromisoformat(start)
    rows = [{
        "title": f"标题 {index}",
        "content": "x" * 1300,
        "pub_time": (start_at + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S"),
        "src": "新浪财经",
    } for index in range(6)]
    client = NewsClient(rows)

    result = method(DataToolsService(tushare_client=client),
        "major_news", start_date=start, end_date=end,
    )

    api, params = client.calls[0]
    assert api == "major_news"
    assert params == {
        "src": "新浪财经",
        "start_date": start,
        "end_date": end,
        "fields": "title,content,pub_time,src",
        "single_attempt": True,
    }
    assert len(result.raw_data) == 5
    assert result.raw_data[0]["published_at"] == (start_at + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    assert len(result.raw_data[0]["content_excerpt"]) == 1200
    assert result.raw_data[0]["content_truncated"] is True
    assert result.raw_data[0]["source"] == "新浪财经"
    assert result.raw_data[0]["source_url"] is None


def test_news_feed_keeps_requested_source_distinct_when_rows_omit_source_and_hides_provider_errors():
    method = getattr(DataToolsService, "get_news_feed", None)
    assert callable(method), "the existing DataToolsService must expose the news feed read tool"
    start, end = _recent_news_window()
    published_at = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [{"title": "标题", "content": "内容", "datetime": published_at}]
    client = NewsClient(rows)

    result = method(DataToolsService(tushare_client=client),
        "news", start_date=start, end_date=end,
    )

    assert client.calls[0][1]["src"] == "sina"
    assert result.raw_data[0]["requested_source"] == "sina"
    assert result.raw_data[0]["source"] is None
    assert result.raw_data[0]["published_at"] == published_at

    failing = DataToolsService(tushare_client=NewsClient(error=RuntimeError("permission denied secret")))
    failed = method(failing, "news", start_date=start, end_date=end)
    assert failed.errors == ["permission_denied"]
    assert "secret" not in str(failed.model_dump())


class ToolUseLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create_message(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _bundle():
    return {
        "symbol": "510880.SH",
        "is_etf": True,
        "as_of": "2026-10-14",
        "retrieved_at": "2026-10-15T09:00:00+08:00",
        "category": "dividend",
        "fund_type": "股票型",
        "benchmark": "红利指数",
        "metrics": {"underlying_index": {
            "value": "000015.SH", "endpoint": "etf_basic", "field": "index_code",
        }},
        "endpoint_statuses": {"fund_basic": "ok"},
        "sources": [{
            "source_record_id": "fund_basic:510880.SH:0",
            "endpoint": "fund_basic",
            "title": "510880 ETF 基础资料",
            "as_of": "2026-10-14",
            "summary": "已核验 ETF 基础资料。",
            "source_url": "",
        }],
        "gaps": ["当前时机缺少 IOPV 溢价资料。"],
        "valuation_conclusion": {
            "status": "data_gap",
            "verdict": "research_unavailable",
            "label": None,
            "basis": None,
            "message": "跟踪指数的估值数据未覆盖，暂不提供估值判断",
        },
    }


def _verified_snapshot():
    path = Path(__file__).resolve().parents[1] / "backend" / "research_snapshots" / "510880_v21_20261014.json"
    content = path.read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


def _final_response(source_id=None):
    groups = {"supporting_evidence": [], "counter_evidence": [], "risks": [], "thesis_changers": []}
    if source_id:
        groups["supporting_evidence"] = [{
            "text": "新闻 feed 仅提供一项待核验线索。",
            "source_ids": [source_id],
            "evidence_level": "low",
        }]
    layers = []
    for layer_id in ("underlying_assets", "etf_product", "current_timing"):
        layers.append({
            "layer_id": layer_id,
            "adequacy": "insufficient",
            "judgment": "现有资料不足以支持更明确判断。",
            "evidence_level": "data_insufficient",
            **groups,
            "missing_evidence": ["仍需补充可核验资料。"],
        })
    return {
        "hypothesis": "检查现有证据能否支撑红利 ETF 的研究判断。",
        "conclusion": "当前证据不足以形成明确的研究结论。",
        "layers": layers,
        "next_step": "缺少决定性证据",
        "next_step_reason": "补齐可核验资料后再评估。",
    }


def _text_response(value):
    import json
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "stop_reason": "end_turn", "usage": {}}


def _tool_response(*calls):
    return {
        "content": [{"type": "tool_use", "id": f"tool-{index}", "name": name, "input": tool_input}
                    for index, (name, tool_input) in enumerate(calls, 1)],
        "stop_reason": "tool_use",
        "usage": {},
    }


def _run_v22(llm, data_tools, audit=None):
    method = getattr(ResearchSynthesizer, "synthesize_single_security_v22", None)
    assert callable(method), "ResearchSynthesizer must provide the bounded V2.2 ETF tool loop"
    snapshot, snapshot_sha256 = _verified_snapshot()
    return method(
        ResearchSynthesizer(llm),
        target_symbol="510880.SH",
        etf_bundle=_bundle(),
        verified_snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
        data_tools=data_tools,
        audit=audit or SerenityAgentAudit(),
    )


def test_v22_uses_only_ai_requested_news_and_binds_feed_source_ids():
    start, end = _recent_news_window()
    published_at = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    news_client = NewsClient([{
        "title": "新闻标题", "content": "新闻正文", "datetime": published_at,
    }])
    data_tools = DataToolsService(tushare_client=news_client)
    llm = ToolUseLLM([
        _tool_response(("search_news", {
            "hypothesis": "检验已有红利证据是否有近期变化。",
            "evidence_need": "补充近期新闻 feed 线索。",
            "start_date": start,
            "end_date": end,
        })),
        _tool_response(("finish_research", _final_response("tushare_news:feed:1:0"))),
    ])

    result = _run_v22(llm, data_tools)

    assert result["status"] == "success"
    assert len(llm.calls) == 2
    trace = result["tool_trace"][0]
    assert trace["tool"] == "search_news"
    assert trace["origin"] == "llm_tool_use"
    assert trace["request_sent"] is True
    assert trace["source_ids"] == ["tushare_news:feed:1:0"]
    source = next(item for item in result["sources"] if item["source_record_id"] == "tushare_news:feed:1:0")
    assert source["requested_source"] == "sina"
    assert source["source"] is None
    assert source["published_at"] == published_at
    assert source["source_url"] is None
    assert result["tool_trace"][1]["tool"] == "finish_research"
    assert result["tool_trace"][1]["status"] == "submitted"


def test_v22_accepts_security_code_in_research_prose_and_finishes_read_news_final_within_three_calls():
    start, end = _recent_news_window()
    published_at = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    news_client = NewsClient([{
        "title": "新闻标题", "content": "新闻正文", "datetime": published_at,
    }])
    data_tools = DataToolsService(tushare_client=news_client)
    final = _final_response("tushare_news:feed:2:0")
    final["conclusion"] = "510880.SH 的研究快照只支持有边界的历史判断。"
    llm = ToolUseLLM([
        _tool_response(("read_etf_evidence", {
            "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
            "evidence_need": "读取已核验指数及 ETF 证据。",
            "scopes": ["underlying_assets", "etf_product"],
        })),
        _tool_response(("search_news", {
            "hypothesis": "核对已有研究假设是否有近期变化。",
            "evidence_need": "补充近期新闻 feed 线索。",
            "start_date": start,
            "end_date": end,
        })),
        _tool_response(("finish_research", final)),
    ])

    result = _run_v22(llm, data_tools)

    assert result["status"] == "success"
    assert [call["tool"] for call in result["tool_trace"]] == [
        "read_etf_evidence", "search_news", "finish_research",
    ]
    assert len(llm.calls) == 3
    assert len(news_client.calls) == 1
    assert result["conclusion"] == final["conclusion"]
    assert [call["tool_choice"] for call in llm.calls] == [
        {"type": "auto", "disable_parallel_tool_use": True},
        {"type": "auto", "disable_parallel_tool_use": True},
        {"type": "auto", "disable_parallel_tool_use": True},
    ]
    assert [tool["name"] for tool in llm.calls[2]["tools"]] == ["finish_research"]


def test_v22_api_uses_isolated_tool_loop_and_preserves_deterministic_valuation(monkeypatch):
    from backend.services.llm_client import LLMCallResult

    snapshot, _ = _verified_snapshot()
    first_evidence_id = snapshot["facts"][0]["source_id"]
    class DiagnosticToolUseLLM(ToolUseLLM):
        def create_message(self, **kwargs):
            response = super().create_message(**kwargs)
            counts = {
                "text": sum(block.get("type") == "text" for block in response["content"]),
                "tool_use": sum(block.get("type") == "tool_use" for block in response["content"]),
                "thinking": 0,
                "redacted_thinking": 0,
                "other": 0,
            }
            return LLMCallResult(response, {
                "provider_stop_reason": response["stop_reason"],
                "provider_content_block_counts": counts,
            })

    llm = DiagnosticToolUseLLM([
        _tool_response(("read_etf_evidence", {
            "hypothesis": "核对底层资产证据能否支持研究判断。",
            "evidence_need": "读取现有 ETF 与官方指数证据。",
            "scopes": ["underlying_assets"],
        })),
        _tool_response(("finish_research", _final_response(first_evidence_id))),
    ])

    class IdentityClient:
        def query(self, api, **kwargs):
            if api == "fund_basic":
                return pd.DataFrame([{
                    "ts_code": "510880.SH", "name": "华泰柏瑞上证红利ETF", "market": "E",
                }])
            return pd.DataFrame()

    class Validator:
        tushare_client = IdentityClient()

    validator = Validator()
    monkeypatch.setattr(DataToolsService, "get_etf_research_bundle", lambda _service, _symbol: _bundle())
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
        json={"code": "510880.SH", "research_version": "v2.2"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    research = result["research_v2_2"]
    assert research["status"] == "success"
    assert len(research["layers"]) == 3
    assert research["tool_trace"][0]["origin"] == "llm_tool_use"
    assert research["tool_trace"][1]["tool"] == "finish_research"
    assert research["tool_trace"][1]["status"] == "submitted"
    assert result["verdict"] == _bundle()["valuation_conclusion"]["message"]
    assert result["transaction_status"] == {
        "eligibility": "本次未评估交易资格",
        "signal": "本次未提供交易信号",
    }
    assert len(llm.calls) == 2
    read_result = json.loads(llm.calls[1]["messages"][-1]["content"][0]["content"])
    verified_snapshot = read_result["verified_snapshot"]
    assert verified_snapshot["version"] == snapshot["version"]
    assert verified_snapshot["facts"]
    assert verified_snapshot["limitations"] == snapshot["limitations"]
    assert any(item["source_record_id"] == first_evidence_id for item in research["sources"])
    assert db.list_themes() == []
    assert result["research_diagnostic"]["calls"][0]["provider_stop_reason"] == "tool_use"
    assert result["research_diagnostic"]["calls"][0]["provider_content_block_counts"] == {
        "text": 0, "tool_use": 1, "thinking": 0, "redacted_thinking": 0, "other": 0,
    }
    assert result["research_diagnostic"]["calls"][0]["normalized_content_block_counts"] == {
        "text": 0, "tool_use": 1, "other": 0,
    }

    llm.responses.append({
        "content": [{"type": "text", "text": "private malformed model text"}],
        "stop_reason": "end_turn",
        "usage": {},
    })
    failed_response = TestClient(app).post(
        "/api/research/single-security",
        json={"code": "510880.SH", "research_version": "v2.2"},
    )
    failed_diagnostic = failed_response.json()["research_diagnostic"]["calls"][0]
    assert failed_response.status_code == 200
    assert failed_diagnostic["failure_class"] == "response_protocol_mismatch"
    assert failed_diagnostic["failure_stage"] == "structured_finish_required"
    assert failed_diagnostic["failure_type"] == "finish_tool_missing"
    assert failed_diagnostic["parse_reached"] is False
    assert failed_diagnostic["provider_content_block_counts"] == {
        "text": 1, "tool_use": 0, "thinking": 0, "redacted_thinking": 0, "other": 0,
    }
    assert "private malformed model text" not in json.dumps(failed_diagnostic)


def test_v22_refuses_unknown_write_tools_and_stops_after_news_error():
    untouched = NewsClient([{"title": "unused", "content": "unused", "datetime": "2026-10-14 09:30:00"}])
    unknown_llm = ToolUseLLM([_tool_response(("write_ledger", {"action": "buy"}))])
    unknown = _run_v22(unknown_llm, DataToolsService(tushare_client=untouched))
    assert unknown["status"] == "unavailable"
    assert unknown["failure_reason"] == "tool_not_allowed"
    assert untouched.calls == []

    start, end = _recent_news_window()
    failing_client = NewsClient(error=RuntimeError("permission denied private detail"))
    failing_llm = ToolUseLLM([_tool_response(("search_news", {
        "hypothesis": "核验近期变化。",
        "evidence_need": "取得新闻来源与时间。",
        "start_date": start,
        "end_date": end,
    }))])
    failed = _run_v22(failing_llm, DataToolsService(tushare_client=failing_client))
    assert failed["status"] == "unavailable"
    assert failed["failure_reason"] == "permission_denied"
    assert len(failing_llm.calls) == 1
    assert len(failing_client.calls) == 1


def test_v22_can_finish_and_rejects_parallel_tool_budget_overrun():
    finished_llm = ToolUseLLM([
        _tool_response(("read_etf_evidence", {
            "hypothesis": "核对当前已有证据是否足够形成研究结论。",
            "evidence_need": "读取已加载的 ETF 与指数快照事实。",
            "scopes": ["underlying_assets", "etf_product"],
        })),
        _tool_response(("finish_research", _final_response("fund_basic:510880.SH:0"))),
    ])
    finished = _run_v22(finished_llm, DataToolsService())
    assert finished["status"] == "success"
    assert finished["stop_reason"] == "finish_research"
    assert [item["tool"] for item in finished["tool_trace"]] == ["read_etf_evidence", "finish_research"]
    assert len(finished_llm.calls) == 2

    start, end = _recent_news_window()
    call = ("search_news", {
        "hypothesis": "核验近期变化。", "evidence_need": "补充 feed。",
        "start_date": start, "end_date": end,
    })
    client = NewsClient([{"title": "新闻标题", "content": "新闻正文", "datetime": start}])
    parallel_llm = ToolUseLLM([_tool_response(call, call, call, call)])
    audit = SerenityAgentAudit()
    parallel = _run_v22(parallel_llm, DataToolsService(tushare_client=client), audit)
    diagnostic = audit.call_diagnostics[0]
    assert parallel["status"] == "unavailable"
    assert parallel["failure_reason"] == "response_protocol_mismatch"
    assert diagnostic["failure_stage"] == "tool_choice_protocol"
    assert diagnostic["failure_type"] == "parallel_tool_use_not_allowed"
    assert parallel["tool_trace"] == []
    assert len(parallel_llm.calls) == 1
    assert parallel_llm.calls[0]["tool_choice"] == {
        "type": "auto", "disable_parallel_tool_use": True,
    }
    assert client.calls == []


def test_v22_tool_use_stop_without_tool_block_is_protocol_mismatch():
    response = {
        "content": [{"type": "text", "text": "not json; must not leak"}],
        "stop_reason": "tool_use",
        "usage": {},
    }
    llm = ToolUseLLM([response])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[0]
    assert result["failure_reason"] == "response_protocol_mismatch"
    assert diagnostic["failure_stage"] == "tool_use_protocol"
    assert diagnostic["failure_type"] == "tool_use_block_missing"
    assert diagnostic["provider_stop_reason"] == "tool_use"
    assert diagnostic["normalized_content_block_counts"] == {"text": 1, "tool_use": 0, "other": 0}
    assert diagnostic["response_received"] is True
    assert "not json" not in json.dumps(diagnostic)


def test_v22_auto_text_response_is_unavailable_without_structured_finish():
    llm = ToolUseLLM([{
        "content": [{"type": "text", "text": "private malformed model text"}],
        "stop_reason": "end_turn",
        "usage": {},
    }])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[0]
    assert result["failure_reason"] == "response_protocol_mismatch"
    assert diagnostic["failure_stage"] == "structured_finish_required"
    assert diagnostic["failure_type"] == "finish_tool_missing"
    assert diagnostic["parse_reached"] is False
    assert "private malformed model text" not in json.dumps(diagnostic)
    assert llm.calls[0]["tool_choice"] == {
        "type": "auto", "disable_parallel_tool_use": True,
    }


def test_v22_schema_failure_records_safe_field_paths_without_input_values():
    llm = ToolUseLLM([_tool_response(("finish_research", {
        "hypothesis": "safe hypothesis",
        "conclusion": "private model text",
        "layers": _final_response()["layers"],
        "next_step": "等待具体条件",
        "next_step_reason": "缺少证据。",
        "untrusted_extra_field": "private input value",
    }))])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[0]
    serialized = json.dumps(diagnostic)
    assert result["failure_reason"] == "response_schema_or_source_validation_failed"
    assert diagnostic["failure_stage"] == "schema_validation"
    assert diagnostic["failure_type"] == "ValidationError"
    assert "unknown_field" in diagnostic["schema_error_paths"]
    assert "untrusted_extra_field" not in serialized
    assert "private input value" not in serialized
    assert "private model text" not in serialized
    assert result["tool_trace"][0]["status"] == "invalid_result"


def test_v22_final_auto_round_requires_structured_finish_even_when_json_text_is_valid():
    start, end = _recent_news_window()
    news_client = NewsClient([{
        "title": "新闻标题", "content": "新闻正文", "datetime": start,
    }])
    llm = ToolUseLLM([
        _tool_response(("read_etf_evidence", {
            "hypothesis": "核对已有 ETF 证据。",
            "evidence_need": "读取已加载证据。",
            "scopes": ["underlying_assets"],
        })),
        _tool_response(("search_news", {
            "hypothesis": "核验近期变化。",
            "evidence_need": "补充近期 feed。",
            "start_date": start,
            "end_date": end,
        })),
        _text_response(_final_response("tushare_news:feed:2:0")),
    ])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(tushare_client=news_client), audit)

    diagnostic = audit.call_diagnostics[-1]
    assert result["status"] == "unavailable"
    assert result["failure_reason"] == "response_protocol_mismatch"
    assert diagnostic["failure_stage"] == "structured_finish_required"
    assert diagnostic["failure_type"] == "finish_tool_missing"
    assert diagnostic["parse_reached"] is False
    assert llm.calls[2]["tool_choice"] == {
        "type": "auto", "disable_parallel_tool_use": True,
    }
    from backend.services.serenity_synthesizer import SingleSecurityResearchV22Schema
    assert llm.calls[2]["tools"][0]["input_schema"] == SingleSecurityResearchV22Schema.model_json_schema()


def test_v22_source_binding_failure_records_missing_source_id_only():
    llm = ToolUseLLM([_tool_response(("finish_research", _final_response("unknown:source:123")))])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[0]
    assert result["failure_reason"] == "response_schema_or_source_validation_failed"
    assert diagnostic["failure_stage"] == "source_binding"
    assert diagnostic["failure_type"] == "source_id_not_found"
    assert diagnostic["missing_source_id"] == "unknown:source:123"
    assert "text" not in diagnostic


def test_v22_finish_rejects_evidence_without_a_source_id():
    final = _final_response()
    final["layers"][0]["supporting_evidence"] = [{
        "text": "无来源编号的证据不得进入报告。",
        "source_ids": [],
        "evidence_level": "low",
    }]
    llm = ToolUseLLM([_tool_response(("finish_research", final))])
    audit = SerenityAgentAudit()

    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[0]
    assert result["status"] == "unavailable"
    assert result["failure_reason"] == "response_schema_or_source_validation_failed"
    assert diagnostic["failure_stage"] == "schema_validation"
    assert diagnostic["failure_type"] == "ValidationError"
    assert "layers[0].supporting_evidence[0].source_ids" in diagnostic["schema_error_paths"]
    assert result["tool_trace"][0]["status"] == "invalid_result"


def _offline_sdk_tool_response(name, tool_input, call_number):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=f"offline-message-{call_number}",
        model="offline-test-model",
        role="assistant",
        stop_reason="tool_use",
        content=[SimpleNamespace(
            type="tool_use",
            id=f"offline-tool-{call_number}",
            name=name,
            input=tool_input,
        )],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _offline_sdk_llm_client(monkeypatch, responder):
    from types import SimpleNamespace
    from backend.services.llm_client import LLMClient

    class OfflineMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            result = responder(kwargs, len(self.calls))
            if isinstance(result, BaseException):
                raise result
            return result

    messages = OfflineMessages()
    provider = SimpleNamespace(messages=messages)
    monkeypatch.setattr("backend.services.llm_client.Anthropic", lambda **_kwargs: provider)
    monkeypatch.setattr("backend.services.llm_client.time.sleep", lambda _seconds: None)
    client = LLMClient(
        api_key="offline-test-key",
        base_url="https://offline.invalid",
        model="offline-test-model",
    )
    return client, messages


def test_v22_actual_llm_client_preserves_finish_attempt_after_nonfinal_timeout(monkeypatch):
    import json
    from anthropic import APITimeoutError
    from httpx import Request
    from backend.services.llm_client import _CALL_LIMIT_PER_LOOP, _DECISION_LOOP_CALLS

    start, end = _recent_news_window()
    read_input = {
        "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
        "evidence_need": "读取已核验指数及 ETF 证据。",
        "scopes": ["underlying_assets", "etf_product"],
    }
    search_input = {
        "hypothesis": "核对已有研究假设是否有近期变化。",
        "evidence_need": "补充近期新闻 feed 线索。",
        "start_date": start,
        "end_date": end,
    }
    final = _final_response("fund_basic:510880.SH:0")
    timeout = APITimeoutError(request=Request(
        "POST", "https://offline.invalid/v1/messages?access_token=offline-secret-sentinel",
    ))

    def respond(kwargs, call_number):
        if call_number == 1:
            return _offline_sdk_tool_response("read_etf_evidence", read_input, call_number)
        if call_number == 2:
            return timeout
        if [tool["name"] for tool in kwargs["tools"]] == ["finish_research"]:
            return _offline_sdk_tool_response("finish_research", final, call_number)
        return _offline_sdk_tool_response("search_news", search_input, call_number)

    llm, sdk = _offline_sdk_llm_client(monkeypatch, respond)
    news = NewsClient([])
    audit = SerenityAgentAudit()
    prior_loops = set(_DECISION_LOOP_CALLS)

    result = _run_v22(llm, DataToolsService(tushare_client=news), audit)

    new_loops = set(_DECISION_LOOP_CALLS) - prior_loops
    assert len(new_loops) == 1
    loop_id = new_loops.pop()
    assert _CALL_LIMIT_PER_LOOP == 3
    assert _DECISION_LOOP_CALLS[loop_id] == 3
    assert len(sdk.calls) == 3
    assert result["status"] == "success"
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        "read_etf_evidence", "finish_research",
    ]
    assert result["tool_trace"][-1]["status"] == "submitted"
    assert news.calls == []
    timeout_diagnostic = audit.call_diagnostics[1]
    assert timeout_diagnostic["attempt_count"] == 1
    assert timeout_diagnostic["retry_count"] == 0
    assert timeout_diagnostic["retry_stop_reason"] == "decision_loop_budget_reserved"
    assert timeout_diagnostic["failure_stage"] == "timeout_retry_budget"
    assert timeout_diagnostic["failure_type"] == "decision_loop_budget_reserved"
    assert sum(call["attempt_count"] for call in audit.call_diagnostics) == 3
    assert "offline-secret-sentinel" not in json.dumps(audit.call_diagnostics)


def test_v22_first_turn_timeout_retry_success_reserves_final_attempt(monkeypatch):
    from anthropic import APITimeoutError
    from httpx import Request
    from backend.services.llm_client import _CALL_LIMIT_PER_LOOP, _DECISION_LOOP_CALLS

    read_input = {
        "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
        "evidence_need": "读取已核验指数及 ETF 证据。",
        "scopes": ["underlying_assets", "etf_product"],
    }
    final = _final_response("fund_basic:510880.SH:0")
    timeout = APITimeoutError(request=Request("POST", "https://offline.invalid/v1/messages"))

    def respond(kwargs, call_number):
        if call_number == 1:
            return timeout
        if call_number == 2:
            return _offline_sdk_tool_response("read_etf_evidence", read_input, call_number)
        if [tool["name"] for tool in kwargs["tools"]] == ["finish_research"]:
            return _offline_sdk_tool_response("finish_research", final, call_number)
        start, end = _recent_news_window()
        return _offline_sdk_tool_response("search_news", {
            "hypothesis": "核对近期变化。",
            "evidence_need": "查询近期新闻 feed。",
            "start_date": start,
            "end_date": end,
        }, call_number)

    llm, sdk = _offline_sdk_llm_client(monkeypatch, respond)
    news = NewsClient([])
    audit = SerenityAgentAudit()
    prior_loops = set(_DECISION_LOOP_CALLS)

    result = _run_v22(llm, DataToolsService(tushare_client=news), audit)

    new_loops = set(_DECISION_LOOP_CALLS) - prior_loops
    assert len(new_loops) == 1
    assert _DECISION_LOOP_CALLS[new_loops.pop()] == _CALL_LIMIT_PER_LOOP == 3
    assert len(sdk.calls) == 3
    assert result["status"] == "success"
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        "read_etf_evidence", "finish_research",
    ]
    assert news.calls == []
    assert audit.call_diagnostics[0]["attempt_count"] == 2
    assert audit.call_diagnostics[0]["retry_count"] == 1
    reserved = audit.call_diagnostics[1]
    assert reserved["attempt_count"] == 0
    assert reserved["retry_stop_reason"] == "decision_loop_budget_reserved"
    assert [tool["name"] for tool in sdk.calls[-1]["tools"]] == ["finish_research"]
    assert sum(call["attempt_count"] for call in audit.call_diagnostics) == 3


def test_v22_actual_llm_client_completes_read_news_finish_with_three_attempts(monkeypatch):
    from backend.services.llm_client import _CALL_LIMIT_PER_LOOP, _DECISION_LOOP_CALLS

    start, end = _recent_news_window()
    published_at = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    read_input = {
        "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
        "evidence_need": "读取已核验指数及 ETF 证据。",
        "scopes": ["underlying_assets", "etf_product"],
    }
    news_input = {
        "hypothesis": "核对已有研究假设是否有近期变化。",
        "evidence_need": "补充近期新闻 feed 线索。",
        "start_date": start,
        "end_date": end,
    }
    final = _final_response("tushare_news:feed:2:0")
    responses = [
        ("read_etf_evidence", read_input),
        ("search_news", news_input),
        ("finish_research", final),
    ]

    def respond(_kwargs, call_number):
        name, tool_input = responses[call_number - 1]
        return _offline_sdk_tool_response(name, tool_input, call_number)

    llm, sdk = _offline_sdk_llm_client(monkeypatch, respond)
    news = NewsClient([{"title": "新闻标题", "content": "新闻正文", "datetime": published_at}])
    audit = SerenityAgentAudit()
    prior_loops = set(_DECISION_LOOP_CALLS)

    result = _run_v22(llm, DataToolsService(tushare_client=news), audit)

    new_loops = set(_DECISION_LOOP_CALLS) - prior_loops
    assert len(new_loops) == 1
    assert _DECISION_LOOP_CALLS[new_loops.pop()] == _CALL_LIMIT_PER_LOOP == 3
    assert len(sdk.calls) == 3
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        "read_etf_evidence", "search_news", "finish_research",
    ]
    assert result["status"] == "success", {
        "failure_reason": result.get("failure_reason"),
        "tool_trace": result.get("tool_trace"),
        "diagnostic": audit.call_diagnostics[-1] if audit.call_diagnostics else None,
    }
    assert result["tool_trace"][-1]["status"] == "submitted"
    assert len(news.calls) == 1
    assert [tool["name"] for tool in sdk.calls[-1]["tools"]] == ["finish_research"]


def test_v22_final_finish_timeout_at_attempt_limit_returns_existing_trace(monkeypatch):
    from anthropic import APITimeoutError
    from httpx import Request
    from backend.services.llm_client import _CALL_LIMIT_PER_LOOP, _DECISION_LOOP_CALLS

    start, end = _recent_news_window()
    published_at = (datetime.fromisoformat(start) + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    read_input = {
        "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
        "evidence_need": "读取已核验指数及 ETF 证据。",
        "scopes": ["underlying_assets", "etf_product"],
    }
    news_input = {
        "hypothesis": "核对已有研究假设是否有近期变化。",
        "evidence_need": "补充近期新闻 feed 线索。",
        "start_date": start,
        "end_date": end,
    }
    timeout = APITimeoutError(request=Request("POST", "https://offline.invalid/v1/messages"))
    responses = [
        ("read_etf_evidence", read_input),
        ("search_news", news_input),
        timeout,
    ]

    def respond(_kwargs, call_number):
        response = responses[call_number - 1]
        if isinstance(response, BaseException):
            return response
        name, tool_input = response
        return _offline_sdk_tool_response(name, tool_input, call_number)

    llm, sdk = _offline_sdk_llm_client(monkeypatch, respond)
    news = NewsClient([{
        "title": "新闻标题", "content": "新闻正文", "datetime": published_at,
    }])
    audit = SerenityAgentAudit()
    prior_loops = set(_DECISION_LOOP_CALLS)

    result = _run_v22(llm, DataToolsService(tushare_client=news), audit)

    new_loops = set(_DECISION_LOOP_CALLS) - prior_loops
    assert len(new_loops) == 1
    assert _DECISION_LOOP_CALLS[new_loops.pop()] == _CALL_LIMIT_PER_LOOP == 3
    assert len(sdk.calls) == 3
    assert result["status"] == "unavailable"
    assert result["failure_reason"] == "llm_budget_exhausted"
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        "read_etf_evidence", "search_news",
    ]
    assert all(entry["tool"] != "finish_research" for entry in result["tool_trace"])
    final_diagnostic = audit.call_diagnostics[-1]
    assert final_diagnostic["attempt_count"] == 1
    assert final_diagnostic["retry_count"] == 0
    assert final_diagnostic["retry_stop_reason"] == "decision_loop_budget_exhausted"
    assert final_diagnostic["failure_stage"] == "timeout_retry_budget"
    assert final_diagnostic["timeout"] is True
    assert sum(call["attempt_count"] for call in audit.call_diagnostics) == 3


def test_v22_no_diagnostic_exception_returns_safely_with_existing_trace():
    class NoDiagnosticLLM:
        def __init__(self):
            self.calls = 0

        def create_message(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _tool_response(("read_etf_evidence", {
                    "hypothesis": "核对底层资产与产品资料是否支持当前研究假设。",
                    "evidence_need": "读取已核验指数及 ETF 证据。",
                    "scopes": ["underlying_assets", "etf_product"],
                }))
            raise ValueError("private-provider-error-sentinel")

    import json

    llm = NoDiagnosticLLM()
    audit = SerenityAgentAudit()
    result = _run_v22(llm, DataToolsService(), audit)

    diagnostic = audit.call_diagnostics[-1]
    assert result["status"] == "unavailable"
    assert result["failure_reason"] == "llm_request_failed"
    assert [entry["tool"] for entry in result["tool_trace"]] == ["read_etf_evidence"]
    assert diagnostic["exception_class"] == "ValueError"
    assert diagnostic["failure_class"] == "client_exception"
    assert diagnostic["failure_stage"] == "provider_call"
    assert diagnostic["failure_type"] == "client_exception"
    assert audit.stage_calls[-1]["status"] == "failure"
    assert "private-provider-error-sentinel" not in json.dumps(diagnostic)
