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
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal
from anthropic import Anthropic

# V2 process-wide concurrency + per-loop budget guards.
# Single backend worker (--workers 1) → these are global V2 limits.
_PROCESS_SEMAPHORE = threading.BoundedSemaphore(2)
_DECISION_LOOP_CALLS: dict[str, int] = {}
_CALL_LIMIT_PER_LOOP = 3


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
        # --- V2 per-loop budget guard: hard cap, no overflow/retry ---
        if decision_loop_id is not None:
            if _DECISION_LOOP_CALLS.get(decision_loop_id, 0) >= _CALL_LIMIT_PER_LOOP:
                raise ValueError("llm_budget_exhausted")

        # --- V2 process-wide concurrency guard: at most 2 simultaneous ---
        acquired = _PROCESS_SEMAPHORE.acquire(timeout=0)
        if not acquired:
            raise ValueError("llm_concurrency_exhausted")

        try:
            if decision_loop_id is not None:
                used = _DECISION_LOOP_CALLS.get(decision_loop_id, 0)
                _DECISION_LOOP_CALLS[decision_loop_id] = used + 1

            request_started = time.perf_counter()
            diagnostic = {
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
            response = self.client.messages.create(**request_kwargs)
            diagnostic["duration_ms"] = max(0.0, (time.perf_counter() - request_started) * 1000)
            diagnostic["status"] = "success"
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
                diagnostic["exception_class"] = type(exc).__name__
                status_code = getattr(exc, "status_code", None)
                diagnostic["http_status"] = status_code if type(status_code) is int and 100 <= status_code <= 599 else None
                diagnostic["provider_code"] = _safe_provider_code(exc)
                diagnostic["timeout"] = isinstance(exc, TimeoutError) or any(
                    base.__name__.lower().endswith("timeout") for base in type(exc).__mro__
                )
                try:
                    exc.call_diagnostic = dict(diagnostic)
                except Exception:
                    pass
            raise ValueError(f"LLM API call failed: {exc}") from exc
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
