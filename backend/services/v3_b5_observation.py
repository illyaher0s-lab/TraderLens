"""Narrow v3-only daily observation contract and artifact boundary."""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import date
from numbers import Real
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "v3_b5_instrumented_is_observation.v1"
IS_START = date(2025, 6, 27)
IS_END = date(2026, 3, 19)
OOS_START = date(2026, 3, 20)
OBSERVATION_FIELDS = (
    "date",
    "cash",
    "portfolio_value",
    "gross_exposure",
    "net_exposure",
    "positions_value",
    "daily_return",
    "position_values_by_symbol",
)
# Compatibility name used by the initial Task 3 RED contract.
DAILY_OBSERVATION_FIELDS = OBSERVATION_FIELDS
EVENT_EQUIVALENCE_FIELDS = (
    "result_id",
    "strategy_revision_id",
    "protocol_snapshot_id",
    "evaluation_mode",
    "backtest_start",
    "backtest_end",
    "order_intents",
    "fills",
    "rejected_orders",
    "future_violations",
    "final_portfolio",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    actual = _sha(path)
    sidecar = Path(path).with_name(Path(path).name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise ValueError(f"sidecar mismatch: {path}")
    return actual


def _parse_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, type(None)):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid observation date: {value}") from exc
    raise ValueError("observation date must be ISO date")


def _finite_number(value: object, field: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} must be finite numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite numeric")
    if non_negative and number < 0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-8)


def _normalize_observations(
    observations: object,
    *,
    allowed_end: date,
    expected_dates: tuple[date, ...] | None = None,
) -> list[dict[str, object]]:
    if not isinstance(observations, (list, tuple)) or not observations:
        raise ValueError("observations must be a non-empty list")

    normalized: list[dict[str, object]] = []
    previous_date: date | None = None
    previous_value: float | None = None
    seen: set[date] = set()
    for index, raw in enumerate(observations):
        if not isinstance(raw, Mapping) or set(raw) != set(OBSERVATION_FIELDS):
            raise ValueError("observation fields mismatch")
        current_date = _parse_date(raw["date"])
        if current_date > allowed_end or current_date >= OOS_START:
            raise ValueError(f"future/OOS observation date: {current_date}")
        if current_date in seen:
            raise ValueError(f"duplicate observation date: {current_date}")
        if previous_date is not None and current_date <= previous_date:
            raise ValueError("observation dates must be strictly ordered")
        seen.add(current_date)

        cash = _finite_number(raw["cash"], "cash", non_negative=True)
        portfolio_value = _finite_number(raw["portfolio_value"], "portfolio_value", non_negative=True)
        gross_exposure = _finite_number(raw["gross_exposure"], "gross_exposure", non_negative=True)
        net_exposure = _finite_number(raw["net_exposure"], "net_exposure", non_negative=True)
        positions_value = _finite_number(raw["positions_value"], "positions_value", non_negative=True)
        daily_return = _finite_number(raw["daily_return"], "daily_return")

        position_values = raw["position_values_by_symbol"]
        if not isinstance(position_values, Mapping):
            raise ValueError("position_values_by_symbol must be an object")
        normalized_values: dict[str, float] = {}
        for symbol, value in position_values.items():
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("position symbol must be non-empty")
            normalized_values[symbol] = _finite_number(value, "position value", non_negative=True)
        value_sum = sum(normalized_values.values())
        if not _close(value_sum, positions_value):
            raise ValueError("positions arithmetic mismatch")
        if not _close(gross_exposure, positions_value) or not _close(net_exposure, positions_value):
            raise ValueError("exposure arithmetic mismatch")
        if not _close(cash + positions_value, portfolio_value):
            raise ValueError("portfolio arithmetic mismatch")

        if index == 0:
            if not _close(daily_return, 0.0):
                raise ValueError("first daily_return must be 0.0")
        else:
            assert previous_value is not None
            if previous_value <= 0:
                raise ValueError("previous portfolio value must be positive")
            expected_return = portfolio_value / previous_value - 1.0
            if not _close(daily_return, expected_return):
                raise ValueError("daily_return arithmetic mismatch")

        normalized.append(
            {
                "date": current_date.isoformat(),
                "cash": cash,
                "portfolio_value": portfolio_value,
                "gross_exposure": gross_exposure,
                "net_exposure": net_exposure,
                "positions_value": positions_value,
                "daily_return": daily_return,
                "position_values_by_symbol": dict(sorted(normalized_values.items())),
            }
        )
        previous_date = current_date
        previous_value = portfolio_value

    actual_dates = tuple(_parse_date(item["date"]) for item in normalized)
    if expected_dates is not None and actual_dates != tuple(expected_dates):
        raise ValueError("observation date sequence mismatch")
    return normalized


def validate_observation_payload(
    observations: object,
    *,
    allowed_end: date,
    expected_dates: tuple[date, ...] | None = None,
) -> dict[str, object]:
    normalized = _normalize_observations(
        observations, allowed_end=allowed_end, expected_dates=expected_dates
    )
    return {
        "status": "valid",
        "observation_count": len(normalized),
        "start": normalized[0]["date"],
        "end": normalized[-1]["date"],
    }


def normalize_observation_payload(
    observations: object,
    *,
    allowed_end: date,
    expected_dates: tuple[date, ...] | None = None,
) -> list[dict[str, object]]:
    return _normalize_observations(
        observations, allowed_end=allowed_end, expected_dates=expected_dates
    )


def validate_event_for_daily_comparison(payload: Mapping[str, object]) -> dict[str, object]:
    if "daily_portfolio_observations" not in payload:
        return {"status": "invalid", "reason": "daily_portfolio_observations_missing"}
    try:
        end = _parse_date(payload.get("backtest_end", IS_END.isoformat()))
        result = validate_observation_payload(
            payload["daily_portfolio_observations"], allowed_end=end
        )
        return result
    except (TypeError, ValueError) as exc:
        return {"status": "invalid", "reason": str(exc)}


def event_equivalence_projection(payload: Mapping[str, object]) -> dict[str, object]:
    """Compare all trading fields; only frozen_at is explicitly excluded."""
    return {field: payload[field] for field in EVENT_EQUIVALENCE_FIELDS}


def _write_once_json(path: Path, raw: bytes) -> None:
    path = Path(path)
    sidecar = path.with_name(path.name + ".sha256")
    if path.exists() or sidecar.exists():
        if not path.exists() or not sidecar.exists() or path.read_bytes() != raw or sidecar.read_text(encoding="utf-8").split()[0] != _sha_bytes(raw):
            raise ValueError(f"observation artifact write-once conflict: {path}")
        return
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        sidecar.write_text(_sha_bytes(raw) + f"  {path.name}\n", encoding="utf-8")
    finally:
        if temp.exists():
            temp.unlink()


def publish_instrumented_is_artifact(
    *,
    output_root: Path,
    manifest_payload: Mapping[str, object],
    event_result: Mapping[str, object],
    observations: object,
    expected_dates: tuple[date, ...],
) -> dict[str, object]:
    normalized = normalize_observation_payload(
        observations, allowed_end=IS_END, expected_dates=expected_dates
    )
    event_raw = _canonical(dict(event_result))
    observation_raw = _canonical(normalized)
    payload = {
        **dict(manifest_payload),
        "schema_version": SCHEMA,
        "status": "valid",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "event_result": {
            "path": "event_result.json",
            "sha256": _sha_bytes(event_raw),
            "canonical_hash": _sha_bytes(event_raw),
            "result_id": event_result.get("result_id"),
        },
        "observations": {
            "path": "observations.json",
            "sha256": _sha_bytes(observation_raw),
            "canonical_hash": _sha_bytes(observation_raw),
            "count": len(normalized),
            "start": normalized[0]["date"],
            "end": normalized[-1]["date"],
        },
    }
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    manifest = {**payload, "artifact_id": artifact_id}
    manifest_raw = _canonical(manifest)
    target = Path(output_root) / artifact_id
    if target.exists():
        expected = {
            target / "manifest.json": manifest_raw,
            target / "event_result.json": event_raw,
            target / "observations.json": observation_raw,
        }
        for path, raw in expected.items():
            if not path.exists() or path.read_bytes() != raw or _sidecar_hash(path) != _sha_bytes(raw):
                raise ValueError("instrumented observation write-once conflict")
        return {
            "status": "already_published",
            "artifact_id": artifact_id,
            "path": str(target),
            "manifest_sha256": _sha_bytes(manifest_raw),
            "event_result_sha256": _sha_bytes(event_raw),
            "observation_sha256": _sha_bytes(observation_raw),
        }

    target.mkdir(parents=True, exist_ok=False)
    _write_once_json(target / "event_result.json", event_raw)
    _write_once_json(target / "observations.json", observation_raw)
    _write_once_json(target / "manifest.json", manifest_raw)
    return {
        "status": "published",
        "artifact_id": artifact_id,
        "path": str(target),
        "manifest_sha256": _sha_bytes(manifest_raw),
        "event_result_sha256": _sha_bytes(event_raw),
        "observation_sha256": _sha_bytes(observation_raw),
    }


def verify_instrumented_is_artifact(
    artifact_dir: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, object]:
    try:
        repo_root = Path(repo_root).resolve()
        artifact_dir = Path(artifact_dir).resolve()
        manifest_path = artifact_dir / "manifest.json"
        event_path = artifact_dir / "event_result.json"
        observation_path = artifact_dir / "observations.json"
        manifest_hash = _sidecar_hash(manifest_path)
        event_hash = _sidecar_hash(event_path)
        observation_hash = _sidecar_hash(observation_path)
        manifest = _read_json(manifest_path)
        event_json = _read_json(event_path)
        observations = json.loads(observation_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "valid":
            raise ValueError("instrumented observation schema/status mismatch")
        if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
            raise ValueError("instrumented observation authorization disclosure mismatch")
        payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
        if manifest.get("artifact_id") != _sha_bytes(_canonical(payload))[:16]:
            raise ValueError("instrumented observation artifact identity mismatch")
        if manifest["event_result"]["sha256"] != event_hash or manifest["event_result"]["canonical_hash"] != _sha_bytes(_canonical(event_json)):
            raise ValueError("instrumented event hash mismatch")
        observation_raw = _canonical(observations)
        if manifest["observations"]["sha256"] != observation_hash or manifest["observations"]["canonical_hash"] != _sha_bytes(observation_raw):
            raise ValueError("instrumented observation hash mismatch")

        from backend.services.b4_protocol_types import EventBacktestResult
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        event = EventBacktestResult.model_validate(event_json)
        expected_dates = FormalPITPartitionAdapter(repo_root).common_trading_dates(IS_START, IS_END)
        validate_observation_payload(
            observations, allowed_end=IS_END, expected_dates=expected_dates
        )
        if event.strategy_revision_id != manifest["identity"]["strategy_revision_id"] or event.protocol_snapshot_id != manifest["identity"]["protocol_snapshot_id"]:
            raise ValueError("instrumented event identity mismatch")
        if event.backtest_start != IS_START or event.backtest_end != IS_END or event.future_violations:
            raise ValueError("instrumented event IS/future binding mismatch")

        for relative, declared in manifest["producer_source_hashes"].items():
            source_path = repo_root / relative
            if _sha(source_path) != declared:
                raise ValueError(f"instrumented producer source hash mismatch: {relative}")

        predecessor = manifest["lineage"]["trading_result_predecessor"]
        predecessor_manifest_path = repo_root / predecessor["manifest_path"]
        predecessor_event_path = repo_root / predecessor["event_result_path"]
        if _sidecar_hash(predecessor_manifest_path) != predecessor["manifest_sha256"] or _sidecar_hash(predecessor_event_path) != predecessor["event_result_sha256"]:
            raise ValueError("B4 predecessor hash mismatch")
        predecessor_manifest = _read_json(predecessor_manifest_path)
        predecessor_event = _read_json(predecessor_event_path)
        if predecessor_manifest.get("artifact_id") != "20960e9fd15cdb44" or predecessor_manifest.get("supplement", {}).get("supplement_id") != "680cd55c91254667":
            raise ValueError("B4 predecessor identity mismatch")
        if event_equivalence_projection(event_json) != event_equivalence_projection(predecessor_event):
            raise ValueError("instrumented trading result equivalence mismatch")

        read_audit = manifest["read_audit"]
        if read_audit.get("oos_read_count") != 0 or read_audit.get("max_requested_date") not in (None, IS_END.isoformat()):
            raise ValueError("instrumented read audit OOS/future mismatch")
        return {
            "status": "verified",
            "artifact_id": manifest["artifact_id"],
            "manifest_sha256": manifest_hash,
            "event_result_sha256": event_hash,
            "observation_sha256": observation_hash,
            "observation_count": len(observations),
            "equivalence_fields": list(EVENT_EQUIVALENCE_FIELDS),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": str(exc)}
