"""V3-only base and transaction-cost stress calculations for the B4 fill ledger."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.v3_b5_bundle import build_lineage
from backend.services.v3_b5_ledger_observation import sha256_file
from backend.services.v3_b5_types import (
    build_result_payload,
    canonical_json,
    sha256_bytes,
    validate_result_payload,
)
from strategy_core.transaction_costs import calculate_transaction_costs


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "data/pit/v3_b5_costs"
SCHEMA = "v3_b5_costs.v1"
B4_ID = "958bb9717edd08a9"
B4_MANIFEST_SHA = "af9ebfbcda0eff795efc4ef26688f57286886206e1e6dfe1699a90a197f8b7c2"
B4_EVENT_SHA = "374479e9df35c80c680adfe34fe95d10a78eb4d049a24fc6bc43cfb3aa0bf1cc"
SUPPLEMENT_ID = "d1134e96d6b2ec1b"
SUPPLEMENT_MANIFEST_SHA = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
OBSERVATION_ID = "f28096063549c23f"
OBSERVATION_MANIFEST_SHA = "32dbd944992c71ce39bad5d856a3ec07529852fbb8e2022f72287d23bc38632c"
OBSERVATION_SHA = "55373c7e7c189663241f48d37b35505f99284d20c7eb07d85b7dec8a0208f842"
IS_RANGE = {"start": "2025-06-27", "end": "2026-03-19"}

ASSUMPTIONS = {
    "base": {
        "commission_rate": 0.0003,
        "minimum_commission": 5.0,
        "sell_stamp_duty": 0.001,
        "transfer_fee_rate": 0.0,
        "slippage_bps": 0.0,
        "impact_bps": 0.0,
    },
    "stress": {
        "commission_rate": 0.0006,
        "minimum_commission": 5.0,
        "sell_stamp_duty": 0.001,
        "transfer_fee_rate": 0.0,
        "slippage_bps": 10.0,
        "impact_bps": 0.0,
        "price_multiplier_buy": 1.001,
        "price_multiplier_sell": 0.999,
        "stress_multiplier": 2.0,
    },
    "denominator": "sum(abs(fill_quantity * immutable_base_fill_price))",
    "impact_model": "none",
    "algorithm": "v3_b5_transaction_costs_v1",
}
COST_ASSUMPTIONS_HASH = sha256_bytes(canonical_json(ASSUMPTIONS))


class CostCalculationError(ValueError):
    """A fill ledger violates the frozen v3 cost contract."""


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    actual = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise CostCalculationError(f"sidecar mismatch: {path}")
    return actual


def _load_b4(repo_root: Path) -> tuple[dict[str, Any], EventBacktestResult]:
    directory = Path(repo_root) / "data/pit/v3_b4_is_results" / B4_ID
    manifest_path = directory / "manifest.json"
    event_path = directory / "event_result.json"
    if _sidecar_hash(manifest_path) != B4_MANIFEST_SHA or _sidecar_hash(event_path) != B4_EVENT_SHA:
        raise CostCalculationError("B4 predecessor hash mismatch")
    manifest = _read_json(manifest_path)
    event = EventBacktestResult.model_validate(_read_json(event_path))
    if manifest.get("artifact_id") != B4_ID:
        raise CostCalculationError("B4 predecessor identity mismatch")
    if manifest.get("supplement", {}).get("supplement_id") != SUPPLEMENT_ID:
        raise CostCalculationError("B4 predecessor supplement mismatch")
    if event.backtest_start.isoformat() != IS_RANGE["start"] or event.backtest_end.isoformat() != IS_RANGE["end"]:
        raise CostCalculationError("B4 predecessor IS range mismatch")
    if event.future_violations:
        raise CostCalculationError("B4 predecessor contains future violations")
    return manifest, event


def _static_observation_lineage(repo_root: Path, observation_dir: Path | None = None) -> dict[str, Any]:
    directory = Path(observation_dir) if observation_dir is not None else Path(repo_root) / "data/pit/v3_b5_ledger_observations" / OBSERVATION_ID
    manifest_path = directory / "manifest.json"
    observations_path = directory / "observations.json"
    if _sidecar_hash(manifest_path) != OBSERVATION_MANIFEST_SHA:
        raise CostCalculationError("ledger observation manifest hash mismatch")
    observation_sha = _sidecar_hash(observations_path)
    if observation_sha != OBSERVATION_SHA:
        raise CostCalculationError("ledger observation content hash mismatch")
    manifest = _read_json(manifest_path)
    if (
        manifest.get("artifact_id") != OBSERVATION_ID
        or manifest.get("schema_version") != "v3_b5_ledger_observations.v1"
        or manifest.get("status") != "valid"
        or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True
    ):
        raise CostCalculationError("ledger observation static status/identity mismatch")
    if manifest.get("observations", {}).get("sha256") != OBSERVATION_SHA or manifest.get("observations", {}).get("count") != 176:
        raise CostCalculationError("ledger observation static summary mismatch")
    lineage = manifest.get("lineage", {})
    if lineage.get("b4", {}).get("artifact_id") != B4_ID or lineage.get("b4", {}).get("manifest_sha256") != B4_MANIFEST_SHA or lineage.get("b4", {}).get("event_sha256") != B4_EVENT_SHA:
        raise CostCalculationError("ledger observation B4 lineage mismatch")
    if lineage.get("trading_supplement", {}).get("supplement_id") != SUPPLEMENT_ID or lineage.get("trading_supplement", {}).get("manifest_sha256") != SUPPLEMENT_MANIFEST_SHA:
        raise CostCalculationError("ledger observation supplement lineage mismatch")
    return {
        "artifact_id": OBSERVATION_ID,
        "manifest_sha256": OBSERVATION_MANIFEST_SHA,
        "observations_sha256": OBSERVATION_SHA,
        "observation_count": 176,
    }


def _source_bindings(repo_root: Path) -> dict[str, dict[str, str]]:
    root = Path(repo_root)
    paths = {
        "cost_service": root / "backend/services/v3_b5_costs.py",
        "publisher": root / "scripts/publish_v3_b5_costs.py",
        "verifier": root / "scripts/verify_v3_b5_costs.py",
        "transaction_costs": root / "strategy_core/transaction_costs.py",
    }
    result = {}
    for name, path in paths.items():
        if not path.exists():
            raise CostCalculationError(f"producer source missing: {path}")
        result[name] = {"path": path.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256_file(path)}
    return result


def _validate_event(event: EventBacktestResult) -> dict[str, Any]:
    if not event.fills:
        raise CostCalculationError("empty fill ledger")
    intents = {item.order_id: item for item in event.order_intents}
    if len(intents) != len(event.order_intents):
        raise CostCalculationError("duplicate order intent identity")
    fill_ids = [item.fill_id for item in event.fills]
    if len(set(fill_ids)) != len(fill_ids):
        raise CostCalculationError("duplicate fill identity")
    if fill_ids != list(dict.fromkeys(fill_ids)):
        raise CostCalculationError("fill identity order is not deterministic")
    for fill in event.fills:
        intent = intents.get(fill.order_id)
        if intent is None or intent.symbol != fill.symbol or intent.intent not in {"buy", "sell"}:
            raise CostCalculationError(f"missing or conflicting fill direction: {fill.fill_id}")
        if intent.quantity < fill.fill_quantity:
            raise CostCalculationError(f"fill quantity exceeds intent: {fill.fill_id}")
        if not _finite(fill.fill_price) or float(fill.fill_price) <= 0 or fill.fill_quantity <= 0:
            raise CostCalculationError(f"invalid fill: {fill.fill_id}")
        if fill.fill_date.isoformat() < IS_RANGE["start"] or fill.fill_date.isoformat() > IS_RANGE["end"]:
            raise CostCalculationError(f"fill outside IS: {fill.fill_id}")
    return intents


def _bps(value: float, denominator: float) -> float:
    return value / denominator * 10000.0


def _aggregate(rows: list[dict[str, Any]], denominator: float, *, stress: bool) -> dict[str, Any]:
    fields = ("commission", "stamp", "transfer", "slippage_amount", "impact_amount")
    totals = {field: sum(float(row[field]) for row in rows) for field in fields}
    total = sum(totals.values())
    result = {
        "gross_traded_notional": denominator,
        **totals,
        "total_cost": total,
        "commission_bps": _bps(totals["commission"], denominator),
        "stamp_bps": _bps(totals["stamp"], denominator),
        "transfer_bps": _bps(totals["transfer"], denominator),
        "slippage_bps": _bps(totals["slippage_amount"], denominator),
        "impact_bps": _bps(totals["impact_amount"], denominator),
        "total_cost_bps": _bps(total, denominator),
        "fill_ids": [row["fill_id"] for row in rows],
        "fill_count": len(rows),
        "per_fill": rows,
        "impact_model": "none",
        "impact_disclosure": "no independent impact model",
    }
    if stress:
        result["stress_slippage_bps"] = 10.0
        result["stress_commission_rate"] = 0.0006
        result["stress_price_rule"] = "buy=base*1.001;sell=base*0.999"
    else:
        result["base_slippage_bps"] = 0.0
        result["base_commission_rate"] = 0.0003
    return result


def calculate_cost_results(event: EventBacktestResult) -> dict[str, Any]:
    """Recompute both approved cost views from the immutable B4 fills only."""
    intents = _validate_event(event)
    base_rows: list[dict[str, Any]] = []
    stress_rows: list[dict[str, Any]] = []
    denominator = 0.0
    for fill in event.fills:
        direction = intents[fill.order_id].intent
        base_price = float(fill.fill_price)
        quantity = int(fill.fill_quantity)
        base_gross, base_commission, base_stamp, base_transfer, _, _ = calculate_transaction_costs(
            direction, quantity, base_price, 0.0003, 5.0, 0.001, 0.0
        )
        stress_price = base_price * (1.001 if direction == "buy" else 0.999)
        stress_gross, stress_commission, stress_stamp, stress_transfer, _, _ = calculate_transaction_costs(
            direction, quantity, stress_price, 0.0006, 5.0, 0.001, 0.0
        )
        slippage = abs(stress_price - base_price) * quantity
        denominator += base_gross
        common = {
            "fill_id": fill.fill_id,
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "fill_date": fill.fill_date.isoformat(),
            "direction": direction,
            "quantity": quantity,
            "base_fill_price": base_price,
        }
        base_rows.append({**common, "price": base_price, "gross_notional": base_gross, "commission": base_commission, "stamp": base_stamp, "transfer": base_transfer, "slippage_amount": 0.0, "impact_amount": 0.0})
        stress_rows.append({**common, "price": stress_price, "gross_notional": stress_gross, "commission": stress_commission, "stamp": stress_stamp, "transfer": stress_transfer, "slippage_amount": slippage, "impact_amount": 0.0})
    if not _finite(denominator) or denominator <= 0:
        raise CostCalculationError("zero or invalid base gross-notional denominator")
    base = _aggregate(base_rows, denominator, stress=False)
    stress = _aggregate(stress_rows, denominator, stress=True)
    if stress["total_cost"] <= base["total_cost"] or stress["total_cost_bps"] <= base["total_cost_bps"]:
        raise CostCalculationError("stress total cost is not strictly greater than base")
    return {
        "base": base,
        "stress": stress,
        "cost_assumptions_hash": COST_ASSUMPTIONS_HASH,
        "cost_assumptions": ASSUMPTIONS,
    }


def _lineage(repo_root: Path, observation: dict[str, Any]) -> dict[str, Any]:
    lineage = build_lineage(repo_root)
    lineage["ledger_observation"] = observation
    lineage["daily_observation_hash"] = observation["observations_sha256"]
    return lineage


def _expected_files(manifest: dict[str, Any], base: dict[str, Any], stress: dict[str, Any]) -> dict[str, bytes]:
    values = {
        "manifest.json": manifest,
        "base_transaction_cost.json": base,
        "stress_transaction_cost.json": stress,
    }
    files: dict[str, bytes] = {}
    for name, value in values.items():
        raw = canonical_json(value)
        files[name] = raw
        files[name + ".sha256"] = f"{sha256_bytes(raw)}  {name}\n".encode("utf-8")
    return files


def _write_once(target: Path, files: dict[str, bytes]) -> str:
    if target.exists():
        for name, expected in files.items():
            path = target / name
            if not path.exists() or path.read_bytes() != expected:
                raise CostCalculationError("v3 B5 cost write-once conflict")
        return "already_published"
    output_root = target.parent
    output_root.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{target.name}.staging-"
    staging = Path(tempfile.mkdtemp(prefix=staging_prefix, dir=output_root))
    temps: list[Path] = []
    try:
        for name, raw in files.items():
            path = staging / name
            with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".", suffix=".tmp", delete=False) as handle:
                temp = Path(handle.name)
                temps.append(temp)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            temps.remove(temp)
        os.replace(staging, target)
        return "published"
    except Exception:
        raise


def _payloads(repo_root: Path, lineage: dict[str, Any], results: dict[str, Any], observation_hash: str) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, dict[str, str]]]:
    sources = _source_bindings(repo_root)
    algorithm_hash = sources["cost_service"]["sha256"]
    base = build_result_payload(
        "base_transaction_cost", lineage=lineage, result=results["base"],
        producer_algorithm_hash=algorithm_hash, cost_assumptions_hash=results["cost_assumptions_hash"],
        daily_observation_hash=observation_hash,
    )
    stress = build_result_payload(
        "stress_transaction_cost", lineage=lineage, result=results["stress"],
        producer_algorithm_hash=algorithm_hash, cost_assumptions_hash=results["cost_assumptions_hash"],
        daily_observation_hash=observation_hash,
    )
    return base, stress, algorithm_hash, sources


def build_cost_artifact(repo_root: Path = ROOT, output_root: Path = OUTPUT_ROOT, *, observation_dir: Path | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if repo_root != ROOT.resolve():
        raise CostCalculationError("v3 B5 costs are bound to the repository root")
    _, event = _load_b4(repo_root)
    observation = _static_observation_lineage(repo_root, observation_dir)
    results = calculate_cost_results(event)
    lineage = _lineage(repo_root, observation)
    base, stress, algorithm_hash, sources = _payloads(repo_root, lineage, results, observation["observations_sha256"])
    refs = {
        "base_transaction_cost": {"payload_id": base["payload_id"], "canonical_payload_sha256": base["canonical_payload_sha256"], "path": "base_transaction_cost.json"},
        "stress_transaction_cost": {"payload_id": stress["payload_id"], "canonical_payload_sha256": stress["canonical_payload_sha256"], "path": "stress_transaction_cost.json"},
    }
    core = {
        "schema_version": SCHEMA,
        "status": "valid",
        "authorization_scope": "v3_is_transaction_cost_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "lineage": lineage,
        "cost_assumptions_hash": results["cost_assumptions_hash"],
        "producer_algorithm_hash": algorithm_hash,
        "producer_source_hashes": sources,
        "results": refs,
        "is_range": dict(IS_RANGE),
        "fill_count": len(event.fills),
        "denominator": results["base"]["gross_traded_notional"],
    }
    artifact_id = sha256_bytes(canonical_json(core))[:16]
    manifest = {**core, "artifact_id": artifact_id}
    files = _expected_files(manifest, base, stress)
    status = _write_once(Path(output_root) / artifact_id, files)
    return {"status": status, "artifact_id": artifact_id, "path": str(Path(output_root) / artifact_id), "manifest_sha256": sha256_bytes(files["manifest.json"]), "not_authorized_for_b6_oos_gate_promotion_signal": True, "base": results["base"], "stress": results["stress"]}


def verify_cost_artifact(repo_root: Path, artifact_dir: Path, *, observation_dir: Path | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    directory = Path(artifact_dir)
    manifest_path = directory / "manifest.json"
    base_path = directory / "base_transaction_cost.json"
    stress_path = directory / "stress_transaction_cost.json"
    for path in (manifest_path, base_path, stress_path):
        if not path.exists():
            raise CostCalculationError(f"cost artifact file missing: {path.name}")
    manifest_sha = _sidecar_hash(manifest_path)
    base_sha = _sidecar_hash(base_path)
    stress_sha = _sidecar_hash(stress_path)
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "valid" or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
        raise CostCalculationError("cost artifact schema/status/disclosure mismatch")
    core = {key: value for key, value in manifest.items() if key != "artifact_id"}
    expected_id = sha256_bytes(canonical_json(core))[:16]
    if manifest.get("artifact_id") != expected_id or directory.name != expected_id:
        raise CostCalculationError("cost artifact identity mismatch")
    observation = _static_observation_lineage(repo_root, observation_dir)
    lineage = _lineage(repo_root, observation)
    if manifest.get("lineage") != lineage:
        raise CostCalculationError("cost artifact lineage mismatch")
    _, event = _load_b4(repo_root)
    results = calculate_cost_results(event)
    expected_base, expected_stress, algorithm_hash, sources = _payloads(repo_root, lineage, results, observation["observations_sha256"])
    actual_base = _read_json(base_path)
    actual_stress = _read_json(stress_path)
    validate_result_payload(actual_base, "base_transaction_cost", lineage)
    validate_result_payload(actual_stress, "stress_transaction_cost", lineage)
    if actual_base != expected_base or actual_stress != expected_stress:
        raise CostCalculationError("recomputed cost payload differs")
    refs = manifest.get("results", {})
    if refs.get("base_transaction_cost", {}).get("canonical_payload_sha256") != actual_base["canonical_payload_sha256"] or refs.get("stress_transaction_cost", {}).get("canonical_payload_sha256") != actual_stress["canonical_payload_sha256"]:
        raise CostCalculationError("cost result reference mismatch")
    if manifest.get("producer_source_hashes") != sources or manifest.get("producer_algorithm_hash") != algorithm_hash or manifest.get("cost_assumptions_hash") != COST_ASSUMPTIONS_HASH:
        raise CostCalculationError("cost source or assumptions hash mismatch")
    return {
        "status": "verified",
        "artifact_id": expected_id,
        "path": str(directory),
        "manifest_sha256": manifest_sha,
        "base_sha256": base_sha,
        "stress_sha256": stress_sha,
        "fill_count": len(event.fills),
        "gross_traded_notional": results["base"]["gross_traded_notional"],
        "base_total_cost": results["base"]["total_cost"],
        "stress_total_cost": results["stress"]["total_cost"],
        "base_total_cost_bps": results["base"]["total_cost_bps"],
        "stress_total_cost_bps": results["stress"]["total_cost_bps"],
    }
