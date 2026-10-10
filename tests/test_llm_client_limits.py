"""
Unit tests for V2 LLMClient limits (no real provider).

Proves:
- Process-wide concurrency cap 2: 3 simultaneous create_message attempts
  reach at most 2 provider calls; the 3rd raises llm_concurrency_exhausted.
- Per-decision_loop_id budget cap 3: the 4th call under one loop id
  raises llm_budget_exhausted and makes NO provider call.
- Buy/sell/approval confirmations must not call LLM: this client enforces
  the budget purely by count, so the workflow must never call create_message
  on a confirmation path; a confirmation that did call would consume a budget slot,
  which is why the deterministic reducer path must skip the LLM entirely.
"""

import threading
import time

from backend.services.llm_client import (
    LLMClient,
    _PROCESS_SEMAPHORE,
    _DECISION_LOOP_CALLS,
    _CALL_LIMIT_PER_LOOP,
)


class _Counter:
    def __init__(self):
        self.n = 0


class _FakeMessages:
    def __init__(self, counter, hold=0.0):
        self.counter = counter
        self.hold = hold

    def create(self, **kwargs):
        self.counter.n += 1
        if self.hold:
            time.sleep(self.hold)
        return _FakeResponse()


class _FakeClient:
    def __init__(self, counter, hold=0.0):
        self.messages = _FakeMessages(counter, hold=hold)


class _FakeResponse:
    def __init__(self):
        self.id = "msg_fake"
        self.model = "fake"
        self.role = "assistant"
        self.stop_reason = "end_turn"
        self.content = []
        self.usage = _Ns(input_tokens=1, output_tokens=1)


class _Ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _make_client(counter, hold=0.0):
    # Construct with a dummy key (no network at construction), then swap the
    # real Anthropic client for a counting fake.
    c = LLMClient(api_key="fake-test-key")
    c.client = _FakeClient(counter, hold=hold)
    return c


def _reset_loops():
    _DECISION_LOOP_CALLS.clear()


def test_concurrency_cap_two():
    """3 simultaneous calls -> at most 2 provider calls; 3rd raises."""
    _reset_loops()
    counter = _Counter()
    client = _make_client(counter, hold=0.5)  # hold so 2 are concurrent

    errors = []

    def worker():
        try:
            client.create_message(
                messages=[{"role": "user", "content": "x"}],
                decision_loop_id="loop_conc",
                stage="research",
            )
        except ValueError as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert counter.n == 2, f"expected 2 provider calls, got {counter.n}"
    assert any("llm_concurrency_exhausted" in e for e in errors), (
        f"expected llm_concurrency_exhausted, errors={errors}"
    )
    # semaphore fully released after the run
    assert _PROCESS_SEMAPHORE._value == 2, (
        f"semaphore leaked: {_PROCESS_SEMAPHORE._value}"
    )


def test_budget_cap_three():
    """4th call under one decision_loop_id is rejected, no provider call."""
    _reset_loops()
    counter = _Counter()
    client = _make_client(counter)

    loop = "loop_budget"
    for i in range(3):
        client.create_message(
            messages=[{"role": "user", "content": f"x{i}"}],
            decision_loop_id=loop,
            stage="research",
        )
    assert counter.n == 3, f"first 3 calls should reach provider, got {counter.n}"

    raised = None
    try:
        client.create_message(
            messages=[{"role": "user", "content": "x3"}],
            decision_loop_id=loop,
            stage="research",
        )
    except ValueError as e:
        raised = str(e)

    assert raised is not None, "4th call must raise"
    assert "llm_budget_exhausted" in raised, f"unexpected error: {raised}"
    assert counter.n == 3, (
        f"4th call must NOT reach provider, got {counter.n}"
    )
    assert _DECISION_LOOP_CALLS[loop] == 3


def test_budget_isolated_per_loop():
    """Different loops have independent budgets."""
    _reset_loops()
    counter = _Counter()
    client = _make_client(counter)

    for loop in ("A", "B"):
        for _ in range(3):
            client.create_message(
                messages=[{"role": "user", "content": "x"}],
                decision_loop_id=loop,
                stage="research",
            )
    assert counter.n == 6
    for loop in ("A", "B"):
        assert _DECISION_LOOP_CALLS[loop] == 3


def test_call_diagnostic_extracts_http_status_and_safe_provider_code():
    import json
    from types import SimpleNamespace
    from unittest.mock import patch

    from backend.services.llm_client import LLMClient

    sentinel = "provider-response-sentinel"

    class _HTTPFailure(Exception):
        status_code = 429
        code = "provider-key-shaped-sentinel"
        body = {
            "error": {
                "type": "rate_limit_error",
                "message": "Authorization: Bearer response-secret-sentinel",
            }
        }

        def __init__(self):
            super().__init__(sentinel)

    def fail_request(**_kwargs):
        raise _HTTPFailure()

    fake_provider = SimpleNamespace(messages=SimpleNamespace(create=fail_request))
    with patch("backend.services.llm_client.Anthropic", return_value=fake_provider):
        client = LLMClient(api_key="test-key", base_url="https://api.anthropic.com", model="test-model")

    try:
        client.create_message(messages=[{"role": "user", "content": "safe test input"}], stage="planner")
    except ValueError as exc:
        diagnostic = getattr(exc.__cause__, "call_diagnostic", None)
    else:
        raise AssertionError("expected the local provider transport to fail")

    assert diagnostic["http_status"] == 429
    assert diagnostic["provider_code"] == "rate_limit_error"
    assert diagnostic["timeout"] is False
    assert sentinel in json.dumps(diagnostic)
    assert "provider-key-shaped-sentinel" not in json.dumps(diagnostic)
    assert "response-secret-sentinel" not in json.dumps(diagnostic)
    assert "Authorization" not in json.dumps(diagnostic)
    assert "Bearer" not in json.dumps(diagnostic)


def test_no_loop_id_not_budgeted():
    """Without a decision_loop_id the per-loop budget does not apply."""
    _reset_loops()
    counter = _Counter()
    client = _make_client(counter)

    for _ in range(5):
        client.create_message(messages=[{"role": "user", "content": "x"}])
    assert counter.n == 5


def test_explicit_sdk_timeouts_retry_twice_and_record_each_attempt(monkeypatch):
    import json
    from anthropic import APITimeoutError
    from httpx import Request
    from types import SimpleNamespace

    calls = []
    constructor_kwargs = {}

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise APITimeoutError(request=Request("POST", "https://cc-vibe.com/v1/messages"))
        return _FakeResponse()

    provider = SimpleNamespace(messages=SimpleNamespace(create=create))

    def make_provider(**kwargs):
        constructor_kwargs.update(kwargs)
        return provider

    monkeypatch.setattr("backend.services.llm_client.Anthropic", make_provider)
    monkeypatch.setattr("backend.services.llm_client.time.sleep", lambda _seconds: None)
    _reset_loops()
    client = LLMClient(api_key="test-key", base_url="https://cc-vibe.com", model="test-model")

    response = client.create_message(
        messages=[{"role": "user", "content": "test"}],
        decision_loop_id="loop-timeout-retry",
        stage="planner",
    )

    diagnostic = response.call_diagnostic
    assert len(calls) == 3
    assert constructor_kwargs["max_retries"] == 0
    assert _DECISION_LOOP_CALLS["loop-timeout-retry"] == 3
    assert diagnostic["attempt_count"] == 3
    assert diagnostic["retry_count"] == 2
    assert [item["status"] for item in diagnostic["attempts"]] == [
        "timeout", "timeout", "success",
    ]
    assert all(item["exception_chain"] for item in diagnostic["attempts"][:2])
    assert "test-key" not in json.dumps(diagnostic)


def test_non_timeout_connection_error_is_not_retried_and_chain_is_redacted(monkeypatch):
    import json
    from anthropic import APIConnectionError
    from httpx import Request
    from types import SimpleNamespace

    calls = []
    api_key = "test-api-key-123"
    lower_message = (
        f"connection lost; Authorization: Bearer {api_key}; "
        "https://user:password@cc-vibe.com/v1/messages?access_token=query-secret"
    )

    def create(**_kwargs):
        calls.append(1)
        try:
            raise OSError(lower_message)
        except OSError as lower:
            raise APIConnectionError(request=Request("POST", "https://cc-vibe.com/v1/messages")) from lower

    provider = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr("backend.services.llm_client.Anthropic", lambda **_kwargs: provider)
    monkeypatch.setattr("backend.services.llm_client.time.sleep", lambda _seconds: None)
    client = LLMClient(api_key=api_key, base_url="https://cc-vibe.com", model="test-model")

    try:
        client.create_message(messages=[{"role": "user", "content": "safe"}])
    except ValueError as exc:
        public_error = str(exc)
        diagnostic = exc.__cause__.call_diagnostic
    else:
        raise AssertionError("expected a connection failure")

    serialized = json.dumps(diagnostic)
    assert len(calls) == 1
    assert diagnostic["retry_count"] == 0
    assert diagnostic["attempt_count"] == 1
    assert diagnostic["timeout"] is False
    assert "connection lost" in serialized
    assert [item["type"] for item in diagnostic["exception_chain"]] == [
        "APIConnectionError", "OSError",
    ]
    assert api_key not in serialized
    assert "user:password" not in serialized
    assert "query-secret" not in serialized
    assert "Bearer " + api_key not in serialized
    assert "[REDACTED]" in serialized
    assert api_key not in public_error
    assert "password" not in public_error
    assert "query-secret" not in public_error


def test_timeout_retries_stop_at_three_attempts_and_obey_loop_budget(monkeypatch):
    from anthropic import APITimeoutError
    from httpx import Request
    from types import SimpleNamespace

    monkeypatch.setattr("backend.services.llm_client.Anthropic", lambda **_kwargs: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: (_ for _ in ()).throw(
            APITimeoutError(request=Request("POST", "https://cc-vibe.com/v1/messages"))
        ))
    ))
    monkeypatch.setattr("backend.services.llm_client.time.sleep", lambda _seconds: None)
    _reset_loops()
    client = LLMClient(api_key="test-key", base_url="https://cc-vibe.com", model="test-model")

    try:
        client.create_message(messages=[{"role": "user", "content": "test"}], decision_loop_id="loop-three-timeouts")
    except ValueError as exc:
        diagnostic = exc.__cause__.call_diagnostic
    else:
        raise AssertionError("three timeouts should fail")
    assert diagnostic["attempt_count"] == 3
    assert diagnostic["retry_count"] == 2
    assert len(diagnostic["attempts"]) == 3
    assert _DECISION_LOOP_CALLS["loop-three-timeouts"] == 3

    _reset_loops()
    _DECISION_LOOP_CALLS["loop-budget-nearly-full"] = 2
    calls = []

    def one_timeout(**_kwargs):
        calls.append(1)
        raise APITimeoutError(request=Request("POST", "https://cc-vibe.com/v1/messages"))

    client.client = SimpleNamespace(messages=SimpleNamespace(create=one_timeout))
    try:
        client.create_message(
            messages=[{"role": "user", "content": "test"}],
            decision_loop_id="loop-budget-nearly-full",
        )
    except ValueError as exc:
        diagnostic = exc.__cause__.call_diagnostic
    else:
        raise AssertionError("the final loop budget slot should allow one attempt only")
    assert len(calls) == 1
    assert _DECISION_LOOP_CALLS["loop-budget-nearly-full"] == 3
    assert diagnostic["retry_count"] == 0
    assert diagnostic["retry_stop_reason"] == "decision_loop_budget_exhausted"


def test_http_error_diagnostic_keeps_status_and_redacted_response_text(monkeypatch):
    import json
    from types import SimpleNamespace

    class _Response:
        status_code = 404
        text = '{"error":{"type":"not_found_error","message":"model_not_found token=provider-secret"}}'

    class _HTTPFailure(Exception):
        status_code = 404
        code = "not_found_error"
        body = {"error": {"type": "not_found_error", "message": "model_not_found token=provider-secret"}}
        response = _Response()

    calls = []

    def fail(**_kwargs):
        calls.append(1)
        raise _HTTPFailure("provider-secret")

    provider = SimpleNamespace(messages=SimpleNamespace(create=fail))
    monkeypatch.setattr("backend.services.llm_client.Anthropic", lambda **_kwargs: provider)
    client = LLMClient(api_key="test-key", base_url="https://cc-vibe.com", model="test-model")

    try:
        client.create_message(messages=[{"role": "user", "content": "safe"}])
    except ValueError as exc:
        public_error = str(exc)
        diagnostic = exc.__cause__.call_diagnostic
    else:
        raise AssertionError("expected HTTP failure")

    serialized = json.dumps(diagnostic)
    assert len(calls) == 1
    assert diagnostic["http_status"] == 404
    assert diagnostic["provider_code"] == "not_found_error"
    assert diagnostic["response_received"] is True
    assert "model_not_found" in serialized
    assert "provider-secret" not in serialized
    assert "token=[REDACTED]" in serialized
    assert "provider-secret" not in public_error


def _llm_failure_log_events(caplog):
    import json

    events = []
    for record in caplog.records:
        message = record.getMessage()
        marker = "LLM_CALL_FAILURE "
        if marker in message:
            events.append(json.loads(message.split(marker, 1)[1]))
    return events


def test_non_diagnostic_failure_logs_redacted_full_cause_and_context_chain(caplog):
    from types import SimpleNamespace

    api_key = "client-api-secret-880"
    request_text = "private-user-input-510880"
    cause_secret = "cause-bearer-secret"
    context_secret = "context-password-secret"
    body_secret = "provider-body-secret"
    response_secret = "response-header-secret"

    class _Response:
        status_code = 502
        text = (
            '{"error":{"message":"Authorization: Bearer '
            + response_secret
            + '","access_token":"'
            + body_secret
            + '","request":"'
            + request_text
            + '"}}'
        )

    class _ProviderFailure(Exception):
        status_code = 502
        body = {
            "error": {
                "message": "request rejected",
                "access_token": body_secret,
            }
        }
        response = _Response()

    cause = OSError(f"socket closed; Authorization: Bearer {cause_secret}")
    context = ValueError(f"prompt={request_text}; password={context_secret}")
    failure = _ProviderFailure(f"api_key={api_key}; request={request_text}")
    failure.__cause__ = cause
    failure.__context__ = context
    provider = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: (_ for _ in ()).throw(failure)),
    )
    client = LLMClient(api_key=api_key, base_url="https://cc-vibe.com", model="test-model")
    client.client = provider
    caplog.set_level("WARNING", logger="backend.services.llm_client")

    try:
        client.create_message(messages=[{"role": "user", "content": request_text}])
    except ValueError as exc:
        diagnostic = exc.call_diagnostic
    else:
        raise AssertionError("expected a provider failure")

    events = _llm_failure_log_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["call_id"] == diagnostic["call_id"]
    assert event["stage"] is None
    assert event["provider"] == "cc-vibe"
    assert event["model"] == "test-model"
    assert event["attempt"] == 1
    assert event["http_status"] == 502
    assert event["timeout"] is False
    assert event["response_received"] is True
    assert event["retrying"] is False
    assert [item["type"] for item in event["exception_chain"]] == [
        "_ProviderFailure", "OSError", "ValueError",
    ]
    logged_text = " ".join(record.getMessage() for record in caplog.records)
    for secret in (api_key, request_text, cause_secret, context_secret, body_secret, response_secret):
        assert secret not in logged_text
    assert "[REDACTED]" in logged_text
    assert "[REDACTED_REQUEST_TEXT]" in logged_text


def test_timeout_retries_log_each_failed_attempt_and_terminal_failure(caplog, monkeypatch):
    import json
    from anthropic import APITimeoutError
    from httpx import Request
    from types import SimpleNamespace

    monkeypatch.setattr("backend.services.llm_client.time.sleep", lambda _seconds: None)
    provider = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: (_ for _ in ()).throw(
        APITimeoutError(request=Request("POST", "https://cc-vibe.com/v1/messages"))
    )))
    client = LLMClient(api_key="test-key", base_url="https://cc-vibe.com", model="test-model")
    client.client = provider
    caplog.set_level("WARNING", logger="backend.services.llm_client")

    try:
        client.create_message(messages=[{"role": "user", "content": "timeout request"}])
    except ValueError:
        pass
    else:
        raise AssertionError("three timeouts should fail")

    events = _llm_failure_log_events(caplog)
    assert len(events) == 3
    assert [event["attempt"] for event in events] == [1, 2, 3]
    assert [event["retrying"] for event in events] == [True, True, False]
    assert [event["timeout"] for event in events] == [True, True, True]
    assert len({event["call_id"] for event in events}) == 1
    assert "test-key" not in " ".join(record.getMessage() for record in caplog.records)


def test_success_does_not_emit_llm_failure_log(caplog):
    _reset_loops()
    client = _make_client(_Counter())
    caplog.set_level("WARNING", logger="backend.services.llm_client")

    client.create_message(messages=[{"role": "user", "content": "normal request"}])

    assert _llm_failure_log_events(caplog) == []
