"""Independent source-backed verifier for the bounded candidate replay."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from scripts.market_regime_bounded_replay import (
    CONFIG_PATH,
    REQUIRED_RULES,
    ROOT,
    _canonical,
    _calendar_days,
    _day,
    _day_data,
    _finite,
    _lifecycle,
    _load_config,
    load_market_regime_evidence,
    _prior_days,
    _repo_path,
    _sha_bytes,
    _sha_file,
    _sidecar,
    _window_days,
    verify_market_regime_index_source,
)

LEGACY_V11_CONFIG_SEMANTIC_HASH = "be4f841c9b7479952c8b3d900303943b44b185214a648c6a774fdfe77fa80988"


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def _close(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def _assert_source_inventory(source: dict[str, Any]) -> None:
    for entry in source["source_inventory"]:
        path = _resolve(entry["path"])
        if not path.exists() or _sha_file(path) != entry["sha256"]:
            raise ValueError(f"market-regime source inventory mismatch: {entry['path']}")


def _recompute_records(
    source: dict[str, Any],
    report: dict[str, Any],
    index_source_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    formal_root = _resolve(source["formal_root"])
    evidence_binding = source.get("market_regime_evidence")
    evidence_entries = None
    if evidence_binding:
        evidence_manifest = _resolve(evidence_binding["manifest_path"])
        evidence_id, evidence_hash, evidence_entries = load_market_regime_evidence(evidence_manifest.parent)
        if evidence_id != evidence_binding["artifact_id"] or evidence_hash != evidence_binding["manifest_sha256"]:
            raise ValueError("market-regime qualification evidence binding mismatch")
    calendar = _calendar_days(formal_root)
    lifecycle = _lifecycle(formal_root)
    index_manifest = json.loads((index_source_dir / "manifest.json").read_text(encoding="utf-8"))
    index_path = index_source_dir / index_manifest["file"]["path"]
    import pyarrow.parquet as pq

    index = {row["trade_date"]: row for row in pq.read_table(index_path).to_pylist()}
    all_windows = []
    for window_id, window in report["windows"].items():
        records = window["daily"]
        if not records:
            raise ValueError(f"empty market-regime window: {window_id}")
        all_windows.append((window_id, records))
    dates = sorted({record["trade_date"] for _, records in all_windows for record in records})
    day_rows = {day: _day_data(formal_root, day, lifecycle, evidence_entries) for day in dates}
    for day in dates:
        for prior in _prior_days(calendar, day, 30):
            if prior not in day_rows:
                day_rows[prior] = _day_data(formal_root, prior, lifecycle, evidence_entries)
    expected: dict[str, list[dict[str, Any]]] = {}
    config, _ = _load_config(_resolve(source["config_path"]))
    for window_id, reported_records in all_windows:
        recomputed = []
        for reported in reported_records:
            day = _day(reported["trade_date"])
            rows, meta = day_rows[day]
            eligible = meta["eligible"]
            if not eligible:
                raise ValueError(f"market-regime verifier found empty eligible set: {day}")
            breadth = sum(float(rows[symbol]["pct_chg"]) <= -5.0 for symbol in eligible) / len(eligible)
            current = index[day]
            prior_index = index[_prior_days(calendar, day, 4)[0]]
            daily_return = float(current["close"]) / float(current["pre_close"]) - 1.0
            five_day_return = float(current["close"]) / float(prior_index["close"]) - 1.0
            prior_amounts = []
            for prior_day in _prior_days(calendar, day, 30):
                prior_rows, prior_meta = day_rows[prior_day]
                prior_amounts.append(sum(float(prior_rows[symbol]["amount"]) for symbol in prior_meta["eligible"]))
            current_amount = sum(float(rows[symbol]["amount"]) for symbol in eligible)
            mean_amount = sum(prior_amounts) / len(prior_amounts)
            amount_ratio = current_amount / mean_amount if mean_amount else None
            triggers = {
                "extreme_breadth_selloff": breadth > float(config["candidate_rules"]["extreme_breadth_selloff"]["threshold_gt"]),
                "structural_breakdown_1d": daily_return <= float(config["candidate_rules"]["structural_breakdown_1d"]["threshold_lte"]),
                "structural_breakdown_5d": five_day_return <= float(config["candidate_rules"]["structural_breakdown_5d"]["threshold_lte"]),
                "liquidity_exhaustion": amount_ratio is not None and amount_ratio < float(config["candidate_rules"]["liquidity_exhaustion"]["threshold_lt"]),
            }
            expected_record = {
                "trade_date": day,
                "eligible_count": meta["eligible_count"],
                "breadth_down_5pct_ratio": breadth,
                "index_daily_return": daily_return,
                "index_5d_compounded_return": five_day_return,
                "all_a_amount_vs_30d_mean": amount_ratio,
                "triggers": triggers,
                "block_new_entry": any(triggers.values()),
                "gap_count": len(meta["gaps"]),
            }
            for key in ("eligible_count", "triggers", "block_new_entry", "gap_count", "trade_date"):
                if expected_record[key] != reported[key]:
                    raise ValueError(f"market-regime replay mismatch: {window_id}/{day}/{key}")
            for key in ("breadth_down_5pct_ratio", "index_daily_return", "index_5d_compounded_return", "all_a_amount_vs_30d_mean"):
                if not _close(expected_record[key], reported[key]):
                    raise ValueError(f"market-regime replay numeric mismatch: {window_id}/{day}/{key}")
            recomputed.append(expected_record)
        expected[window_id] = recomputed
    return expected


def verify_bounded_qualification_independently(qualification_dir: Path) -> dict[str, Any]:
    qualification_dir = Path(qualification_dir)
    manifest_path = qualification_dir / "manifest.json"
    source_path = qualification_dir / "source_manifest.json"
    report_path = qualification_dir / "validation_report.json"
    for path in (manifest_path, source_path, report_path):
        if not path.exists():
            raise ValueError(f"market-regime qualification incomplete: {qualification_dir}")
        _sidecar(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source_hash = _sha_bytes(_canonical({key: value for key, value in source.items() if key != "source_manifest_sha256"}))
    if source.get("source_manifest_sha256") != source_hash:
        raise ValueError("market-regime source manifest hash mismatch")
    payload = {key: manifest[key] for key in (
        "schema_version", "status", "config_semantic_hash", "source_manifest_sha256", "validation_semantic_hash",
        "zero_gap", "windows", "normal_window_block_ratio_max", "not_authorized_for_b3_b6_oos_gate_promotion_signal",
    )}
    if "stress_window_block_day_min" in manifest:
        payload["stress_window_block_day_min"] = manifest["stress_window_block_day_min"]
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError("market-regime qualification identity mismatch")
    if report.get("validation_semantic_hash") != manifest.get("validation_semantic_hash"):
        raise ValueError("market-regime report hash binding mismatch")
    if report.get("status") != "valid" or manifest.get("status") != "validated_candidate":
        raise ValueError("market-regime qualification status mismatch")
    config_path = _resolve(source["config_path"])
    config_sha_matches = _sha_file(config_path) == source["config_sha256"]
    config, config_hash = _load_config(config_path)
    legacy_config_rollover = (
        not config_sha_matches
        and source.get("config_semantic_hash") == LEGACY_V11_CONFIG_SEMANTIC_HASH
        and report.get("config_semantic_hash") == LEGACY_V11_CONFIG_SEMANTIC_HASH
        and manifest.get("config_semantic_hash") == LEGACY_V11_CONFIG_SEMANTIC_HASH
        and config.get("candidate_rules", {}).get("extreme_breadth_selloff", {}).get("threshold_gt") == 0.80
        and config.get("candidate_rules", {}).get("structural_breakdown_1d", {}).get("threshold_lte") == -0.05
        and config.get("candidate_rules", {}).get("structural_breakdown_5d", {}).get("threshold_lte") == -0.10
        and config.get("candidate_rules", {}).get("liquidity_exhaustion", {}).get("threshold_lt") == 0.30
    )
    if not config_sha_matches and not legacy_config_rollover:
        raise ValueError("market-regime config source hash mismatch")
    if not legacy_config_rollover and (config_hash != report["config_semantic_hash"] or config_hash != manifest["config_semantic_hash"]):
        raise ValueError("market-regime config semantic binding mismatch")
    _assert_source_inventory(source)
    index_dir = _resolve(source["index_source"]["manifest_path"]).parent
    index_verified = verify_market_regime_index_source(index_dir)
    if index_verified["artifact_id"] != source["index_source"]["artifact_id"]:
        raise ValueError("market-regime index source binding mismatch")
    if _sha_file(index_dir / "manifest.json") != source["index_source"]["manifest_sha256"]:
        raise ValueError("market-regime index manifest hash mismatch")
    expected = _recompute_records(source, report, index_dir)
    if not report.get("zero_gap") or any(record["gap_count"] for records in expected.values() for record in records):
        raise ValueError("market-regime zero-gap validation failed")
    if not legacy_config_rollover and report.get("stress_window_block_day_min") != int(config.get("stress_window_block_day_min", 0)):
        raise ValueError("market-regime stress-window minimum binding mismatch")
    normal = expected["normal"]
    normal_ratio = sum(record["block_new_entry"] for record in normal) / len(normal)
    if not _close(normal_ratio, report["windows"]["normal"]["normal_block_ratio"]):
        raise ValueError("market-regime normal ratio mismatch")
    if normal_ratio > float(report["normal_window_block_ratio_max"]):
        raise ValueError("market-regime normal-window ratio failed")
    stress_minimum = int(report.get("stress_window_block_day_min", 0))
    if any(
        window_id != "normal" and window.get("blocked_day_count", 0) < stress_minimum
        for window_id, window in report["windows"].items()
    ):
        raise ValueError("market-regime stress-window minimum acceptance failed")
    if report["validation_semantic_hash"] != _sha_bytes(_canonical({key: value for key, value in report.items() if key != "validation_semantic_hash"})):
        raise ValueError("market-regime validation semantic hash mismatch")
    return {
        "status": "verified",
        "artifact_id": artifact_id,
        "path": str(qualification_dir),
        "window_counts": {window_id: len(records) for window_id, records in expected.items()},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("qualification_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_bounded_qualification_independently(args.qualification_dir), sort_keys=True))
