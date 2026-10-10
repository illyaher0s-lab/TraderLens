"""
LLM Client for Research Conversation Agent.

Connects to cc-vibe.com API with Anthropic-compatible interface.
Supports tool calling for whitelisted research tools.

CONSTRAINTS:
- Agent can only call whitelisted tools
- Agent cannot directly mutate board state
- Agent can only create ProposedAction
- Missing API key must fail loud, not silent fallback
"""

from __future__ import annotations

import os
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from anthropic import APITimeoutError, Anthropic
from httpx import TimeoutException

# V2 process-wide concurrency + per-loop budget guards.
# Single backend worker (--workers 1) → these are global V2 limits.
_PROCESS_SEMAPHORE = threading.BoundedSemaphore(2)
_DECISION_LOOP_CALLS: dict[str, int] = {}
_CALL_LIMIT_PER_LOOP = 3
_DECISION_LOOP_CALLS_LOCK = threading.Lock()
_MAX_TIMEOUT_RETRIES = 2
_TIMEOUT_RETRY_DELAYS = (0.25, 0.5)
_LOGGER = logging.getLogger(__name__)


def _request_input_bytes(messages, system, tools, max_tokens):
    try:
        payload = json.dumps(
            {"messages": messages, "system": system, "tools": tools, "max_tokens": max_tokens},
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        return 0
    return len(payload)


_SAFE_PROVIDER_CODES = frozenset(
    {
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
        "rate_limit_error",
        "api_error",
        "overloaded_error",
        "internal_server_error",
    }
)


def _safe_provider_code(exc):
    try:
        values = [getattr(exc, "code", None)]
        body = getattr(exc, "body", None)
        error = body.get("error") if isinstance(body, dict) else None
        values.append(error.get("type") if isinstance(error, dict) else None)
    except Exception:
        return None
    return next(
        (value for value in values if isinstance(value, str) and value in _SAFE_PROVIDER_CODES),
        None,
    )


def _exception_chain(exc: BaseException) -> list[BaseException]:
    pending = [exc]
    seen: set[int] = set()
    chain = []
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return chain


def _is_timeout_exception(exc: BaseException) -> bool:
    return any(
        isinstance(item, (APITimeoutError, TimeoutException, TimeoutError))
        for item in _exception_chain(exc)
    )


def _request_text_fragments(messages, system, tools) -> tuple[str, ...]:
    fragments: set[str] = set()

    def visit(value, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, str):
            if len(value) >= 8:
                fragments.add(value)
            stripped = value.lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    visit(json.loads(value), depth + 1)
                except (TypeError, ValueError):
                    pass
        elif isinstance(value, dict):
            for item in value.values():
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, depth + 1)

    visit(messages)
    visit(system)
    visit(tools)
    return tuple(sorted(fragments, key=lambda fragment: (-len(fragment), fragment)))


def _safe_diagnostic_text(
    value,
    api_key: str | None,
    request_fragments: tuple[str, ...],
    sensitive_fragments: tuple[str, ...] = (),
) -> str:
    text = str(value)
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    for fragment in request_fragments:
        text = text.replace(fragment, "[REDACTED_REQUEST_TEXT]")
    for fragment in sensitive_fragments:
        if fragment:
            text = text.replace(fragment, "[REDACTED]")
    text = re.sub(
        r"(?i)[\"']?(?:authorization|proxy-authorization)[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?[^\"'\s,;}]+(?:\s+[^\"'\s,;}]+)?",
        "[REDACTED_HEADER]",
        text,
    )
    text = re.sub(
        r"(?i)([\"']?(?:x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;}]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(r"(?i)\bbearer\s+[^\s,;}]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(
        r"(?i)([?&][^=?&#\s]*(?:token|key|secret|auth|signature|credential)[^=?&#\s]*=)[^&#\s]+",
        r"\1[REDACTED]",
        text,
    )
    return text


def _diagnostic_exception_chain(
    exc,
    api_key: str | None,
    request_fragments: tuple[str, ...],
    sensitive_fragments: tuple[str, ...] = (),
) -> list[dict]:
    result = []
    for item in _exception_chain(exc):
        message = _safe_diagnostic_text(
            str(item), api_key, request_fragments, sensitive_fragments,
        )
        result.append({"type": type(item).__name__, "message": message})
    return result


def _log_failure_event(
    diagnostic: dict,
    *,
    event: str,
    attempt: int,
    status: str,
    retrying: bool,
) -> None:
    """Write only the already-sanitized call diagnostic to the existing log."""
    payload = {
        "event": event,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "call_id": diagnostic.get("call_id"),
        "stage": diagnostic.get("stage"),
        "provider": diagnostic.get("provider"),
        "model": diagnostic.get("model"),
        "attempt": attempt,
        "status": status,
        "http_status": diagnostic.get("http_status"),
        "provider_code": diagnostic.get("provider_code"),
        "timeout": diagnostic.get("timeout") is True,
        "response_received": diagnostic.get("response_received") is True,
        "retrying": retrying,
        "retry_stop_reason": diagnostic.get("retry_stop_reason"),
        "exception_chain": diagnostic.get("exception_chain") or [],
        "response_error_text": diagnostic.get("response_error_text"),
    }
    try:
        _LOGGER.warning("LLM_CALL_FAILURE %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        # A logging failure must not change the provider call's existing behavior.
        return


def _http_status_from_chain(exc) -> int | None:
    for item in _exception_chain(exc):
        status = getattr(item, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            return status
        response = getattr(item, "response", None)
        response_status = getattr(response, "status_code", None)
        if type(response_status) is int and 100 <= response_status <= 599:
            return response_status
    return None


def _response_error_text_from_chain(
    exc,
    api_key: str | None,
    request_fragments: tuple[str, ...],
    sensitive_fragments: tuple[str, ...] = (),
) -> str | None:
    for item in _exception_chain(exc):
        body = getattr(item, "body", None)
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False, default=str) if isinstance(body, (dict, list)) else str(body)
            return _safe_diagnostic_text(raw, api_key, request_fragments, sensitive_fragments)
        response = getattr(item, "response", None)
        if response is not None:
            try:
                response_text = response.text
            except Exception:
                response_text = None
            if isinstance(response_text, str) and response_text:
                return _safe_diagnostic_text(response_text, api_key, request_fragments, sensitive_fragments)
    return None


def _response_secret_fragments(exc) -> tuple[str, ...]:
    sensitive_key = re.compile(
        r"(?i)(?:authorization|proxy-authorization|x-api-key|api[_-]?key|"
        r"access[_-]?token|refresh[_-]?token|token|secret|password|credential)"
    )
    secrets: set[str] = set()

    def collect(value, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(key, str) and sensitive_key.search(key) and isinstance(item, str):
                    candidate = item.strip()
                    if candidate:
                        secrets.add(candidate)
                        if candidate.lower().startswith("bearer "):
                            secrets.add(candidate[7:].strip())
                collect(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, depth + 1)
        elif isinstance(value, str):
            for pattern in (
                r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[\"']?([^\"'\s,;}]+)",
                r"(?i)(?:x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|credential)"
                r"[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}]+)",
            ):
                for match in re.finditer(pattern, value):
                    if match.group(1):
                        secrets.add(match.group(1))
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    collect(json.loads(stripped), depth + 1)
                except (TypeError, ValueError):
                    pass

    for item in _exception_chain(exc):
        collect(getattr(item, "body", None))
        response = getattr(item, "response", None)
        if response is not None:
            try:
                collect(response.text)
            except Exception:
                pass
    return tuple(sorted(secrets, key=lambda fragment: (-len(fragment), fragment)))


def _provider_code_from_chain(exc) -> str | None:
    for item in _exception_chain(exc):
        code = _safe_provider_code(item)
        if code is not None:
            return code
    return None


def _reserve_decision_loop_call(decision_loop_id: str) -> bool:
    with _DECISION_LOOP_CALLS_LOCK:
        used = _DECISION_LOOP_CALLS.get(decision_loop_id, 0)
        if used >= _CALL_LIMIT_PER_LOOP:
            return False
        _DECISION_LOOP_CALLS[decision_loop_id] = used + 1
        return True


class LLMCallResult(dict):
    def __init__(self, payload: dict, call_diagnostic: dict):
        super().__init__(payload)
        self.call_diagnostic = dict(call_diagnostic)


class LLMClient:
    """
    LLM client for research conversation agent.
    
    Uses Anthropic SDK with custom base URL.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        """
        Initialize LLM client.

        Args:
            api_key: API key (loads from RESEARCH_LLM_API_KEY env var if None)
            base_url: API base URL
            model: Model name
            timeout: Finite request timeout (seconds). A hung upstream fails
                fast and surfaces as research_unavailable instead of blocking
                forever. 30s matches the precedent in serenity_executor.py.

        Raises:
            ValueError: If API key is missing
        """
        self.api_key = api_key or os.getenv("RESEARCH_LLM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "LLM API key not configured. "
                "Set RESEARCH_LLM_API_KEY environment variable or pass api_key explicitly."
            )

        self.base_url = base_url or os.getenv("RESEARCH_LLM_BASE_URL", "https://cc-vibe.com")
        self.model = model or os.getenv("RESEARCH_LLM_MODEL", "claude-sonnet-4-6")
        self.timeout = timeout

        self.client = Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=0,
        )

    def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        decision_loop_id: str | None = None,
        stage: str | None = None,
        source_count: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Create a message with the LLM.

        Args:
            messages: Conversation messages
            system: System prompt
            tools: Tool definitions
            max_tokens: Maximum tokens to generate
            decision_loop_id: V2 whole-loop budget key; enforces a hard
                cap of _CALL_LIMIT_PER_LOOP calls per loop (default 3).
            stage: V2 stage label for latency telemetry.
            timeout: Optional per-request timeout override; None uses the
                timeout configured when the client was created.

        Returns:
            Response dict with content, tool_use, and usage

        Raises:
            ValueError: If API call fails, budget exhausted (4th call in a
                loop), or concurrency exhausted (more than 2 simultaneous).
        """
        # Each provider attempt, including a timeout retry, consumes a loop slot.
        if decision_loop_id is not None:
            with _DECISION_LOOP_CALLS_LOCK:
                if _DECISION_LOOP_CALLS.get(decision_loop_id, 0) >= _CALL_LIMIT_PER_LOOP:
                    raise ValueError("llm_budget_exhausted")

        # --- V2 process-wide concurrency guard: at most 2 simultaneous ---
        acquired = _PROCESS_SEMAPHORE.acquire(timeout=0)
        if not acquired:
            raise ValueError("llm_concurrency_exhausted")

        try:
            request_started = time.perf_counter()
            request_fragments = _request_text_fragments(messages, system, tools)
            call_id = uuid.uuid4().hex
            failure_events_logged = 0
            diagnostic = {
                "call_id": call_id,
                "stage": stage if stage in {"planner", "synthesizer"} else None,
                "provider": self.get_provider_name(),
                "model": self.get_model_name(),
                "request_started_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": 0.0,
                "status": "in_progress",
                "exception_class": None,
                "http_status": None,
                "provider_code": None,
                "timeout": False,
                "response_received": False,
                "response_error_text": None,
                "exception_chain": [],
                "attempt_count": 0,
                "retry_count": 0,
                "retry_stop_reason": None,
                "attempts": [],
                "input_bytes": _request_input_bytes(messages, system, tools, max_tokens),
                "source_count": source_count if type(source_count) is int and source_count >= 0 else None,
                "output_parse_reached": False,
            }
            request_kwargs = {
                "model": self.model,
                "messages": messages,
                "system": system,
                "tools": tools,
                "max_tokens": max_tokens,
            }
            if timeout is not None:
                request_kwargs["timeout"] = timeout
            response = None
            last_exception = None
            for attempt_number in range(1, _MAX_TIMEOUT_RETRIES + 2):
                if decision_loop_id is not None and not _reserve_decision_loop_call(decision_loop_id):
                    diagnostic["retry_stop_reason"] = "decision_loop_budget_exhausted"
                    if last_exception is not None:
                        raise last_exception
                    raise ValueError("llm_budget_exhausted")

                attempt_started = time.perf_counter()
                diagnostic["attempt_count"] += 1
                try:
                    response = self.client.messages.create(**request_kwargs)
                except Exception as attempt_exception:
                    last_exception = attempt_exception
                    attempt_timeout = _is_timeout_exception(attempt_exception)
                    response_secrets = _response_secret_fragments(attempt_exception)
                    attempt_chain = _diagnostic_exception_chain(
                        attempt_exception, self.api_key, request_fragments, response_secrets,
                    )
                    attempt_status = _http_status_from_chain(attempt_exception)
                    attempt_provider_code = _provider_code_from_chain(attempt_exception)
                    attempt_response_error = _response_error_text_from_chain(
                        attempt_exception, self.api_key, request_fragments, response_secrets,
                    )
                    attempt_duration = max(0.0, (time.perf_counter() - attempt_started) * 1000)
                    attempt_diagnostic = {
                        "attempt": attempt_number,
                        "status": "timeout" if attempt_timeout else "error",
                        "duration_ms": attempt_duration,
                        "http_status": attempt_status,
                        "provider_code": attempt_provider_code,
                        "timeout": attempt_timeout,
                        "response_received": attempt_status is not None or attempt_response_error is not None,
                        "exception_chain": attempt_chain,
                        "response_error_text": attempt_response_error,
                    }
                    diagnostic["attempts"].append(attempt_diagnostic)
                    diagnostic["exception_class"] = type(attempt_exception).__name__
                    diagnostic["http_status"] = attempt_status
                    diagnostic["provider_code"] = attempt_provider_code
                    diagnostic["timeout"] = attempt_timeout
                    diagnostic["response_received"] = attempt_diagnostic["response_received"]
                    diagnostic["exception_chain"] = attempt_chain
                    diagnostic["response_error_text"] = attempt_response_error
                    if not attempt_timeout:
                        diagnostic["retry_stop_reason"] = "not_timeout"
                        _log_failure_event(
                            diagnostic,
                            event="llm_attempt_failed",
                            attempt=attempt_number,
                            status=attempt_diagnostic["status"],
                            retrying=False,
                        )
                        failure_events_logged += 1
                        raise
                    if attempt_number > _MAX_TIMEOUT_RETRIES:
                        diagnostic["retry_stop_reason"] = "max_retries_reached"
                        _log_failure_event(
                            diagnostic,
                            event="llm_attempt_failed",
                            attempt=attempt_number,
                            status=attempt_diagnostic["status"],
                            retrying=False,
                        )
                        failure_events_logged += 1
                        raise
                    if decision_loop_id is not None:
                        with _DECISION_LOOP_CALLS_LOCK:
                            has_loop_budget = (
                                _DECISION_LOOP_CALLS.get(decision_loop_id, 0)
                                < _CALL_LIMIT_PER_LOOP
                            )
                        if not has_loop_budget:
                            diagnostic["retry_stop_reason"] = "decision_loop_budget_exhausted"
                            _log_failure_event(
                                diagnostic,
                                event="llm_attempt_failed",
                                attempt=attempt_number,
                                status=attempt_diagnostic["status"],
                                retrying=False,
                            )
                            failure_events_logged += 1
                            raise
                    diagnostic["retry_count"] += 1
                    _log_failure_event(
                        diagnostic,
                        event="llm_attempt_failed",
                        attempt=attempt_number,
                        status=attempt_diagnostic["status"],
                        retrying=True,
                    )
                    failure_events_logged += 1
                    time.sleep(_TIMEOUT_RETRY_DELAYS[attempt_number - 1])
                    continue

                attempt_duration = max(0.0, (time.perf_counter() - attempt_started) * 1000)
                diagnostic["attempts"].append({
                    "attempt": attempt_number,
                    "status": "success",
                    "duration_ms": attempt_duration,
                    "http_status": None,
                    "provider_code": None,
                    "timeout": False,
                    "response_received": True,
                    "exception_chain": [],
                    "response_error_text": None,
                })
                diagnostic["response_received"] = True
                diagnostic["timeout"] = False
                diagnostic["status"] = "success"
                break

            if response is None:
                if last_exception is not None:
                    raise last_exception
                raise ValueError("llm_budget_exhausted")

            diagnostic["duration_ms"] = max(0.0, (time.perf_counter() - request_started) * 1000)
            # Convert response to dict
            result = {
                "id": response.id,
                "model": response.model,
                "role": response.role,
                "content": [],
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            # Extract content blocks
            for block in response.content:
                if block.type == "text":
                    result["content"].append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "tool_use":
                    result["content"].append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            return LLMCallResult(result, diagnostic)

        except Exception as exc:
            if "diagnostic" in locals():
                diagnostic["duration_ms"] = max(0.0, (time.perf_counter() - request_started) * 1000)
                diagnostic["status"] = "error"
                if (
                    not diagnostic["exception_chain"]
                    or (diagnostic["attempts"] and diagnostic["attempts"][-1]["status"] == "success")
                ):
                    response_secrets = _response_secret_fragments(exc)
                    diagnostic["exception_class"] = type(exc).__name__
                    diagnostic["http_status"] = _http_status_from_chain(exc)
                    diagnostic["provider_code"] = _provider_code_from_chain(exc)
                    diagnostic["timeout"] = _is_timeout_exception(exc)
                    diagnostic["exception_chain"] = _diagnostic_exception_chain(
                        exc, self.api_key, request_fragments, response_secrets,
                    )
                    diagnostic["response_error_text"] = _response_error_text_from_chain(
                        exc, self.api_key, request_fragments, response_secrets,
                    )
                    diagnostic["response_received"] = (
                        diagnostic["http_status"] is not None
                        or diagnostic["response_error_text"] is not None
                    )
                if not locals().get("failure_events_logged", 0):
                    _log_failure_event(
                        diagnostic,
                        event="llm_call_failed",
                        attempt=diagnostic.get("attempt_count", 0),
                        status="error",
                        retrying=False,
                    )
                try:
                    exc.call_diagnostic = dict(diagnostic)
                except Exception:
                    pass
            safe_chain = diagnostic.get("exception_chain", []) if "diagnostic" in locals() else []
            safe_detail = next(
                (
                    item.get("message")
                    for item in safe_chain
                    if isinstance(item, dict) and isinstance(item.get("message"), str) and item["message"]
                ),
                type(exc).__name__,
            )
            error = ValueError(f"LLM API call failed: {safe_detail}")
            if "diagnostic" in locals():
                try:
                    error.call_diagnostic = dict(diagnostic)
                except Exception:
                    pass
            raise error from exc
        finally:
            _PROCESS_SEMAPHORE.release()
    
    def get_provider_name(self) -> str:
        """Get the provider name for audit metadata."""
        # Extract provider from base_url
        if "cc-vibe.com" in self.base_url:
            return "cc-vibe"
        elif "anthropic.com" in self.base_url:
            return "anthropic"
        else:
            return "custom"
    
    def get_model_name(self) -> str:
        """Get the model name for audit metadata."""
        return self.model


class ResearchAgentTools:
    """
    Whitelisted tools for research conversation agent.
    
    Agent can ONLY call these tools.
    Agent CANNOT directly mutate board state.
    """

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """
        Get tool definitions for LLM.
        
        Returns:
            List of tool definitions in Anthropic format
        """
        return [
            {
                "name": "read_theme",
                "description": "Read current theme summary including name, background, status, and board_version.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                    },
                    "required": ["theme_id"],
                },
            },
            {
                "name": "read_candidates",
                "description": "Read current candidates for a theme, including symbols, status, and hard_filter_flags.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                    },
                    "required": ["theme_id"],
                },
            },
            {
                "name": "verify_ticker",
                "description": "Verify ticker/company/exchange identity from Tushare data source. Returns company name, exchange, listing status, and confidence level. MUST be called before proposing to add a stock.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol (e.g., '300750.SZ', '600519.SH')",
                        },
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "propose_add_candidate",
                "description": "Propose adding a candidate stock to the theme. Creates a ProposedAction that user must apply from the board. MUST call verify_ticker first and pass the verification_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol (verified)",
                        },
                        "verification_id": {
                            "type": "string",
                            "description": "Verification ID from verify_ticker tool (REQUIRED)",
                        },
                        "match_reason": {
                            "type": "string",
                            "description": "Why this stock matches the theme",
                        },
                    },
                    "required": ["theme_id", "symbol", "verification_id", "match_reason"],
                },
            },
        ]
