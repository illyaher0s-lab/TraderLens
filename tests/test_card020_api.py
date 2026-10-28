import hashlib
import json
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.card020 as card020_api
from backend.api.card020 import PROTOCOL_SHA256, create_card020_router
from backend.services.card020_preflight import _code_fingerprint
from backend.services.card020_store import Card020Conflict, Card020Store
from backend.services.card020_vol_budget import _json_sha256


class _FakeMessageStream:
    def __init__(self, final_message):
        self.response = SimpleNamespace(status_code=200)
        self.final_message = final_message

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
        return self.final_message

    def close(self):
        return None


def test_safe_card020_diagnostic_discards_unexpected_enum_types():
    class MalformedDiagnostic(Exception):
        call_diagnostic = {
            "attempt_count": 1,
            "retry_count": 0,
            "attempts": [{"attempt": 1, "status": {"secret": "status"}}],
            "retry_stop_reason": ["private"],
            "stop_reason": ["private"],
        }

    safe = card020_api._safe_card020_call_diagnostic(MalformedDiagnostic())

    assert safe is not None
    assert safe["attempts"] == []
    assert safe["retry_stop_reason"] is None
    assert safe["stop_reason"] == "other"
    assert "secret" not in json.dumps(safe)


def test_provider_error_persists_only_safe_call_diagnostic(monkeypatch):
    class DiagnosticFailure(TimeoutError):
        call_diagnostic = {
            "call_id": "private-call-id",
            "attempt_count": 3,
            "retry_count": 2,
            "duration_ms": 270750.5,
            "http_status": None,
            "timeout": True,
            "response_received": False,
            "retry_stop_reason": "max_retries_reached",
            "attempts": [
                {
                    "attempt": 1,
                    "status": "timeout",
                    "duration_ms": 90010.2,
                    "http_status": None,
                    "timeout": True,
                    "response_received": False,
                    "exception_chain": [{"message": "Authorization: Bearer private-token"}],
                },
                {
                    "attempt": 2,
                    "status": "timeout",
                    "duration_ms": 90011.3,
                    "http_status": None,
                    "timeout": True,
                    "response_received": False,
                },
                {
                    "attempt": 3,
                    "status": "timeout",
                    "duration_ms": 90012.4,
                    "http_status": None,
                    "timeout": True,
                    "response_received": False,
                },
            ],
            "api_key": "private-token",
            "base_url": "https://private.example",
            "exception_chain": [{"message": "private raw error"}],
        }

    class FailingClient:
        model = "synthetic-test-model"

        class Messages:
            def stream(self, **_kwargs):
                raise DiagnosticFailure("private raw error")

        client = SimpleNamespace(messages=Messages())

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    app = FastAPI()
    app.include_router(
        create_card020_router(type("DB", (), {"conn": connection})(), llm_client=FailingClient())
    )
    client = TestClient(app)
    source_text, _ = card020_api._read_protocol()

    response = client.post(
        "/api/research/card020/parse",
        json={"source_text": source_text},
    )

    assert response.status_code == 502
    parse_id = response.json()["detail"]["parse_id"]
    record = client.get("/api/research/card020/state").json()["latest_parse"]
    assert record["parse_id"] == parse_id
    diagnostic = record["result"]["call_diagnostic"]
    assert diagnostic["attempt_count"] == 1
    assert diagnostic["retry_count"] == 0
    assert diagnostic["timeout"] is True
    assert diagnostic["response_received"] is False
    assert diagnostic["retry_stop_reason"] == "max_retries_reached"
    assert diagnostic["attempts"][0]["status"] == "timeout"
    assert diagnostic["content_delta_count"] == 0
    assert diagnostic["message_stop_seen"] is False
    assert set(diagnostic) == {
        "attempt_count", "retry_count", "duration_ms", "http_status", "timeout",
        "response_received", "retry_stop_reason", "attempts", "content_delta_count",
        "tool_use_start_count", "tool_use_count", "message_stop_seen", "stop_reason",
    }
    assert set(diagnostic["attempts"][0]) == {
        "attempt", "status", "duration_ms", "http_status", "timeout", "response_received",
    }
    serialized = json.dumps(record)
    for private_value in ("private-call-id", "private-token", "private.example", "private raw error"):
        assert private_value not in serialized
    connection.close()


def test_stream_failure_after_content_persists_safe_progress_counts():
    calls = []

    class InterruptedStream:
        response = SimpleNamespace(status_code=200)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def __iter__(self):
            yield SimpleNamespace(type="message_start")
            yield SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="tool_use"))
            yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta"))
            raise ConnectionError("private streamed response fragment")

        def close(self):
            return None

    class Messages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            return InterruptedStream()

    llm_client = SimpleNamespace(
        model="synthetic-test-model",
        client=SimpleNamespace(messages=Messages()),
    )
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    app = FastAPI()
    app.include_router(create_card020_router(
        type("DB", (), {"conn": connection})(), llm_client=llm_client,
    ))
    client = TestClient(app)
    source_text, _ = card020_api._read_protocol()

    response = client.post("/api/research/card020/parse", json={"source_text": source_text})

    assert response.status_code == 502
    record = client.get("/api/research/card020/state").json()["latest_parse"]
    diagnostic = record["result"]["call_diagnostic"]
    assert len(calls) == 1
    assert diagnostic["attempt_count"] == 1
    assert diagnostic["retry_count"] == 0
    assert diagnostic["attempts"][0]["status"] == "error"
    assert diagnostic["response_received"] is True
    assert diagnostic["content_delta_count"] == 1
    assert diagnostic["time_to_first_content_ms"] >= 0
    assert diagnostic["tool_use_start_count"] == 1
    assert diagnostic["message_stop_seen"] is False
    assert "private streamed response fragment" not in json.dumps(record)
    connection.close()


def test_parse_api_persists_original_protocol_hash_and_text_with_numbered_model_view():
    class CapturingClient:
        def __init__(self):
            self.request = None
            self.model = "synthetic-test-model"
            self.client = SimpleNamespace(messages=self)

        def stream(self, **kwargs):
            self.request = kwargs
            final = SimpleNamespace(
                id="synthetic-card020-response",
                model="synthetic-test-model",
                stop_reason="tool_use",
                content=[SimpleNamespace(
                    type="tool_use",
                    name="submit_510880_strategy_mapping",
                    input={"mappings": [], "line_coverage": []},
                )],
            )
            return _FakeMessageStream(final)

    source_text, protocol_hash = card020_api._read_protocol()
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper()
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    llm_client = CapturingClient()
    app = FastAPI()
    app.include_router(
        create_card020_router(type("DB", (), {"conn": connection})(), llm_client=llm_client)
    )
    client = TestClient(app)

    response = client.post("/api/research/card020/parse", json={"source_text": source_text})

    assert response.status_code == 200
    saved = response.json()
    assert saved["status"] == "blocked"
    assert saved["source_sha256"] == source_hash
    assert saved["protocol_sha256"] == protocol_hash == PROTOCOL_SHA256
    expected_prompt = "\n".join(
        f"[L{line_number:04d}] {line}"
        for line_number, line in enumerate(source_text.splitlines(), start=1)
    )
    assert llm_client.request["messages"][0]["content"] == expected_prompt
    persisted = Card020Store(connection).get_parse(saved["parse_id"])
    assert persisted["source_text"] == source_text
    assert persisted["source_sha256"] == source_hash
    assert persisted["protocol_sha256"] == PROTOCOL_SHA256
    connection.close()


def test_parse_stopped_by_max_tokens_cannot_be_frozen():
    class MaxTokensClient:
        model = "synthetic-test-model"

        class Messages:
            def stream(self, **_kwargs):
                final = SimpleNamespace(
                    id="synthetic-max-tokens-response",
                    model="synthetic-test-model",
                    stop_reason="max_tokens",
                    content=[SimpleNamespace(
                        type="tool_use",
                        name="submit_510880_strategy_mapping",
                        input={"mappings": [], "line_coverage": []},
                    )],
                )
                return _FakeMessageStream(final)

        client = SimpleNamespace(messages=Messages())

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    app = FastAPI()
    app.include_router(
        create_card020_router(type("DB", (), {"conn": connection})(), llm_client=MaxTokensClient())
    )
    client = TestClient(app)
    source_text, protocol_hash = card020_api._read_protocol()

    response = client.post("/api/research/card020/parse", json={"source_text": source_text})

    assert response.status_code == 200
    saved = response.json()
    assert saved["status"] == "blocked"
    assert any("tool_use" in reason for reason in saved["result"]["blocking_reasons"])
    assert saved["result"]["call_diagnostic"]["stop_reason"] == "max_tokens"
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper()
    assert saved["result"]["source_sha256"] == saved["source_sha256"] == source_hash

    restored = client.get("/api/research/card020/state").json()["latest_parse"]
    assert restored["parse_id"] == saved["parse_id"]
    assert restored["status"] == "blocked"
    assert restored["result"]["source_sha256"] == source_hash
    assert hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper() == restored["result"]["source_sha256"]

    store = Card020Store(connection)
    try:
        store.freeze_parse(
            saved["parse_id"], "unused-preflight", True, saved["source_sha256"], protocol_hash,
        )
    except Card020Conflict as exc:
        assert str(exc) == "parse_not_ready"
    else:
        raise AssertionError("max_tokens response was accepted for freeze")
    assert store.get_frozen() is None
    connection.close()


def _seed_frozen_strategy(store: Card020Store) -> tuple[dict, dict]:
    fingerprint = _code_fingerprint()
    source_text = "synthetic frozen Card020 source"
    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper()
    parse = store.record_parse(
        protocol_sha256=PROTOCOL_SHA256,
        source_text=source_text,
        result={
            "status": "ready_for_confirmation",
            "source_sha256": source_sha256,
            "fields": {"strategy_id": "510880-vol-budget-v1"},
            "source_mappings": [{
                "field": "strategy_id", "source_line_numbers": [1], "source_quotes": [source_text],
            }],
            "line_coverage": [{"line_number": 1, "classification": "mapped_rule"}],
            "parser_sha256": fingerprint["files"]["backend/services/strategy_idea_flow.py"],
        },
        status="ready_for_confirmation",
    )
    preflight = store.record_preflight({
        "preflight_id": "card020-api-hash-preflight",
        "status": "passed_with_disclosed_data_limits",
        "strategy_id": "510880-vol-budget-v1",
        "protocol_sha256": PROTOCOL_SHA256,
        "input_inventory_sha256": "a" * 64,
        "input_inventory": {"source_status": "synthetic_test_input"},
        "execution_fingerprint": fingerprint,
        "critical_source_gaps": [],
        "data_limitations": ["synthetic test input"],
        "evidence_level": "low",
        "historical_metrics_computed": False,
    })
    frozen = store.freeze_parse(
        parse["parse_id"], preflight["preflight_id"], True, source_sha256, PROTOCOL_SHA256,
    )
    return frozen, preflight


def test_saved_run_result_hash_survives_api_persistence_and_readback(monkeypatch, tmp_path):
    database_path = tmp_path / "card020.sqlite3"
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    store = Card020Store(connection)
    frozen, preflight = _seed_frozen_strategy(store)
    monkeypatch.setattr(
        card020_api,
        "prepare_card020_inputs",
        lambda: {
            "preflight": preflight,
            "market": object(),
            "calendar": object(),
            "dividend_events": [],
            "data_provenance": {"source_status": "synthetic_test_input"},
        },
    )

    def synthetic_runner(frozen_input, **_kwargs):
        result = {
            "freeze_id": frozen_input["freeze_id"],
            "evaluation_category": "D",
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
        }
        result["result_sha256"] = _json_sha256(result)
        return result

    app = FastAPI()
    app.include_router(
        create_card020_router(type("DB", (), {"conn": connection})(), runner=synthetic_runner)
    )
    client = TestClient(app)

    response = client.post(
        "/api/research/card020/run",
        json={"freeze_id": frozen["freeze_id"], "idempotency_key": "hash-readback-001"},
    )

    assert response.status_code == 200, response.text
    run_record = response.json()
    assert run_record["run_id"]
    recovered = client.get(f"/api/research/card020/runs/{run_record['run_id']}").json()
    persisted_result = recovered["result"]
    assert "run_id" not in persisted_result
    assert persisted_result["result_sha256"] == _json_sha256(persisted_result)

    connection.close()
    reopened = Card020Store(sqlite3.connect(str(database_path), check_same_thread=False))
    restarted_result = reopened.get_run(run_record["run_id"])["result"]
    assert restarted_result["result_sha256"] == _json_sha256(restarted_result)
    reopened.connection.close()
