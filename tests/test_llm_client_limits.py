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
    assert sentinel not in json.dumps(diagnostic)
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
