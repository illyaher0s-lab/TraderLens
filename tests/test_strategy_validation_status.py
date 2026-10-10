import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import strategy_validations


def _audit_payload():
    return {
        "status": "hard_block:b5_validation_inputs_missing",
        "reason": "hard_block:b5_validation_inputs_missing",
        "first_missing_prerequisite": "b5_validation_inputs",
        "missing_b5_validation_inputs": [
            "base_cost",
            "stress_cost",
            "benchmark_comparison",
            "same_universe_control_comparison",
        ],
        "b4_artifact": {
            "artifact_id": "20960e9fd15cdb44",
            "qualification_status": "pass",
            "canary_blocked_count": 6,
            "future_violations": 0,
            "oos_read_count": 0,
            "max_requested_date": "2026-03-19",
            "is_range": {"start": "2025-06-27", "end": "2026-03-19"},
            "supplement_id": "680cd55c91254667",
            "protocol_snapshot_id": "protocol-1",
            "strategy_revision_id": "revision-1",
        },
    }


def _write_audit(tmp_path, payload=None):
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps(payload or _audit_payload(), sort_keys=True), encoding="utf-8"
    )
    return path


def test_valid_audit_maps_to_non_actionable_watch_status(tmp_path):
    path = _write_audit(tmp_path)

    status = strategy_validations.load_strategy_validation_status(path)

    assert status["status"] == "watch"
    assert status["actionable"] is False
    assert status["candidate_is_signal"] is False
    assert status["reason_code"] == "hard_block:b5_validation_inputs_missing"
    assert status["missing"] == _audit_payload()["missing_b5_validation_inputs"]
    assert status["b4_summary"]["artifact_id"] == "20960e9fd15cdb44"
    assert "signal" not in status
    assert "action_plan" not in status


def test_missing_or_unknown_audit_is_fail_safe_unavailable(tmp_path):
    missing = strategy_validations.load_strategy_validation_status(tmp_path / "missing.json")
    assert missing["status"] == "unavailable"
    assert missing["actionable"] is False
    assert missing["candidate_is_signal"] is False

    unknown_payload = _audit_payload()
    unknown_payload["status"] = "no_signal"
    unknown = strategy_validations.load_strategy_validation_status(
        _write_audit(tmp_path, unknown_payload)
    )
    assert unknown["status"] == "unavailable"
    assert unknown["actionable"] is False


def test_tampered_audit_is_fail_safe_with_injected_expected_hash(tmp_path):
    path = _write_audit(tmp_path)
    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = _audit_payload()
    payload["missing_b5_validation_inputs"] = ["base_cost"]
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    status = strategy_validations.load_strategy_validation_status(
        path, expected_sha256=expected_hash
    )

    assert status["status"] == "unavailable"
    assert status["actionable"] is False


def test_strategy_validation_endpoint_exposes_status_without_signal_fields(tmp_path, monkeypatch):
    path = _write_audit(tmp_path)
    monkeypatch.setattr(
        strategy_validations,
        "DEFAULT_AUDIT_PATH",
        path,
    )

    response = strategy_validations.list_validations()

    assert response["validations"] == []
    assert response["count"] == 0
    assert response["validation_status"]["status"] == "watch"
    assert response["validation_status"]["actionable"] is False
    assert "signals" not in response["validation_status"]
    assert "action_plan" not in response["validation_status"]


def test_strategy_validation_http_endpoint_is_read_only_and_non_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(strategy_validations, "DEFAULT_AUDIT_PATH", _write_audit(tmp_path))
    app = FastAPI()
    app.include_router(strategy_validations.router)

    response = TestClient(app).get("/api/strategy-validations")

    assert response.status_code == 200
    body = response.json()
    assert body["validation_status"]["status"] == "watch"
    assert body["validation_status"]["actionable"] is False
    assert body["validation_status"]["candidate_is_signal"] is False
    assert "signal" not in body["validation_status"]
    assert "action_plan" not in body["validation_status"]
