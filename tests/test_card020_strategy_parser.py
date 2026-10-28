from __future__ import annotations

import hashlib
import pytest

from backend.services.strategy_idea_flow import StrategyIdeaFlowService


EXPECTED_FIELDS = {
    "strategy_id": "510880-vol-budget-v1",
    "symbol": "510880.SH",
    "initial_capital_cny": "5000",
    "assets": "510880 and CNY cash only",
    "leverage_and_shorting": "forbidden",
    "signal_frequency": "SSE month-end close",
    "volatility_lookback": "60 trading-day returns",
    "annualized_volatility_target": "0.10",
    "target_position_formula": "min(1, 0.10 / annualized volatility)",
    "zero_volatility_rule": "zero volatility means 100% target",
    "missing_market_data_rule": "stop; do not infer or impute",
    "maximum_exposure": "1.00",
    "lot_size_shares": "100",
    "commission_rate": "0.0003",
    "minimum_commission_cny": "5",
    "commission_limit_ratio": "0.005",
    "commission_filter_action": "cancel remaining monthly adjustment above 0.5%",
    "execution_timing": "next valid SSE trading day open",
    "signal_price": "causally valid adjusted close",
    "execution_price": "raw open with adverse slippage and adverse tick rounding",
    "volume_capacity": "10% of prior valid trading-day volume, rounded down to 100 shares",
    "daily_fill_limit": "at most one fill per account per trading day",
    "base_slippage": "0.0005",
    "stress_slippage": "0.001",
    "research_start": "2018-01-02",
    "research_end": "2020-12-31",
    "preheat_start": "2016-12-23",
    "preheat_end": "2017 year-end",
    "buy_and_hold": "one independent initial 5000 CNY buy order, then hold",
    "static_half": "initial up to 2500 CNY including costs, then no rebalance",
    "dividend_accounting": "Card017 V2 entitlement, receivable, payment and no double count",
    "t_plus_one_and_market_limits": "enforced",
    "main_end_value": "settled cash plus raw-close holdings plus confirmed dividend receivable",
    "realized_volatility": "daily NAV simple returns, sample standard deviation times sqrt(252), minimum two returns",
    "drawdown_method": "amount and ratio independently determine peaks, troughs and recovery",
    "segment_normalization": "2018-2019 and 2020 each start at 5000 for evaluation only; continuous ledger is not reset",
    "category_order": "D-C-A-B",
    "D_rule": "untrusted critical source data or computation blocks evaluation",
    "C_no_dynamic_rule": "no executed risk adjustment beyond initial build is C",
    "C_stable_dominance_rule": "the same simple comparator dominates in both base and stress costs",
    "dominance_definition": "comparator terminal value >= candidate, both drawdowns <= candidate, at least one strict improvement",
    "A_full_period_rule": "candidate is no worse than buy-and-hold on terminal value and both drawdowns in base and stress, with one strict improvement per scenario",
    "A_segment_rule": "buy-and-hold must not dominate in any 2018-2019 or 2020 segment under base or stress costs",
    "B_rule": "all other valid results, with tradeoffs and unclear advantages described",
}


class ToolUseClient:
    def __init__(self, tool_input: dict, *, stop_reason: str | None = "tool_use", extra_tool_calls: int = 0):
        from types import SimpleNamespace

        self.tool_input = tool_input
        self.stop_reason = stop_reason
        self.extra_tool_calls = extra_tool_calls
        self.calls: list[dict] = []
        self.model = "synthetic-test-model"
        self.client = SimpleNamespace(messages=self)

    def stream(self, **kwargs):
        from types import SimpleNamespace

        self.calls.append(kwargs)

        class FakeStream:
            response = SimpleNamespace(status_code=200)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def __iter__(self):
                events = [
                    SimpleNamespace(type="message_start"),
                    SimpleNamespace(type="ping"),
                ]
                for _ in range(1 + self_outer.extra_tool_calls):
                    events.extend([
                        SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="tool_use")),
                        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta")),
                        SimpleNamespace(type="content_block_stop"),
                    ])
                events.extend([SimpleNamespace(type="message_delta"), SimpleNamespace(type="message_stop")])
                return iter(events)

            def get_final_message(self):
                content = [
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_510880_strategy_mapping",
                        input=self_outer.tool_input,
                    )
                ]
                content.extend(
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_510880_strategy_mapping",
                        input=self_outer.tool_input,
                    )
                    for _ in range(self_outer.extra_tool_calls)
                )
                return SimpleNamespace(
                    id="synthetic-card020-response",
                    model="synthetic-test-model",
                    stop_reason=self_outer.stop_reason,
                    content=content,
                )

            def close(self):
                return None

        self_outer = self
        return FakeStream()

    def create_message(self, **_kwargs):
        raise AssertionError("Card020 parser must use the complete SDK stream")


def build_input(
    fields: dict[str, str] | None = None,
    *,
    extra_lines: list[str] | None = None,
    blank_lines_before: set[int] | None = None,
):
    values = dict(fields or EXPECTED_FIELDS)
    blank_lines_before = blank_lines_before or set()
    lines = []
    mappings = []
    for index, (field, value) in enumerate(values.items()):
        if index in blank_lines_before:
            lines.append("")
        line_number = len(lines) + 1
        line = f"{field} = {value}"
        lines.append(line)
        mappings.append({
            "field": field,
            "value": value,
            "source_line_numbers": [line_number],
            "source_quotes": [line],
        })
    coverage = [
        {"line_number": item["source_line_numbers"][0], "classification": "mapped_rule"}
        for item in mappings
    ]
    for line in extra_lines or []:
        lines.append(line)
        coverage.append({"line_number": len(lines), "classification": "context"})
    raw_text = "\n".join(lines)
    return raw_text, {"mappings": mappings, "line_coverage": coverage}


def insert_source_line(raw_text: str, model_output: dict, line_number: int, line: str) -> str:
    lines = raw_text.splitlines()
    lines.insert(line_number - 1, line)
    for mapping in model_output["mappings"]:
        mapping["source_line_numbers"] = [
            number + 1 if number >= line_number else number
            for number in mapping["source_line_numbers"]
        ]
    for coverage in model_output["line_coverage"]:
        if coverage["line_number"] >= line_number:
            coverage["line_number"] += 1
    return "\n".join(lines)


def parser_for(service: StrategyIdeaFlowService):
    parser = getattr(service, "parse_fixed_510880_strategy", None)
    assert callable(parser), "fixed 510880 strategy parsing entry point is missing"
    return parser


def assert_card020_concurrency_gate_released():
    from backend.services.llm_client import _PROCESS_SEMAPHORE

    acquired = 0
    while _PROCESS_SEMAPHORE.acquire(blocking=False):
        acquired += 1
    try:
        assert acquired == 2
    finally:
        for _ in range(acquired):
            _PROCESS_SEMAPHORE.release()


def test_fixed_strategy_parse_uses_real_llm_tool_and_accepts_complete_cited_mapping():
    from backend.services import strategy_idea_flow

    raw_text, model_output = build_input(extra_lines=["Candidate supplied as a complete strategy."])
    model_output["line_coverage"][-1]["classification"] = "context"
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "ready_for_confirmation"
    assert result["fields"] == EXPECTED_FIELDS
    assert len(result["source_mappings"]) == len(EXPECTED_FIELDS)
    assert len(client.calls) == 1
    assert client.calls[0]["tools"][0]["name"] == "submit_510880_strategy_mapping"
    assert client.calls[0]["tool_choice"] == {
        "type": "tool", "name": "submit_510880_strategy_mapping"
    }
    assert client.calls[0]["timeout"].connect <= 5.0
    assert client.calls[0]["timeout"].read == strategy_idea_flow.CARD020_STREAM_WALL_SECONDS
    assert client.calls[0]["max_tokens"] == 8192
    assert result["call_diagnostic"]["attempt_count"] == 1
    assert result["call_diagnostic"]["retry_count"] == 0
    assert result["call_diagnostic"]["content_delta_count"] == 1
    assert result["call_diagnostic"]["message_stop_seen"] is True
    assert "CANONICAL REPRESENTATION" in client.calls[0]["system"]
    value_schema = client.calls[0]["tools"][0]["input_schema"]["properties"]["mappings"]["items"]["properties"]["value"]
    assert set(value_schema["enum"]) == set(EXPECTED_FIELDS.values())


def test_fixed_strategy_parse_marks_an_omitted_markdown_table_separator_as_context():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 32, "|---|---|")
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "ready_for_confirmation"
    assert result["deterministic_format_lines"] == [32]
    assert {item["line_number"]: item["classification"] for item in result["line_coverage"]}[32] == "context"
    assert len(result["line_coverage"]) == len(raw_text.splitlines())


@pytest.mark.parametrize("separator", [
    "| :--- | ---: |",
    ":---|---:",
    "|:---:|:----:|",
    "|---|",
])
def test_fixed_strategy_parse_recognizes_markdown_separator_variants(separator):
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, separator)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "ready_for_confirmation"
    assert result["deterministic_format_lines"] == [2]
    assert {item["line_number"]: item["classification"] for item in result["line_coverage"]}[2] == "context"


def test_fixed_strategy_parse_keeps_model_supplied_context_for_separator():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    model_output["line_coverage"].append({"line_number": 2, "classification": "context"})

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "ready_for_confirmation"
    assert result["deterministic_format_lines"] == []
    assert sum(item["line_number"] == 2 for item in result["line_coverage"]) == 1
    assert {item["line_number"]: item["classification"] for item in result["line_coverage"]}[2] == "context"


def test_fixed_strategy_parse_does_not_claim_invalid_model_coverage_as_program_added():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    model_output["line_coverage"].append({"line_number": 2, "classification": ["context"]})

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "blocked"
    assert result["deterministic_format_lines"] == []
    assert any("逐行覆盖包含无效行号或类别" in reason for reason in result["blocking_reasons"])


@pytest.mark.parametrize("classification", ["mapped_rule", "unsupported", "ambiguous", "contradiction", "unmapped"])
def test_fixed_strategy_parse_blocks_non_context_separator_classification(classification):
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    model_output["line_coverage"].append({"line_number": 2, "classification": classification})

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "blocked"
    assert result["deterministic_format_lines"] == []
    assert any("Markdown 表格分隔行，只能标为 context" in reason for reason in result["blocking_reasons"])


@pytest.mark.parametrize("lookalike", [
    "|--|---|",
    "|---|ordinary|",
    "ordinary | --- |",
    "---",
    "|:--:|---|",
])
def test_fixed_strategy_parse_does_not_autofill_separator_lookalikes(lookalike):
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, lookalike)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "blocked"
    assert result["deterministic_format_lines"] == []
    assert 2 not in {item["line_number"] for item in result["line_coverage"]}
    assert any("恰好覆盖每一条非空原文行" in reason for reason in result["blocking_reasons"])


def test_fixed_strategy_parse_still_blocks_missing_real_text_beside_separator():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    raw_text = insert_source_line(raw_text, model_output, 3, "Unmapped executable behavior")

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    coverage = {item["line_number"]: item["classification"] for item in result["line_coverage"]}
    assert result["status"] == "blocked"
    assert result["deterministic_format_lines"] == [2]
    assert coverage[2] == "context"
    assert 3 not in coverage
    assert any("恰好覆盖每一条非空原文行" in reason for reason in result["blocking_reasons"])


def test_fixed_strategy_parse_blocks_mapping_citation_to_separator():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    first_mapping = model_output["mappings"][0]
    first_mapping["source_line_numbers"].append(2)
    first_mapping["source_quotes"].append("---")
    model_output["line_coverage"].append({"line_number": 2, "classification": "mapped_rule"})

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "blocked"
    assert result["deterministic_format_lines"] == []
    assert first_mapping["field"] in result["blocking_fields"]
    assert any("不能作为规则来源" in reason for reason in result["blocking_reasons"])


def test_fixed_strategy_parse_blocks_duplicate_separator_coverage():
    raw_text, model_output = build_input()
    raw_text = insert_source_line(raw_text, model_output, 2, "|---|---|")
    model_output["line_coverage"].extend([
        {"line_number": 2, "classification": "context"},
        {"line_number": 2, "classification": "context"},
    ])

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=ToolUseClient(model_output))

    assert result["status"] == "blocked"
    assert any("逐行覆盖存在重复行" in reason for reason in result["blocking_reasons"])
    assert result["deterministic_format_lines"] == []


def test_fixed_strategy_parse_uses_complete_sdk_stream_before_validation():
    from types import SimpleNamespace

    raw_text, model_output = build_input()
    calls = []

    class CompletedStream:
        response = SimpleNamespace(status_code=200)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def __iter__(self):
            return iter([
                SimpleNamespace(type="message_start"),
                SimpleNamespace(type="ping"),
                SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="tool_use")),
                SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta")),
                SimpleNamespace(type="content_block_stop"),
                SimpleNamespace(type="message_delta"),
                SimpleNamespace(type="message_stop"),
            ])

        def get_final_message(self):
            return SimpleNamespace(
                id="synthetic-card020-stream",
                model="synthetic-test-model",
                stop_reason="tool_use",
                content=[SimpleNamespace(
                    type="tool_use",
                    name="submit_510880_strategy_mapping",
                    input=model_output,
                )],
            )

        def close(self):
            return None

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            return CompletedStream()

    client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "ready_for_confirmation"
    assert result["fields"] == EXPECTED_FIELDS
    assert len(calls) == 1
    assert calls[0]["tools"][0]["name"] == "submit_510880_strategy_mapping"
    assert calls[0]["tool_choice"] == {
        "type": "tool", "name": "submit_510880_strategy_mapping"
    }
    assert calls[0]["messages"][0]["content"] == "\n".join(
        f"[L{line_number:04d}] {line}"
        for line_number, line in enumerate(raw_text.splitlines(), start=1)
    )


def test_fixed_strategy_parse_blocks_stream_without_message_stop():
    from types import SimpleNamespace

    raw_text, _ = build_input()
    calls = []
    final_message_calls = []

    class IncompleteStream:
        response = SimpleNamespace(status_code=200)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def __iter__(self):
            return iter([SimpleNamespace(type="message_start"), SimpleNamespace(type="ping")])

        def get_final_message(self):
            final_message_calls.append(True)
            raise AssertionError("an unfinished stream cannot yield a final message")

        def close(self):
            return None

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            return IncompleteStream()

    client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert any("message_stop" in reason for reason in result["blocking_reasons"])
    assert result["call_diagnostic"]["message_stop_seen"] is False
    assert result["call_diagnostic"]["content_delta_count"] == 0
    assert len(calls) == 1
    assert final_message_calls == []


def test_fixed_strategy_parse_stops_waiting_for_first_stream_event(monkeypatch):
    import threading
    import time
    from types import SimpleNamespace

    from backend.services import strategy_idea_flow

    monkeypatch.setattr(strategy_idea_flow, "CARD020_STREAM_WALL_SECONDS", 0.05)
    raw_text, _ = build_input()
    calls = []

    class WaitingStream:
        response = SimpleNamespace(status_code=200)

        def __init__(self):
            self.closed = threading.Event()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def __iter__(self):
            self.closed.wait(1)
            return iter(())

        def close(self):
            self.closed.set()

    streams = []

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            stream = WaitingStream()
            streams.append(stream)
            return stream

    client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )

    started = time.perf_counter()
    try:
        parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)
    except RuntimeError as exc:
        assert str(exc) == "card020_stream_timeout"
        assert exc.call_diagnostic["timeout"] is True
        assert exc.call_diagnostic["attempt_count"] == 1
        assert exc.call_diagnostic["retry_count"] == 0
        assert exc.call_diagnostic["message_stop_seen"] is False
    else:
        raise AssertionError("a first-event stall must stop at the Card020 wall deadline")

    assert len(calls) == 1
    assert streams[0].closed.is_set()
    assert time.perf_counter() - started < 0.5
    assert_card020_concurrency_gate_released()


def test_fixed_strategy_parse_ignores_pings_until_wall_deadline(monkeypatch):
    import threading
    import time
    from types import SimpleNamespace

    from backend.services import strategy_idea_flow

    monkeypatch.setattr(strategy_idea_flow, "CARD020_STREAM_WALL_SECONDS", 0.05)
    raw_text, _ = build_input()
    calls = []

    class PingStream:
        response = SimpleNamespace(status_code=200)

        def __init__(self):
            self.closed = threading.Event()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def __iter__(self):
            while not self.closed.is_set():
                yield SimpleNamespace(type="ping")
                self.closed.wait(0.005)

        def close(self):
            self.closed.set()

    streams = []

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            stream = PingStream()
            streams.append(stream)
            return stream

    client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )

    started = time.perf_counter()
    try:
        parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)
    except RuntimeError as exc:
        assert exc.call_diagnostic["timeout"] is True
        assert exc.call_diagnostic["content_delta_count"] == 0
        assert exc.call_diagnostic["message_stop_seen"] is False
    else:
        raise AssertionError("provider pings cannot extend the total Card020 deadline")

    assert len(calls) == 1
    assert streams[0].closed.is_set()
    assert time.perf_counter() - started < 0.5
    assert_card020_concurrency_gate_released()


def test_fixed_strategy_parse_records_midstream_disconnect_without_retry():
    from types import SimpleNamespace

    raw_text, _ = build_input()
    calls = []
    closed = []

    class DisconnectedStream:
        response = SimpleNamespace(status_code=200)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def __iter__(self):
            yield SimpleNamespace(type="message_start")
            raise ConnectionError("private provider response")

        def close(self):
            closed.append(True)

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            return DisconnectedStream()

    client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )

    try:
        parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)
    except RuntimeError as exc:
        assert str(exc) == "card020_stream_failed"
        diagnostic = exc.call_diagnostic
        assert diagnostic["attempt_count"] == 1
        assert diagnostic["retry_count"] == 0
        assert diagnostic["attempts"][0]["status"] == "error"
        assert diagnostic["response_received"] is True
        assert "private provider response" not in str(exc)
    else:
        raise AssertionError("a disconnected stream must not be accepted")

    assert len(calls) == 1
    assert closed == [True]
    assert_card020_concurrency_gate_released()


def test_fixed_strategy_parse_blocks_missing_abnormal_and_max_token_stop_reasons():
    raw_text, model_output = build_input()

    for stop_reason in (None, "max_tokens", "end_turn", "stop_sequence", "refusal", "other"):
        client = ToolUseClient(model_output, stop_reason=stop_reason)

        result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

        assert result["status"] == "blocked", stop_reason
        assert result["blocking_reasons"], stop_reason
        assert result["source_sha256"] == hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper()


def test_fixed_strategy_parse_blocks_multiple_tool_results():
    raw_text, model_output = build_input()
    client = ToolUseClient(model_output, extra_tool_calls=1)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"]


def test_fixed_strategy_parse_labels_physical_lines_and_keeps_multiple_citations_in_one_mapping():
    extra_line = "strategy_id = 510880-vol-budget-v1"
    raw_text, model_output = build_input(
        extra_lines=[extra_line],
        blank_lines_before={1, 4},
    )
    model_output["line_coverage"][-1]["classification"] = "mapped_rule"
    strategy_mapping = next(item for item in model_output["mappings"] if item["field"] == "strategy_id")
    strategy_mapping["source_line_numbers"].append(len(raw_text.splitlines()))
    strategy_mapping["source_quotes"].append(extra_line)
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "ready_for_confirmation"
    strategy_mappings = [item for item in result["source_mappings"] if item["field"] == "strategy_id"]
    assert len(strategy_mappings) == 1
    assert len(strategy_mappings[0]["source_line_numbers"]) == 2
    expected_prompt = "\n".join(
        f"[L{line_number:04d}] {line}"
        for line_number, line in enumerate(raw_text.splitlines(), start=1)
    )
    assert client.calls[0]["messages"][0]["content"] == expected_prompt
    assert "[L0002] " in expected_prompt
    assert "original one-based physical line number" in client.calls[0]["system"]
    assert "one mapping object per field" in client.calls[0]["system"]


def test_fixed_strategy_parse_blocks_duplicate_field_mapping_with_blank_lines():
    raw_text, model_output = build_input(blank_lines_before={1, 4})
    model_output["mappings"].append(dict(model_output["mappings"][0]))
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert "strategy_id" in result["blocking_fields"]
    assert any("重复映射" in reason for reason in result["blocking_reasons"])


def test_fixed_strategy_parse_blocks_missing_required_field():
    fields = dict(EXPECTED_FIELDS)
    fields.pop("volatility_lookback")
    raw_text, model_output = build_input(fields, blank_lines_before={1, 4})
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert "volatility_lookback" in result["blocking_fields"]


def test_fixed_strategy_parse_blocks_unsupported_clause():
    raw_text, model_output = build_input(extra_lines=["Use leverage up to 150% when volatility rises."])
    model_output["line_coverage"][-1]["classification"] = "unsupported"
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"]


def test_fixed_strategy_parse_blocks_conflicting_value_even_with_valid_quote():
    raw_text, model_output = build_input(blank_lines_before={1, 4})
    field_index = next(i for i, item in enumerate(model_output["mappings"]) if item["field"] == "annualized_volatility_target")
    model_output["mappings"][field_index]["value"] = "0.12"
    model_output["mappings"][field_index]["source_quotes"] = ["annualized_volatility_target = 0.12"]
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert "annualized_volatility_target" in result["blocking_fields"]


def test_fixed_strategy_parse_blocks_quote_not_found_at_cited_line():
    raw_text, model_output = build_input(blank_lines_before={1, 4})
    model_output["mappings"][0]["source_quotes"] = ["invented source text"]
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"]


def test_fixed_strategy_parse_blocks_quote_cited_to_wrong_physical_line():
    raw_text, model_output = build_input(blank_lines_before={1})
    symbol_mapping = next(item for item in model_output["mappings"] if item["field"] == "symbol")
    symbol_mapping["source_line_numbers"] = [1]
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert any("引文不在所标注的原文行中" in reason for reason in result["blocking_reasons"])


def test_fixed_strategy_parse_blocks_incomplete_source_line_coverage():
    raw_text, model_output = build_input(blank_lines_before={1, 4})
    model_output["line_coverage"].pop()
    client = ToolUseClient(model_output)

    result = parser_for(StrategyIdeaFlowService())(raw_text, llm_client=client)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"]


def test_fixed_strategy_parse_does_not_fallback_when_llm_call_fails():
    class FailingClient:
        model = "synthetic-test-model"

        class Messages:
            def stream(self, **_kwargs):
                raise RuntimeError("provider unavailable")

        from types import SimpleNamespace

        client = SimpleNamespace(messages=Messages())

        def create_message(self, **_kwargs):
            raise RuntimeError("provider unavailable")

    raw_text, _ = build_input()

    try:
        parser_for(StrategyIdeaFlowService())(raw_text, llm_client=FailingClient())
    except RuntimeError as exc:
        assert str(exc) == "card020_stream_failed"
        assert exc.call_diagnostic["attempt_count"] == 1
        assert exc.call_diagnostic["retry_count"] == 0
    else:
        raise AssertionError("LLM failure was silently replaced by a fallback parse")
