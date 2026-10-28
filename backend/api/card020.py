"""Card020 fixed 510880 strategy parsing, confirmation, and result routes."""

from __future__ import annotations

import hashlib
import math
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.services.card020_store import Card020Conflict, Card020Store
from backend.services.card020_preflight import prepare_card020_inputs
from backend.services.strategy_idea_flow import StrategyIdeaFlowService


STRATEGY_ID = "510880-vol-budget-v1"
PROTOCOL_SHA256 = "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = PROJECT_ROOT / "docs" / "510880-vol-budget-v1｜低频波动风险预算策略.md"
_RUN_LOCK = threading.Lock()


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_text: str = Field(min_length=1, max_length=50000)


class FreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parse_id: str = Field(min_length=1, max_length=128)
    preflight_id: str = Field(min_length=1, max_length=128)
    source_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    confirmed: bool = False


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    freeze_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)


def _read_protocol() -> tuple[str, str]:
    try:
        raw = PROTOCOL_PATH.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Card020 固定协议文件不可读取。") from exc
    actual = hashlib.sha256(raw).hexdigest().upper()
    if actual != PROTOCOL_SHA256:
        raise HTTPException(status_code=503, detail="Card020 固定协议哈希与修订3不一致。")
    return text, actual


def _normalize_line_endings(text: str) -> str:
    # Browser text controls normalize CRLF to LF. Preserve all other bytes/text.
    return text.replace("\r\n", "\n").replace("\r", "\n")


_CARD020_SAFE_ATTEMPT_STATUSES = frozenset({"timeout", "error", "success"})
_CARD020_SAFE_RETRY_STOP_REASONS = frozenset({
    "max_retries_reached",
    "not_timeout",
    "decision_loop_budget_exhausted",
    "decision_loop_budget_reserved",
})
_CARD020_SAFE_STOP_REASONS = frozenset({
    "tool_use", "end_turn", "max_tokens", "stop_sequence", "refusal",
})


def _safe_card020_call_diagnostic(exc: Exception) -> dict | None:
    raw = getattr(exc, "call_diagnostic", None)
    if not isinstance(raw, dict):
        return None

    def safe_integer(value, *, minimum: int, maximum: int) -> int | None:
        return value if type(value) is int and minimum <= value <= maximum else None

    def safe_duration(value) -> int | float | None:
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            return None
        return value

    def safe_http_status(value) -> int | None:
        return value if type(value) is int and 100 <= value <= 599 else None

    attempts = []
    raw_attempts = raw.get("attempts")
    if isinstance(raw_attempts, list):
        for item in raw_attempts[:3]:
            if not isinstance(item, dict):
                continue
            number = safe_integer(item.get("attempt"), minimum=1, maximum=3)
            status = item.get("status")
            if number is None or not isinstance(status, str) or status not in _CARD020_SAFE_ATTEMPT_STATUSES:
                continue
            attempts.append({
                "attempt": number,
                "status": status,
                "duration_ms": safe_duration(item.get("duration_ms")),
                "http_status": safe_http_status(item.get("http_status")),
                "timeout": item.get("timeout") if type(item.get("timeout")) is bool else status == "timeout",
                "response_received": item.get("response_received")
                if type(item.get("response_received")) is bool else False,
            })

    attempt_count = safe_integer(raw.get("attempt_count"), minimum=0, maximum=3)
    retry_count = safe_integer(raw.get("retry_count"), minimum=0, maximum=2)
    retry_stop_reason = raw.get("retry_stop_reason")
    safe_diagnostic = {
        "attempt_count": len(attempts) if attempt_count is None else attempt_count,
        "retry_count": 0 if retry_count is None else retry_count,
        "duration_ms": safe_duration(raw.get("duration_ms")),
        "http_status": safe_http_status(raw.get("http_status")),
        "timeout": raw.get("timeout") if type(raw.get("timeout")) is bool else False,
        "response_received": raw.get("response_received")
        if type(raw.get("response_received")) is bool else False,
        "retry_stop_reason": retry_stop_reason
        if isinstance(retry_stop_reason, str) and retry_stop_reason in _CARD020_SAFE_RETRY_STOP_REASONS else None,
        "attempts": attempts,
    }
    content_delta_count = safe_integer(raw.get("content_delta_count"), minimum=0, maximum=1_000_000)
    tool_use_start_count = safe_integer(raw.get("tool_use_start_count"), minimum=0, maximum=1_000_000)
    tool_use_count = safe_integer(raw.get("tool_use_count"), minimum=0, maximum=1_000_000)
    if content_delta_count is not None:
        safe_diagnostic["content_delta_count"] = content_delta_count
    if tool_use_start_count is not None:
        safe_diagnostic["tool_use_start_count"] = tool_use_start_count
    if tool_use_count is not None:
        safe_diagnostic["tool_use_count"] = tool_use_count
    first_content_ms = safe_duration(raw.get("time_to_first_content_ms"))
    if first_content_ms is not None:
        safe_diagnostic["time_to_first_content_ms"] = first_content_ms
    if type(raw.get("message_stop_seen")) is bool:
        safe_diagnostic["message_stop_seen"] = raw["message_stop_seen"]
    raw_stop_reason = raw.get("stop_reason")
    if raw_stop_reason is None or (
        isinstance(raw_stop_reason, str) and raw_stop_reason in _CARD020_SAFE_STOP_REASONS
    ):
        safe_diagnostic["stop_reason"] = raw_stop_reason
    else:
        safe_diagnostic["stop_reason"] = "other"
    return safe_diagnostic


def create_card020_router(db, llm_client=None, *, runner=None) -> APIRouter:
    router = APIRouter(prefix="/api/research/card020", tags=["Card020"])
    store = Card020Store(db.conn)
    strategy_flow = StrategyIdeaFlowService()

    @router.get("/protocol")
    def get_protocol():
        source_text, protocol_hash = _read_protocol()
        return {
            "strategy_id": STRATEGY_ID,
            "protocol_revision": 3,
            "protocol_sha256": protocol_hash,
            "source_text": source_text,
            "confirmation_statement": "我已阅读上方固定规则与证据限制，确认冻结本策略和输入清单。",
        }

    @router.post("/parse")
    def parse_protocol(request: ParseRequest):
        canonical_text, protocol_hash = _read_protocol()
        source_hash = hashlib.sha256(request.source_text.encode("utf-8")).hexdigest().upper()
        if _normalize_line_endings(request.source_text) != _normalize_line_endings(canonical_text):
            result = {
                "status": "blocked",
                "fields": {},
                "source_mappings": [],
                "line_coverage": [],
                "blocking_fields": [],
                "blocking_reasons": ["提交文本与固定修订3协议不一致；仅忽略 CRLF/LF 换行差异。"],
                "source_sha256": source_hash,
            }
            return store.record_parse(
                protocol_sha256=protocol_hash,
                source_text=request.source_text,
                result=result,
                status="blocked",
            )
        if llm_client is None:
            raise HTTPException(status_code=503, detail="真实 LLM 解析服务当前不可用。")
        try:
            result = strategy_flow.parse_fixed_510880_strategy(
                request.source_text,
                llm_client=llm_client,
            )
        except Exception as exc:
            failed = {
                "status": "provider_error",
                "fields": {},
                "source_mappings": [],
                "line_coverage": [],
                "blocking_fields": [],
                "blocking_reasons": ["真实 LLM 调用或结构化输出校验失败；未使用本地回退。"],
                "source_sha256": source_hash,
                "error_type": type(exc).__name__,
            }
            call_diagnostic = _safe_card020_call_diagnostic(exc)
            if call_diagnostic is not None:
                failed["call_diagnostic"] = call_diagnostic
            failed["parser_sha256"] = _parser_sha256()
            recorded = store.record_parse(
                protocol_sha256=protocol_hash,
                source_text=request.source_text,
                result=failed,
                status="provider_error",
            )
            raise HTTPException(
                status_code=502,
                detail={"message": "真实 LLM 解析失败，失败记录已保存。", "parse_id": recorded["parse_id"]},
            ) from exc
        result["parser_sha256"] = _parser_sha256()
        return store.record_parse(
            protocol_sha256=protocol_hash,
            source_text=request.source_text,
            result=result,
            status=result["status"],
        )

    @router.post("/preflight")
    def preflight_inputs():
        _, protocol_hash = _read_protocol()
        try:
            prepared = prepare_card020_inputs()
            preflight = prepared["preflight"]
        except Exception as exc:
            preflight = {
                "preflight_id": f"card020_preflight_failed_{hashlib.sha256(str(id(exc)).encode()).hexdigest()[:16]}",
                "status": "blocked",
                "strategy_id": STRATEGY_ID,
                "protocol_sha256": protocol_hash,
                "critical_source_gaps": ["固定历史输入或执行代码清单核验失败。"],
                "historical_metrics_computed": False,
                "error_type": type(exc).__name__,
            }
            return store.record_preflight(preflight)
        return store.record_preflight(preflight)

    @router.get("/parses/{parse_id}")
    def get_parse(parse_id: str):
        parse = store.get_parse(parse_id)
        if parse is None:
            raise HTTPException(status_code=404, detail="解析记录不存在。")
        parse.pop("source_text", None)
        return parse

    @router.post("/freeze")
    def freeze_strategy(request: FreezeRequest):
        _, protocol_hash = _read_protocol()
        try:
            current_preflight = prepare_card020_inputs()["preflight"]
        except Exception as exc:
            raise HTTPException(status_code=503, detail="冻结前输入/执行版本复核失败。") from exc
        saved_preflight = store.get_preflight(request.preflight_id)
        if saved_preflight is None:
            raise HTTPException(status_code=404, detail="请先完成固定输入预检。")
        if (
            current_preflight["input_inventory_sha256"] != saved_preflight.get("input_inventory_sha256")
            or current_preflight["execution_fingerprint"]["bundle_sha256"]
            != (saved_preflight.get("execution_fingerprint") or {}).get("bundle_sha256")
        ):
            raise HTTPException(status_code=409, detail="输入或执行代码在预检后发生变化，请重新预检。")
        try:
            return store.freeze_parse(
                request.parse_id,
                request.preflight_id,
                request.confirmed,
                request.source_sha256.upper(),
                protocol_hash,
            )
        except Card020Conflict as exc:
            status_code = 409 if str(exc) != "parse_not_found" else 404
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @router.get("/state")
    def get_state():
        _, protocol_hash = _read_protocol()
        state = store.get_state()
        state["protocol_sha256"] = protocol_hash
        return state

    @router.post("/run")
    def run_validation(request: RunRequest):
        _, current_protocol_hash = _read_protocol()
        frozen = store.get_frozen(request.freeze_id)
        if frozen is None:
            raise HTTPException(status_code=409, detail="策略尚未由页面确认并冻结。")
        if frozen["protocol_sha256"] != current_protocol_hash or current_protocol_hash != PROTOCOL_SHA256:
            raise HTTPException(status_code=409, detail="冻结协议哈希与当前修订3不一致。")
        try:
            prepared = prepare_card020_inputs()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="固定输入清单复核失败，未启动历史运行。") from exc
        current_preflight = prepared["preflight"]
        if (
            current_preflight["input_inventory_sha256"] != frozen["input_inventory_sha256"]
            or current_preflight["execution_fingerprint"]["bundle_sha256"] != frozen["execution_bundle_sha256"]
            or current_preflight["execution_fingerprint"]["executor_version"] != frozen["executor_version"]
        ):
            raise HTTPException(status_code=409, detail="冻结后的输入或执行代码已变化；未启动历史运行。")
        if not _RUN_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="已有 Card020 历史运行正在进行。")
        try:
            try:
                claimed, run_record = store.begin_run(request.freeze_id, request.idempotency_key)
            except Card020Conflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if not claimed:
                if run_record["status"] == "running":
                    raise HTTPException(status_code=409, detail={"run_id": run_record["run_id"], "status": "running"})
                return run_record
            if runner is None:
                store.finish_run(run_record["run_id"], result=None, error_code="runner_unavailable")
                raise HTTPException(status_code=503, detail="Card020 固定运行器不可用。")
            try:
                result = runner(
                    frozen,
                    market=prepared["market"],
                    calendar=prepared["calendar"],
                    dividend_events=prepared["dividend_events"],
                    data_provenance=prepared["data_provenance"],
                )
            except Exception as exc:
                store.finish_run(run_record["run_id"], result=None, error_code="deterministic_run_failed")
                raise HTTPException(
                    status_code=500,
                    detail={"run_id": run_record["run_id"], "message": "确定性运行失败；失败状态已保存。"},
                ) from exc
            return store.finish_run(run_record["run_id"], result=result)
        finally:
            _RUN_LOCK.release()

    @router.get("/runs")
    def list_runs():
        return {"runs": store.list_runs()}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        result = store.get_run(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="运行记录不存在。")
        return result

    return router


def _parser_sha256() -> str:
    path = PROJECT_ROOT / "backend" / "services" / "strategy_idea_flow.py"
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()
