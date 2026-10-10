"""Read-only user-facing status projection for the current strategy audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "verification"
    / "task4_v3_one_shot_audit.json"
)
PRODUCTION_AUDIT_SHA256 = "db67a92283867f311f5758ccb6e9b18f45d8fdde14980b4e88f87ed1a35be78b"
EXPECTED_STATUS = "hard_block:b5_validation_inputs_missing"
EXPECTED_FIRST_MISSING = "b5_validation_inputs"
EXPECTED_MISSING = (
    "base_cost",
    "stress_cost",
    "benchmark_comparison",
    "same_universe_control_comparison",
)


def _unavailable() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "user_facing_level": "unavailable",
        "actionable": False,
        "candidate_is_signal": False,
        "reason_code": "validation_status_unavailable",
        "title": "策略验证状态暂不可用",
        "message": "暂时无法确认策略验证状态，当前不能作为买卖依据。",
        "missing": [],
        "b4_verified": False,
        "b4_summary": None,
        "audit_sha256": None,
    }


def _valid_b4_summary(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = (
        "artifact_id",
        "qualification_status",
        "canary_blocked_count",
        "future_violations",
        "oos_read_count",
        "max_requested_date",
        "is_range",
        "supplement_id",
        "protocol_snapshot_id",
        "strategy_revision_id",
    )
    if any(key not in value or value[key] in (None, "") for key in required):
        return False
    if value["qualification_status"] != "pass":
        return False
    if value["canary_blocked_count"] != 6:
        return False
    if value["future_violations"] != 0 or value["oos_read_count"] != 0:
        return False
    date_range = value["is_range"]
    return (
        isinstance(date_range, dict)
        and isinstance(date_range.get("start"), str)
        and isinstance(date_range.get("end"), str)
    )


def load_strategy_validation_status(
    audit_path: str | Path | None = None,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Project a verified audit into a non-actionable UI status.

    An injected path is intended for tests. Production's default path is
    additionally bound to the currently verified audit hash.
    """
    path = Path(audit_path) if audit_path is not None else DEFAULT_AUDIT_PATH
    expected = expected_sha256
    if audit_path is None and expected is None:
        expected = PRODUCTION_AUDIT_SHA256

    try:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            return _unavailable()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return _unavailable()
        if payload.get("status") != EXPECTED_STATUS:
            return _unavailable()
        if payload.get("reason") != EXPECTED_STATUS:
            return _unavailable()
        if payload.get("first_missing_prerequisite") != EXPECTED_FIRST_MISSING:
            return _unavailable()
        if tuple(payload.get("missing_b5_validation_inputs", ())) != EXPECTED_MISSING:
            return _unavailable()
        b4 = payload.get("b4_artifact")
        if not _valid_b4_summary(b4):
            return _unavailable()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return _unavailable()

    return {
        "status": "watch",
        "user_facing_level": "watch",
        "actionable": False,
        "candidate_is_signal": False,
        "reason_code": EXPECTED_STATUS,
        "title": "策略验证暂不可执行",
        "message": "策略历史回测已完成，但成本压力、市场基准和同股票池对照尚未完成，因此当前不能作为买卖依据。",
        "missing": list(EXPECTED_MISSING),
        "b4_verified": True,
        "b4_summary": {
            "artifact_id": b4["artifact_id"],
            "supplement_id": b4["supplement_id"],
            "protocol_snapshot_id": b4["protocol_snapshot_id"],
            "strategy_revision_id": b4["strategy_revision_id"],
            "is_range": b4["is_range"],
            "future_violations": b4["future_violations"],
            "oos_read_count": b4["oos_read_count"],
        },
        "audit_sha256": digest,
    }
