"""Build the immutable V2 availability-coverage diagnostic package."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from scripts.sw2021_pit_qualification_core import apply_market_scope, build_events, eligible_codes_independent, step_active

FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
SW_DIR = FORMAL / "sw_l1_membership"
VENDOR_DIR = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
REQUIRED_DAILY = ("daily", "daily_basic", "stk_limit", "adj_factor")
TEMPLATE_ID = "relative_strength_rotation_shsz_sw2021_v1"
COVERAGE_SCHEMA = {
    "coverage_schema_version": "v2",
    "coverage_by_date": ["trade_date", "expected_codes", "complete_codes", "unavailable_codes"],
    "coverage_by_code": ["ts_code", "expected_days", "complete_days", "unavailable_days"],
    "unavailable_security_dates": ["trade_date", "ts_code", "missing_fields"],
    "required_input_columns": ["ts_code", "trade_date"],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _algorithm_hash() -> str:
    payload = b"coverage:" + (ROOT / "scripts/build_v2_coverage.py").read_bytes()
    payload += b"|expected_universe:" + (ROOT / "scripts/sw2021_pit_qualification_core.py").read_bytes()
    return hashlib.sha256(payload).hexdigest()


def _lifecycle(vendor_lifecycle: dict) -> pd.DataFrame:
    frames = [
        pd.read_parquet(FORMAL / "stock_basic" / f"list_status={status}" / "part.parquet",
                        columns=["ts_code", "list_date", "delist_date"])
        for status in ("L", "D", "P")
    ]
    table = pd.concat(frames, ignore_index=True).set_index("ts_code")
    if table.index.duplicated().any():
        raise ValueError("STRUCTURAL_ERROR: stock_basic has duplicate ts_code lifecycle rows")
    allowed = {"000022.SZ", "000043.SZ", "300114.SZ"}
    if vendor_lifecycle.get("status") != "candidate_verified" or {item["ts_code"] for item in vendor_lifecycle["codes"]} != allowed:
        raise ValueError("STRUCTURAL_ERROR: vendor lifecycle supplement is not the frozen candidate")
    for item in vendor_lifecycle["codes"]:
        table.loc[item["ts_code"]] = [item["list_date"], item["delist_date"]]
    table["list_date"] = pd.to_numeric(table["list_date"])
    table["delist_date"] = pd.to_numeric(table["delist_date"]).fillna(99991231)
    return table


def compute_coverage_hash(manifest: dict, algorithm_hash: str, *, input_manifest_hashes: dict | None = None,
                          schema: dict | None = None) -> str:
    """Return a stable package identity with no machine-specific inputs."""
    canonical = {
        "coverage_schema": schema or COVERAGE_SCHEMA,
        "qualification_package_id": manifest["qualification_package_id"],
        "scope_hash": manifest["scope_hash"],
        "template_hash": manifest["template_hash"],
        "data_requirements_hash": manifest["data_requirements_hash"],
        "snapshot_hash": manifest["snapshot_hash"],
        "input_manifest_content_hashes": input_manifest_hashes or {},
        "algorithm_hash": algorithm_hash,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def build_expected_codes_for_date(lifecycle: pd.DataFrame, active: dict[str, Counter], date: int,
                                  market_scope: list[str]) -> set[str]:
    """Build expected codes solely from lifecycle, PIT membership, and scope."""
    eligible, _, _, _, _ = eligible_codes_independent(lifecycle, active, date)
    expected, _, _ = apply_market_scope(eligible, market_scope)
    return expected


def read_bound_partition(path: Path, date: int, interface: str) -> set[str]:
    """Read one registered partition or fail before a diagnostic can be published."""
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"STRUCTURAL_ERROR: {interface} partition {date} is missing its registered hash")
    if sidecar.read_text().strip() != _sha256(path):
        raise ValueError(f"STRUCTURAL_ERROR: {interface} partition {date} registered hash mismatch")
    try:
        frame = pd.read_parquet(path, columns=COVERAGE_SCHEMA["required_input_columns"])
    except Exception as exc:
        raise ValueError(f"STRUCTURAL_ERROR: {interface} partition {date} lacks required columns") from exc
    if set(frame["trade_date"].astype(str)) != {str(date)}:
        raise ValueError(f"STRUCTURAL_ERROR: {interface} partition {date} has path/date mismatch")
    if frame.duplicated(["trade_date", "ts_code"], keep=False).any():
        raise ValueError(f"STRUCTURAL_ERROR: {interface} partition {date} has duplicate (trade_date, ts_code)")
    return set(frame["ts_code"].dropna())


def _preflight(manifest: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[int], list[str], dict]:
    """Reject any drift from the qualification package before reading daily inputs."""
    from backend.services.strategy_template_library import get_template_by_id
    from scripts.qualify_sw2021_pit_package import BENCHMARKS, _guard_hash, _snapshot_hash

    template = get_template_by_id(TEMPLATE_ID)
    if template is None or template.frozen_template_hash != manifest["template_hash"]:
        raise ValueError("PRECHECK_FAILED: template hash differs from qualification manifest")
    market_scope = list(template.strategy_config_payload.get("market_scope", []))
    if market_scope != ["SH", "SZ"] or template.strategy_config_payload.get("minimum_history_trading_days") != 0:
        raise ValueError("PRECHECK_FAILED: template scope/window differs from frozen qualification")
    universe_path = SW_DIR / "sw2021_universe_candidate.json"
    vendor_candidate_path = VENDOR_DIR / "security_lifecycle_candidate.json"
    membership_manifest_path = SW_DIR / "manifest.json"
    universe = json.loads(universe_path.read_text())
    vendor_lifecycle = json.loads(vendor_candidate_path.read_text())
    membership_manifest = json.loads(membership_manifest_path.read_text())
    sw_parts = [part for part in membership_manifest["partitions"] if part["src"] == "SW2021"]
    requirements = {
        "template_id": template.template_id,
        "template_hash": template.frozen_template_hash,
        "taxonomy_source": "SW2021",
        "universe_definition_hash": universe["universe_definition_hash"],
        "sw2021_partitions": {part["name"]: part["sha256"] for part in sw_parts},
        "vendor_lifecycle_candidate_hash": _sha256(vendor_candidate_path),
        "vendor_package_hash": vendor_lifecycle["vendor_package_sha256"],
        "vendor_lifecycle_codes": ["000022.SZ", "000043.SZ", "300114.SZ"],
        "interfaces": list(REQUIRED_DAILY) + ["trade_cal", "stock_basic", "stock_st", "suspend_d"],
        "benchmarks": list(BENCHMARKS),
        "market_scope": market_scope,
        "minimum_history_trading_days": 0,
    }
    requirements_hash = hashlib.sha256(json.dumps(requirements, sort_keys=True).encode()).hexdigest()
    snapshot_hash = _snapshot_hash(sw_parts, vendor_candidate_path, universe_path)
    scope_hash = hashlib.sha256(
        f"{template.frozen_template_hash}|{_guard_hash()}|{requirements_hash}|{snapshot_hash}".encode()
    ).hexdigest()[:16]
    expected = {
        "qualification_package_id": manifest.get("qualification_package_id"),
        "scope_hash": scope_hash,
        "data_requirements_hash": requirements_hash,
        "snapshot_hash": snapshot_hash,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("PRECHECK_FAILED: source scope, requirements, or snapshot differs from qualification manifest")
    memberships = pd.concat([
        pd.read_parquet(SW_DIR / part["name"], columns=["ts_code", "l1_code", "in_date", "out_date"])
        for part in sw_parts
    ], ignore_index=True)
    memberships["in_date"] = pd.to_numeric(memberships["in_date"])
    memberships["out_date"] = pd.to_numeric(memberships["out_date"]).fillna(99991231)
    calendar = pd.read_parquet(FORMAL / "trade_cal" / "part.parquet")
    days = sorted(pd.to_numeric(calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"]).astype(int).tolist())
    if len(days) != manifest.get("checked_trade_days"):
        raise ValueError("PRECHECK_FAILED: trading calendar window differs from qualification manifest")
    binding_paths = {
        "qualification_manifest.json": ROOT / "data/pit/formal_packages" / manifest["qualification_package_id"] / "manifest.json",
        "sw2021_membership_manifest.json": membership_manifest_path,
        "sw2021_universe_candidate.json": universe_path,
        "vendor_lifecycle_candidate.json": vendor_candidate_path,
        "vendor_snapshot_manifest.json": VENDOR_DIR / "manifest.json",
    }
    return _lifecycle(vendor_lifecycle), memberships, days, market_scope, {name: _sha256(path) for name, path in binding_paths.items()}


def _published_result(output_dir: Path) -> dict:
    result = json.loads((output_dir / "coverage_manifest.json").read_text())
    manifest_hash_path = output_dir / "coverage_manifest.json.sha256"
    if not manifest_hash_path.exists() or manifest_hash_path.read_text().strip() != _sha256(output_dir / "coverage_manifest.json"):
        raise ValueError("STRUCTURAL_ERROR: published coverage manifest hash mismatch")
    for name, key in (
        ("coverage_by_date.parquet", "coverage_by_date_hash"),
        ("coverage_by_code.parquet", "coverage_by_code_hash"),
        ("unavailable_security_dates.parquet", "unavailable_parquet_hash"),
    ):
        if _sha256(output_dir / name) != result[key]:
            raise ValueError(f"STRUCTURAL_ERROR: published {name} hash mismatch")
    result["status"] = "already_published"
    return result


def _write_report(result: dict) -> None:
    report = f"""# V2 Historical Validation Availability Coverage Report

**Status:** {result['status']}  
**Coverage Hash:** `{result['coverage_hash']}`  

## Summary

- Expected stock-days: {result['expected_stock_days']:,}
- Complete stock-days: {result['complete_stock_days']:,}
- Unavailable stock-days: {result['unavailable_stock_days']:,}

## Disclosure

availability mask 是覆盖诊断产物，不是新的 formal package、tradability mask 或回测 universe。后续 B6/OOS 若跳过 unavailable observations，必须同时保留原始 expected-universe 分母并披露逐日覆盖率，不得只报告 supported observations 上的收益而省略覆盖变化。
"""
    (ROOT / "docs/verification/V2_AVAILABILITY_COVERAGE_REPORT.md").write_text(report)


def build_coverage_package(qualification_package_id: str) -> dict:
    """Scan the frozen inputs and publish only unavailable expected observations."""
    manifest_path = ROOT / "data/pit/formal_packages" / qualification_package_id / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Qualification package not found: {qualification_package_id}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("qualification_package_id") != qualification_package_id:
        raise ValueError("PRECHECK_FAILED: qualification package identifier mismatch")
    lifecycle, memberships, days, market_scope, input_manifest_hashes = _preflight(manifest)
    algorithm_hash = _algorithm_hash()
    coverage_hash = compute_coverage_hash(manifest, algorithm_hash, input_manifest_hashes=input_manifest_hashes,
                                          schema=COVERAGE_SCHEMA)
    output_dir = ROOT / "data/pit/coverage_packages" / coverage_hash
    if (output_dir / "coverage_manifest.json").exists():
        return _published_result(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite unpublished coverage directory: {output_dir}")

    starts, ends = build_events(memberships, days)
    active: dict[str, Counter] = {}
    unavailable_rows, by_date_rows = [], []
    code_stats = defaultdict(lambda: Counter(expected=0, complete=0, unavailable=0))
    field_counts = Counter()
    for index, date in enumerate(days):
        active = step_active(active, ends, starts, index)
        expected = build_expected_codes_for_date(lifecycle, active, date, market_scope)
        available = {
            interface: read_bound_partition(FORMAL / interface / f"trade_date={date}" / "part.parquet", date, interface)
            for interface in REQUIRED_DAILY
        }
        complete = expected.intersection(*(available[interface] for interface in REQUIRED_DAILY))
        unavailable = expected - complete
        by_date_rows.append({"trade_date": date, "expected_codes": len(expected), "complete_codes": len(complete),
                             "unavailable_codes": len(unavailable)})
        for code in expected:
            code_stats[code]["expected"] += 1
        for code in complete:
            code_stats[code]["complete"] += 1
        for code in unavailable:
            missing = tuple(sorted(interface for interface in REQUIRED_DAILY if code not in available[interface]))
            unavailable_rows.append({"trade_date": date, "ts_code": code, "missing_fields": list(missing)})
            code_stats[code]["unavailable"] += 1
            field_counts.update(missing)

    by_date = pd.DataFrame(by_date_rows).sort_values("trade_date")
    by_code = pd.DataFrame([
        {"ts_code": code, "expected_days": counts["expected"], "complete_days": counts["complete"],
         "unavailable_days": counts["unavailable"]}
        for code, counts in sorted(code_stats.items())
    ])
    unavailable = pd.DataFrame(unavailable_rows, columns=COVERAGE_SCHEMA["unavailable_security_dates"]).sort_values(
        ["trade_date", "ts_code"]
    )
    expected_total = int(by_date["expected_codes"].sum())
    complete_total = int(by_date["complete_codes"].sum())
    unavailable_total = int(by_date["unavailable_codes"].sum())
    if expected_total != manifest["expected_stock_days_after_market_scope"] or complete_total + unavailable_total != expected_total:
        raise AssertionError("coverage totals do not match the frozen expected universe")
    if len(unavailable) != unavailable_total or int(by_code["expected_days"].sum()) != expected_total:
        raise AssertionError("coverage aggregation does not reconcile")

    output_dir.mkdir(parents=True, exist_ok=False)
    by_date.to_parquet(output_dir / "coverage_by_date.parquet", index=False)
    by_code.to_parquet(output_dir / "coverage_by_code.parquet", index=False)
    unavailable.to_parquet(output_dir / "unavailable_security_dates.parquet", index=False)
    result = {
        "status": "coverage_published",
        "coverage_hash": coverage_hash,
        "algorithm_hash": algorithm_hash,
        "coverage_schema": COVERAGE_SCHEMA,
        "input_qualification_package_id": qualification_package_id,
        "input_scope_hash": manifest["scope_hash"],
        "input_template_hash": manifest["template_hash"],
        "input_data_requirements_hash": manifest["data_requirements_hash"],
        "input_snapshot_hash": manifest["snapshot_hash"],
        "input_manifest_content_hashes": input_manifest_hashes,
        "checked_trade_days": len(days),
        "expected_stock_days": expected_total,
        "complete_stock_days": complete_total,
        "unavailable_stock_days": unavailable_total,
        "field_missing_counts": dict(sorted(field_counts.items())),
        "build_completion": {
            "status": "completed",
            "scanned_trade_days": len(days),
            "required_partition_reads": len(days) * len(REQUIRED_DAILY),
            "structural_validation": "passed",
        },
        "structural_errors": [],
        "top_10_dates_by_unavailable": by_date.sort_values(["unavailable_codes", "trade_date"], ascending=[False, True]).head(10)[["trade_date", "unavailable_codes"]].values.tolist(),
        "top_10_codes_by_unavailable": by_code.sort_values(["unavailable_days", "ts_code"], ascending=[False, True]).head(10)[["ts_code", "unavailable_days"]].values.tolist(),
        "coverage_by_date_hash": _sha256(output_dir / "coverage_by_date.parquet"),
        "coverage_by_code_hash": _sha256(output_dir / "coverage_by_code.parquet"),
        "unavailable_parquet_hash": _sha256(output_dir / "unavailable_security_dates.parquet"),
    }
    (output_dir / "coverage_manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    (output_dir / "coverage_manifest.json.sha256").write_text(_sha256(output_dir / "coverage_manifest.json"))
    _write_report(result)
    return result


if __name__ == "__main__":
    print(json.dumps(build_coverage_package("de3fed9c3819d25c"), indent=2, sort_keys=True))
