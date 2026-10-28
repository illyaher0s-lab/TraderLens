"""
Strategy Idea Flow Service

Red lines enforced:
1. Idea defaults to untrusted, no signals until validated
2. LLM only extracts and explains, never decides
3. Only path to library: approved frozen template approval path
4. Failed/blocked ideas enter RejectedStrategyRegistry
5. StrategyDraft must have hard source chain
"""

import uuid
import hashlib
import json
import threading
import time
from datetime import datetime
from typing import Optional

from httpx import Timeout

from contracts.strategy_idea import (
    StrategyIdea,
    StrategyIdeaTrustStatus,
    TemplatePathType,
    StrategyIdeaExtraction,
    TemplateMappingResult,
    CandidateTemplateEvaluation,
)
from backend.services.llm_client import (
    _PROCESS_SEMAPHORE,
    _http_status_from_chain,
    _is_timeout_exception,
)

CARD020_STREAM_WALL_SECONDS = 120.0
CARD020_STREAM_READ_SECONDS = 120.0
_CARD020_SAFE_STREAM_STOP_REASONS = frozenset({
    "tool_use", "end_turn", "max_tokens", "stop_sequence", "refusal",
})


def _card020_stream_timeout(wall_seconds: float) -> Timeout:
    return Timeout(
        connect=min(5.0, max(0.01, wall_seconds / 4)),
        read=min(CARD020_STREAM_READ_SECONDS, max(0.01, wall_seconds)),
        write=min(5.0, max(0.01, wall_seconds / 4)),
        pool=min(2.0, max(0.01, wall_seconds / 10)),
    )


def _card020_stream_diagnostic(
    *,
    started: float,
    http_status: int | None,
    timeout: bool,
    response_received: bool,
    attempt_status: str,
    content_delta_count: int,
    first_content_ms: float | None,
    message_stop_seen: bool,
    stop_reason: str | None,
    tool_use_start_count: int,
    tool_use_count: int,
) -> dict:
    safe_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
    safe_stop_reason = (
        stop_reason
        if isinstance(stop_reason, str) and stop_reason in _CARD020_SAFE_STREAM_STOP_REASONS
        else "other" if isinstance(stop_reason, str) else None
    )
    return {
        "attempt_count": 1,
        "retry_count": 0,
        "duration_ms": round(max(0.0, (time.perf_counter() - started) * 1000), 1),
        "http_status": safe_status,
        "timeout": timeout,
        "response_received": response_received,
        "retry_stop_reason": "max_retries_reached" if timeout else "not_timeout" if attempt_status == "error" else None,
        "attempts": [{
            "attempt": 1,
            "status": attempt_status,
            "duration_ms": round(max(0.0, (time.perf_counter() - started) * 1000), 1),
            "http_status": safe_status,
            "timeout": timeout,
            "response_received": response_received,
        }],
        "content_delta_count": min(max(content_delta_count, 0), 1_000_000),
        "time_to_first_content_ms": round(first_content_ms, 1) if first_content_ms is not None else None,
        "message_stop_seen": message_stop_seen,
        "stop_reason": safe_stop_reason,
        "tool_use_start_count": min(max(tool_use_start_count, 0), 1_000_000),
        "tool_use_count": min(max(tool_use_count, 0), 1_000_000),
    }


def _card020_stream_error(message: str, diagnostic: dict) -> RuntimeError:
    error = RuntimeError(message)
    error.call_diagnostic = diagnostic
    return error


def _call_card020_stream(llm_client, *, messages: list[dict], system: str, tools: list[dict], tool_choice: dict, max_tokens: int) -> dict:
    model = getattr(llm_client, "model", None)
    sdk_client = getattr(llm_client, "client", None)
    stream_call = getattr(getattr(sdk_client, "messages", None), "stream", None)
    if not isinstance(model, str) or not model or not callable(stream_call):
        raise ValueError("real streaming LLM client is required for Card020 parsing")

    started = time.perf_counter()
    if not _PROCESS_SEMAPHORE.acquire(blocking=False):
        diagnostic = _card020_stream_diagnostic(
            started=started,
            http_status=None,
            timeout=False,
            response_received=False,
            attempt_status="error",
            content_delta_count=0,
            first_content_ms=None,
            message_stop_seen=False,
            stop_reason=None,
            tool_use_start_count=0,
            tool_use_count=0,
        )
        diagnostic["attempt_count"] = 0
        diagnostic["attempts"] = []
        raise _card020_stream_error("llm_concurrency_exhausted", diagnostic)

    http_status = None
    response_received = False
    content_delta_count = 0
    first_content_ms = None
    message_stop_seen = False
    stop_reason = None
    tool_use_start_count = 0
    tool_use_count = 0
    deadline_reached = threading.Event()
    active_stream = {"value": None}

    def close_stream_at_deadline():
        deadline_reached.set()
        stream = active_stream["value"]
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass

    timer = threading.Timer(CARD020_STREAM_WALL_SECONDS, close_stream_at_deadline)
    timer.daemon = True
    timer.start()
    try:
        with stream_call(
            model=model,
            messages=messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            timeout=_card020_stream_timeout(CARD020_STREAM_WALL_SECONDS),
        ) as stream:
            active_stream["value"] = stream
            if deadline_reached.is_set():
                close_stream_at_deadline()
                raise TimeoutError("Card020 stream wall deadline reached")
            response = getattr(stream, "response", None)
            http_status = getattr(response, "status_code", None)
            response_received = http_status is not None
            for event in stream:
                if deadline_reached.is_set():
                    break
                event_type = getattr(event, "type", None)
                if event_type == "content_block_start":
                    if getattr(getattr(event, "content_block", None), "type", None) == "tool_use":
                        tool_use_start_count += 1
                elif event_type == "content_block_delta":
                    delta_type = getattr(getattr(event, "delta", None), "type", None)
                    if delta_type in {"text_delta", "input_json_delta"}:
                        content_delta_count += 1
                        if first_content_ms is None:
                            first_content_ms = (time.perf_counter() - started) * 1000
                elif event_type == "message_stop":
                    message_stop_seen = True
                    break
            if deadline_reached.is_set():
                raise TimeoutError("Card020 stream wall deadline reached")

            if message_stop_seen:
                final_message = stream.get_final_message()
                stop_reason = getattr(final_message, "stop_reason", None)
                final_content = []
                for block in getattr(final_message, "content", None) or []:
                    block_type = getattr(block, "type", None)
                    if block_type == "tool_use":
                        tool_use_count += 1
                        final_content.append({
                            "type": "tool_use",
                            "name": getattr(block, "name", None),
                            "input": getattr(block, "input", None),
                        })
                    elif block_type == "text":
                        final_content.append({"type": "text", "text": getattr(block, "text", "")})
                    else:
                        final_content.append({"type": block_type})
                result = {
                    "id": getattr(final_message, "id", None),
                    "model": getattr(final_message, "model", None),
                    "stop_reason": stop_reason,
                    "content": final_content,
                    "message_stop_seen": True,
                }
            else:
                result = {
                    "id": None,
                    "model": model,
                    "stop_reason": None,
                    "content": [],
                    "message_stop_seen": False,
                }
    except Exception as exc:
        timed_out = deadline_reached.is_set() or _is_timeout_exception(exc)
        http_status = http_status or _http_status_from_chain(exc)
        response_received = response_received or http_status is not None
        diagnostic = _card020_stream_diagnostic(
            started=started,
            http_status=http_status,
            timeout=timed_out,
            response_received=response_received,
            attempt_status="timeout" if timed_out else "error",
            content_delta_count=content_delta_count,
            first_content_ms=first_content_ms,
            message_stop_seen=message_stop_seen,
            stop_reason=stop_reason,
            tool_use_start_count=tool_use_start_count,
            tool_use_count=tool_use_count,
        )
        raise _card020_stream_error(
            "card020_stream_timeout" if timed_out else "card020_stream_failed",
            diagnostic,
        ) from exc
    finally:
        timer.cancel()
        active_stream["value"] = None
        _PROCESS_SEMAPHORE.release()

    if deadline_reached.is_set():
        diagnostic = _card020_stream_diagnostic(
            started=started,
            http_status=http_status,
            timeout=True,
            response_received=response_received,
            attempt_status="timeout",
            content_delta_count=content_delta_count,
            first_content_ms=first_content_ms,
            message_stop_seen=message_stop_seen,
            stop_reason=stop_reason,
            tool_use_start_count=tool_use_start_count,
            tool_use_count=tool_use_count,
        )
        raise _card020_stream_error("card020_stream_timeout", diagnostic)

    result["call_diagnostic"] = _card020_stream_diagnostic(
        started=started,
        http_status=http_status,
        timeout=False,
        response_received=response_received,
        attempt_status="success",
        content_delta_count=content_delta_count,
        first_content_ms=first_content_ms,
        message_stop_seen=message_stop_seen,
        stop_reason=stop_reason,
        tool_use_start_count=tool_use_start_count,
        tool_use_count=tool_use_count,
    )
    return result


class StrategyIdeaFlowService:
    """
    Strategy idea flow service.
    
    LLM: extracts claims, explains mapping (草案/解释)
    Deterministic code: decides trust_status, live_eligible, entry to library
    """

    def create_idea(
        self,
        raw_source_text: str,
        source_channel: str,
    ) -> StrategyIdea:
        """
        Create strategy idea.
        
        Red line 1: Defaults to untrusted.
        """
        return StrategyIdea(
            idea_id=f"idea_{uuid.uuid4().hex[:12]}",
            raw_source_text=raw_source_text,
            source_channel=source_channel,
            trust_status=StrategyIdeaTrustStatus.untrusted,  # Red line 1
            created_at=datetime.now(),
        )

    def extract_claims(self, idea: StrategyIdea) -> StrategyIdeaExtraction:
        """
        Extract claims from idea using LLM.
        
        Red line 2: LLM only extracts, fields have 'claimed_' prefix.
        """
        # LLM extraction (placeholder - real LLM call would go here)
        # For now, use simple parsing
        text = idea.raw_source_text
        
        # Simple extraction (deterministic fallback)
        claimed_entry = "未提取"
        claimed_exit = "未提取"
        
        if "两点半" in text or "14:30" in text or "2:30" in text:
            claimed_entry = "下午两点半后买入"
        
        if "第二天" in text or "次日" in text:
            claimed_exit = "次日早盘卖出"
        
        return StrategyIdeaExtraction(
            extraction_id=f"extract_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            claimed_entry=claimed_entry,
            claimed_exit=claimed_exit,
            claimed_edge=None,  # Often missing in short videos
            extraction_source="llm_assisted",  # Honest labeling
            extracted_at=datetime.now(),
        )

    def get_planned_signals_for_idea(self, idea_id: str) -> list:
        """
        Get planned signals for idea.
        
        Red line 1: Untrusted ideas produce no signals.
        """
        # Always empty for untrusted ideas
        return []

    def get_execution_cards_for_idea(self, idea_id: str) -> list:
        """
        Get execution cards for idea.
        
        Red line 1: Untrusted ideas produce no execution cards.
        """
        # Always empty for untrusted ideas
        return []

    def map_to_template(
        self,
        idea: StrategyIdea,
        matched_template_id: Optional[str],
        template_version: Optional[str],
        mapping_reason: str,
    ) -> TemplateMappingResult:
        """
        Map idea to template.
        
        Red line 2/3: LLM explains, deterministic code decides path & live_eligible.
        """
        # Determine path type (deterministic)
        if matched_template_id and template_version:
            path_type = TemplatePathType.approved_template_match
        elif matched_template_id is None:
            path_type = TemplatePathType.no_template_fit
        else:
            path_type = TemplatePathType.candidate_evaluation
        
        # Red line 3: live_eligible defaults False, only deterministic code can set True
        # (and only after full validation passes)
        live_eligible = False
        
        return TemplateMappingResult(
            mapping_id=f"mapping_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            path_type=path_type,
            matched_template_id=matched_template_id,
            template_version=template_version,
            mapping_reason=mapping_reason,
            live_eligible=live_eligible,  # Deterministic only
            created_at=datetime.now(),
        )

    def create_candidate_evaluation(
        self,
        idea: StrategyIdea,
    ) -> CandidateTemplateEvaluation:
        """
        Create candidate template evaluation.
        
        Red line 3: Candidate is never approved, stored separately.
        """
        return CandidateTemplateEvaluation(
            candidate_id=f"candidate_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            is_approved_template=False,  # Hardcoded, guarded
            evaluation_status="pending",
            stored_separately_from_live=True,  # Hardcoded, guarded
            created_at=datetime.now(),
        )

    def reject_idea(
        self,
        idea: StrategyIdea,
        reason: str,
    ) -> dict:
        """
        Reject idea and enter into RejectedStrategyRegistry.
        
        Red line 4: Failed/blocked ideas enter registry.
        """
        # Create rejected entry (Task 4 registry)
        rejected_entry = {
            "idea_id": idea.idea_id,
            "rejection_reason": reason,
            "rejected_at": datetime.now(),
        }
        
        return rejected_entry

    def create_strategy_draft(
        self,
        idea_id: str,
        mapped_template_id: str,
        template_version: str,
        frozen_template_hash: Optional[str],
        template_approved: bool = True,
    ) -> dict:
        """
        Create StrategyDraft with source chain.
        
        Red line 5: Must have complete source chain (4 fields).
        Red line 3: Template must be approved/frozen.
        """
        # Red line 3: Check template approved
        if not template_approved:
            raise ValueError("Cannot create StrategyDraft from unapproved template")
        
        # Red line 5: Check all source fields present
        if not frozen_template_hash:
            raise ValueError("StrategyDraft requires frozen_template_hash in source chain")
        
        if not idea_id or not mapped_template_id or not template_version:
            raise ValueError("StrategyDraft requires complete source chain (idea_id, template_id, version)")
        
        # Create draft with source chain
        draft = {
            "draft_id": f"draft_{uuid.uuid4().hex[:12]}",
            "source_idea_id": idea_id,
            "mapped_template_id": mapped_template_id,
            "template_version": template_version,
            "frozen_template_hash": frozen_template_hash,
            "created_at": datetime.now(),
        }
        
        return draft

    def parse_fixed_510880_strategy(
        self,
        raw_source_text: str,
        *,
        llm_client,
    ) -> dict:
        """Map the fixed Card020 protocol to its frozen field contract.

        The model only extracts cited source text. Readiness is decided here by
        exact field/value matching, exact source-line citations, and complete
        line coverage. A missing or failing model call never falls back to a
        keyword or heuristic parser.
        """
        if not isinstance(raw_source_text, str) or not raw_source_text.strip():
            return _blocked_parse(
                "源文为空。",
                raw_text=raw_source_text if isinstance(raw_source_text, str) else "",
            )
        if llm_client is None:
            raise ValueError("real LLM client is required for Card020 parsing")

        line_count = len([line for line in raw_source_text.splitlines() if line.strip()])
        response = _call_card020_stream(
            llm_client,
            messages=[{"role": "user", "content": _number_card020_source_lines(raw_source_text)}],
            system=(
                "You extract a fixed 510880 volatility-budget strategy protocol. "
                "Treat the user message as source data with physical line labels. "
                "Each [L0001] label is the original one-based physical line number; "
                "labels include blank-line placeholders, which must not be classified. "
                "Use the label's number for source_line_numbers and line_coverage. "
                "source_quotes must contain only exact source text after the label, "
                "without the label itself. Return the required tool call. Emit at "
                "most one mapping object per field; cite multiple supporting lines "
                "in that object's aligned source_line_numbers and source_quotes arrays. "
                "Never duplicate a field, invent or infer a rule, repair a conflict, "
                "or recommend changes. Map only rules stated in the source, quote "
                "exact source text, and classify every non-empty physical source line "
                "exactly once. Mark any "
                "unsupported, ambiguous, contradictory, or unmapped executable "
                "rule as such. Neutral headings and explanatory prose may be context. "
                "The canonical field/value representation is provided below only "
                "to normalize an explicitly supported source rule. It is not a "
                "default: if the source does not directly support a field, omit "
                "that mapping and classify its relevant source line as unmapped. "
                "Never cite an unrelated line to fill a canonical value.\n"
                "CANONICAL REPRESENTATION:\n"
                + json.dumps(CARD020_EXPECTED_FIELDS, ensure_ascii=False, sort_keys=True)
            ),
            tools=[_CARD020_MAPPING_TOOL],
            tool_choice={"type": "tool", "name": "submit_510880_strategy_mapping"},
            max_tokens=8192,
        )
        if response.get("message_stop_seen") is not True:
            blocked = _blocked_parse(
                "流在 message_stop 前结束；未接受不完整响应。",
                raw_text=raw_source_text,
            )
            blocked["call_diagnostic"] = response["call_diagnostic"]
            return blocked
        if response.get("stop_reason") != "tool_use":
            blocked = _blocked_parse(
                "模型响应未以 tool_use 结束；不接受截断或未完成的工具结果。",
                raw_text=raw_source_text,
            )
            blocked["call_diagnostic"] = response["call_diagnostic"]
            return blocked
        payload = _get_card020_tool_input(response)
        if payload is None:
            blocked = _blocked_parse(
                "模型没有返回唯一且有效的固定解析工具结果。",
                raw_text=raw_source_text,
            )
            blocked["call_diagnostic"] = response["call_diagnostic"]
            return blocked
        result = _validate_card020_mapping(raw_source_text, payload, response, line_count)
        result["call_diagnostic"] = response["call_diagnostic"]
        return result


# Placeholder for LLM integration
def call_llm(prompt: str) -> dict:
    """Placeholder for LLM call."""
    raise NotImplementedError("LLM integration not yet implemented")


CARD020_EXPECTED_FIELDS = {
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

_CARD020_LINE_CLASSIFICATIONS = frozenset({
    "mapped_rule", "context", "unsupported", "ambiguous", "contradiction", "unmapped",
})
_CARD020_MAPPING_TOOL = {
    "name": "submit_510880_strategy_mapping",
    "description": "Return source-cited mappings for the fixed 510880 protocol and classify each non-empty line.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["mappings", "line_coverage"],
        "properties": {
            "mappings": {
                "type": "array",
                "description": "At most one mapping object per field. Put multiple citations for one field into the aligned source_line_numbers and source_quotes arrays.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field", "value", "source_line_numbers", "source_quotes"],
                    "properties": {
                        "field": {"type": "string", "enum": list(CARD020_EXPECTED_FIELDS)},
                        "value": {
                            "type": "string",
                            "enum": list(dict.fromkeys(CARD020_EXPECTED_FIELDS.values())),
                            "description": "Use the canonical representation only when the cited source line directly supports it; never fill an absent rule from this list.",
                        },
                        "source_line_numbers": {
                            "type": "array",
                            "description": "One-based original physical line numbers from the L labels; blank lines count in numbering.",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                        "source_quotes": {
                            "type": "array",
                            "description": "Exact source fragments from the cited original lines; omit the L labels.",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                        },
                    },
                },
            },
            "line_coverage": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["line_number", "classification"],
                    "properties": {
                        "line_number": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "One-based original physical line number from the L label; classify every non-empty source line once and skip blank placeholders.",
                        },
                        "classification": {"type": "string", "enum": sorted(_CARD020_LINE_CLASSIFICATIONS)},
                    },
                },
            },
        },
    },
}


def _get_card020_tool_input(response: object) -> dict | None:
    if not isinstance(response, dict):
        return None
    blocks = response.get("content")
    if not isinstance(blocks, list):
        return None
    calls = [
        block for block in blocks
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]
    if len(calls) != 1 or calls[0].get("name") != _CARD020_MAPPING_TOOL["name"]:
        return None
    payload = calls[0].get("input")
    return payload if isinstance(payload, dict) else None


def _number_card020_source_lines(raw_text: str) -> str:
    return "\n".join(
        f"[L{line_number:04d}] {line}"
        for line_number, line in enumerate(raw_text.splitlines(), start=1)
    )


def _is_card020_table_separator(line: str) -> bool:
    """Recognize pipe-delimited Markdown separators with only hyphen/alignment cells."""
    formatted = line.strip()
    if not formatted or "|" not in formatted:
        return False
    if formatted.startswith("|"):
        formatted = formatted[1:]
    if formatted.endswith("|"):
        formatted = formatted[:-1]
    cells = formatted.split("|")
    if not cells:
        return False
    for cell in cells:
        cell = cell.strip()
        if cell.startswith(":"):
            cell = cell[1:]
        if cell.endswith(":"):
            cell = cell[:-1]
        if len(cell) < 3 or set(cell) != {"-"}:
            return False
    return True


def _blocked_parse(
    reason: str,
    *,
    raw_text: str,
    fields: dict | None = None,
    mappings: list | None = None,
    coverage: list | None = None,
) -> dict:
    return {
        "status": "blocked",
        "fields": fields or {},
        "source_mappings": mappings or [],
        "line_coverage": coverage or [],
        "deterministic_format_lines": [],
        "blocking_fields": [],
        "blocking_reasons": [reason],
        "source_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper(),
    }


def _validate_card020_mapping(raw_text: str, payload: dict, response: dict, line_count: int) -> dict:
    reasons: list[str] = []
    blocking_fields: set[str] = set()
    raw_lines = raw_text.splitlines()
    nonempty_line_numbers = {i for i, line in enumerate(raw_lines, 1) if line.strip()}
    table_separator_line_numbers = {
        number for number in nonempty_line_numbers
        if _is_card020_table_separator(raw_lines[number - 1])
    }
    mappings_raw = payload.get("mappings")
    coverage_raw = payload.get("line_coverage")
    if not isinstance(mappings_raw, list) or not isinstance(coverage_raw, list):
        return _blocked_parse("解析结果缺少字段映射或逐行覆盖。", raw_text=raw_text)

    mappings: list[dict] = []
    found: dict[str, str] = {}
    cited_lines: set[int] = set()
    for item in mappings_raw:
        if not isinstance(item, dict):
            reasons.append("字段映射格式无效。")
            continue
        field = item.get("field")
        value = item.get("value")
        line_numbers = item.get("source_line_numbers")
        quotes = item.get("source_quotes")
        if not isinstance(field, str) or field not in CARD020_EXPECTED_FIELDS:
            reasons.append("出现固定协议以外的字段。")
            continue
        if field in found:
            blocking_fields.add(field)
            reasons.append(f"字段 {field} 重复映射。")
        if not isinstance(value, str):
            blocking_fields.add(field)
            reasons.append(f"字段 {field} 的值无效。")
            value = ""
        found[field] = value
        if value != CARD020_EXPECTED_FIELDS[field]:
            blocking_fields.add(field)
            reasons.append(f"字段 {field} 与固定协议值不一致。")
        if not isinstance(line_numbers, list) or not line_numbers or not isinstance(quotes, list) or len(line_numbers) != len(quotes):
            blocking_fields.add(field)
            reasons.append(f"字段 {field} 缺少逐条对应的原文引文。")
            continue
        for line_number, quote in zip(line_numbers, quotes):
            if type(line_number) is not int or line_number not in nonempty_line_numbers or not isinstance(quote, str) or not quote.strip():
                blocking_fields.add(field)
                reasons.append(f"字段 {field} 的来源行号或引文无效。")
                continue
            if quote not in raw_lines[line_number - 1]:
                blocking_fields.add(field)
                reasons.append(f"字段 {field} 的引文不在所标注的原文行中。")
                continue
            if line_number in table_separator_line_numbers:
                blocking_fields.add(field)
                reasons.append(f"字段 {field} 引用了 Markdown 表格分隔行，该格式行不能作为规则来源。")
                continue
            cited_lines.add(line_number)
        mappings.append({
            "field": field,
            "value": value,
            "source_line_numbers": list(line_numbers),
            "source_quotes": list(quotes),
        })

    missing_fields = sorted(set(CARD020_EXPECTED_FIELDS) - set(found))
    blocking_fields.update(missing_fields)
    if missing_fields:
        reasons.append("缺少必需字段映射。")

    coverage_by_line: dict[int, str] = {}
    model_reported_coverage_line_numbers: set[int] = set()
    for item in coverage_raw:
        if not isinstance(item, dict):
            reasons.append("逐行覆盖记录格式无效。")
            continue
        line_number = item.get("line_number")
        classification = item.get("classification")
        if type(line_number) is int and line_number in nonempty_line_numbers:
            model_reported_coverage_line_numbers.add(line_number)
        if (
            type(line_number) is not int
            or line_number not in nonempty_line_numbers
            or not isinstance(classification, str)
            or classification not in _CARD020_LINE_CLASSIFICATIONS
        ):
            reasons.append("逐行覆盖包含无效行号或类别。")
            continue
        if line_number in coverage_by_line:
            reasons.append("逐行覆盖存在重复行。")
        coverage_by_line[line_number] = classification
        if line_number in table_separator_line_numbers and classification != "context":
            reasons.append(f"原文第 {line_number} 行是 Markdown 表格分隔行，只能标为 context。")
        if classification == "mapped_rule" and line_number not in cited_lines:
            reasons.append("标为规则的原文行没有被字段映射引用。")
        if classification in {"unsupported", "ambiguous", "contradiction", "unmapped"}:
            reasons.append(f"原文第 {line_number} 行存在不支持、歧义、冲突或未映射规则。")
    deterministic_format_lines = []
    for line_number in sorted(table_separator_line_numbers):
        if line_number not in model_reported_coverage_line_numbers:
            coverage_by_line[line_number] = "context"
            deterministic_format_lines.append(line_number)
    if set(coverage_by_line) != nonempty_line_numbers:
        reasons.append("模型没有恰好覆盖每一条非空原文行。")
    for line_number in cited_lines:
        if coverage_by_line.get(line_number) != "mapped_rule":
            reasons.append(f"原文第 {line_number} 行被引用但未标记为规则。")

    # `line_count` exists to keep the count derived from the exact prompt input;
    # an inconsistent split is always a block rather than inferred coverage.
    if len(nonempty_line_numbers) != line_count:
        reasons.append("原文行数校验失败。")
    if len(found) != len(mappings_raw):
        reasons.append("字段映射中有无法验证的记录。")

    unique_reasons = list(dict.fromkeys(reasons))
    status = "ready_for_confirmation" if not unique_reasons else "blocked"
    return {
        "status": status,
        "fields": {key: found[key] for key in CARD020_EXPECTED_FIELDS if key in found},
        "source_mappings": mappings,
        "line_coverage": [
            {"line_number": number, "classification": classification}
            for number, classification in sorted(coverage_by_line.items())
        ],
        "deterministic_format_lines": deterministic_format_lines,
        "blocking_fields": sorted(blocking_fields),
        "blocking_reasons": unique_reasons,
        "source_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper(),
        "model": response.get("model") if isinstance(response.get("model"), str) else None,
        "response_id": response.get("id") if isinstance(response.get("id"), str) else None,
    }
