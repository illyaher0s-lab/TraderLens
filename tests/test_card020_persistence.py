from __future__ import annotations

import hashlib
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.card020 import PROTOCOL_SHA256, create_card020_router
from backend.services.card020_preflight import EXECUTOR_VERSION, _code_fingerprint
from backend.services.card020_store import Card020Store


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.model = "test-model"
        self.client = SimpleNamespace(messages=self)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        final_message = SimpleNamespace(
            id="test-stream-response",
            model="test-model",
            stop_reason="tool_use",
            content=[SimpleNamespace(
                type="tool_use",
                name="submit_510880_strategy_mapping",
                input={"mappings": [], "line_coverage": []},
            )],
        )

        class FakeStream:
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
                return final_message

            def close(self):
                return None

        return FakeStream()


def test_parse_route_accepts_only_line_ending_normalization_and_keeps_hashes_separate():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    client_llm = FakeLLM()
    app = FastAPI()
    app.include_router(create_card020_router(type("DB", (), {"conn": connection})(), client_llm))
    client = TestClient(app)

    protocol = client.get("/api/research/card020/protocol").json()
    canonical = protocol["source_text"]
    submitted = canonical.replace("\r\n", "\n")
    result = client.post("/api/research/card020/parse", json={"source_text": submitted}).json()

    assert protocol["protocol_sha256"] == PROTOCOL_SHA256
    assert result["status"] == "blocked"  # Fake output lacks complete field/line mappings.
    assert result["source_sha256"] == hashlib.sha256(submitted.encode("utf-8")).hexdigest().upper()
    assert result["protocol_sha256"] == protocol["protocol_sha256"]
    assert len(client_llm.calls) == 1

    edited = submitted + "\n加杠杆"
    rejected = client.post("/api/research/card020/parse", json={"source_text": edited}).json()
    assert rejected["status"] == "blocked"
    assert "CRLF/LF" in rejected["result"]["blocking_reasons"][0]
    assert len(client_llm.calls) == 1


def test_confirmed_freeze_and_completed_run_survive_connection_restart(tmp_path):
    path = tmp_path / "research.sqlite3"
    connection = sqlite3.connect(str(path), check_same_thread=False)
    store = Card020Store(connection)
    source = "fixed protocol source"
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    fingerprint = _code_fingerprint()
    parse = store.record_parse(
        protocol_sha256=PROTOCOL_SHA256,
        source_text=source,
        result={
            "status": "ready_for_confirmation",
            "source_sha256": source_hash,
            "fields": {"strategy_id": "510880-vol-budget-v1"},
            "source_mappings": [{"field": "strategy_id", "source_line_numbers": [1], "source_quotes": ["fixed"]}],
            "line_coverage": [{"line_number": 1, "classification": "mapped_rule"}],
            "parser_sha256": fingerprint["files"]["backend/services/strategy_idea_flow.py"],
        },
        status="ready_for_confirmation",
    )
    preflight = store.record_preflight({
        "preflight_id": "preflight-test-001",
        "status": "passed_with_disclosed_data_limits",
        "strategy_id": "510880-vol-budget-v1",
        "protocol_sha256": PROTOCOL_SHA256,
        "input_inventory_sha256": "b" * 64,
        "input_inventory": {"market": {"source_status": "downloaded_unverified_for_research_use"}},
        "execution_fingerprint": fingerprint,
        "critical_source_gaps": [],
        "data_limitations": ["provider-origin authentication is not established"],
        "evidence_level": "low",
        "historical_metrics_computed": False,
    })
    with pytest.raises(ValueError, match="confirmation_required"):
        store.freeze_parse(parse["parse_id"], preflight["preflight_id"], False, source_hash, PROTOCOL_SHA256)
    with pytest.raises(ValueError, match="source_hash_mismatch"):
        store.freeze_parse(parse["parse_id"], preflight["preflight_id"], True, "0" * 64, PROTOCOL_SHA256)

    frozen = store.freeze_parse(
        parse["parse_id"], preflight["preflight_id"], True, source_hash, PROTOCOL_SHA256,
    )
    assert frozen["source_sha256"] == source_hash
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE card020_frozen_strategies SET source_text = 'changed' WHERE freeze_id = ?",
            (frozen["freeze_id"],),
        )
    connection.rollback()

    claimed, run = store.begin_run(frozen["freeze_id"], "card020-idempotency-test-001")
    assert claimed is True
    saved = store.finish_run(run["run_id"], result={"evaluation_category": "D", "result_sha256": "r"})
    assert saved["status"] == "completed"
    duplicate, same = store.begin_run(frozen["freeze_id"], "card020-idempotency-test-001")
    assert duplicate is False
    assert same["run_id"] == run["run_id"]
    with pytest.raises(ValueError, match="freeze_already_run"):
        store.begin_run(frozen["freeze_id"], "card020-idempotency-test-002")

    connection.close()
    reopened = sqlite3.connect(str(path), check_same_thread=False)
    recovered = Card020Store(reopened)
    assert recovered.get_frozen(frozen["freeze_id"])["freeze_sha256"] == frozen["freeze_sha256"]
    assert recovered.get_run(run["run_id"])["result"]["result_sha256"] == "r"
    with pytest.raises(ValueError, match="freeze_already_run"):
        recovered.begin_run(frozen["freeze_id"], "card020-new-key-after-restart")
    reopened.close()


def test_running_or_failed_batch_cannot_be_restarted_with_a_new_key(tmp_path):
    path = tmp_path / "interrupted.sqlite3"
    connection = sqlite3.connect(str(path), check_same_thread=False)
    store = Card020Store(connection)
    fingerprint = _code_fingerprint()
    source = "protocol source for interrupted test"
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    preflight = store.record_preflight({
        "preflight_id": "preflight-interrupted-001",
        "status": "passed_with_disclosed_data_limits",
        "strategy_id": "510880-vol-budget-v1",
        "protocol_sha256": PROTOCOL_SHA256,
        "input_inventory_sha256": "e" * 64,
        "input_inventory": {"market": {"snapshot_id": "fixed-test"}},
        "execution_fingerprint": fingerprint,
        "critical_source_gaps": [],
        "data_limitations": ["provider-origin authentication is not established"],
        "evidence_level": "low",
        "historical_metrics_computed": False,
    })
    parse = store.record_parse(
        protocol_sha256=PROTOCOL_SHA256,
        source_text=source,
        result={
            "status": "ready_for_confirmation", "source_sha256": source_hash,
            "parser_sha256": fingerprint["files"]["backend/services/strategy_idea_flow.py"],
            "fields": {"strategy_id": "510880-vol-budget-v1"},
            "source_mappings": [], "line_coverage": [],
        },
        status="ready_for_confirmation",
    )
    frozen = store.freeze_parse(
        parse["parse_id"], preflight["preflight_id"], True, source_hash, PROTOCOL_SHA256,
    )
    _claimed, run = store.begin_run(frozen["freeze_id"], "card020-interrupted-key-001")
    connection.close()  # Simulate process exit with a persisted running claim.

    reopened = sqlite3.connect(str(path), check_same_thread=False)
    recovered = Card020Store(reopened)
    assert recovered.get_run(run["run_id"])["status"] == "running"
    with pytest.raises(ValueError, match="freeze_already_run"):
        recovered.begin_run(frozen["freeze_id"], "card020-interrupted-new-key")
    recovered.finish_run(run["run_id"], result=None, error_code="deterministic_run_failed")
    with pytest.raises(ValueError, match="freeze_already_run"):
        recovered.begin_run(frozen["freeze_id"], "card020-failed-new-key")
    reopened.close()
