"""Full scoped PIT qualification for the SW2021 industry-relative candidate."""
"""SW2021 PIT formal qualification."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from scripts.sw2021_pit_qualification_core import build_events, eligible_codes_independent, step_active, apply_market_scope


FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
SW_DIR = FORMAL / "sw_l1_membership"
VENDOR_DIR = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
REQUIRED_DAILY = ("daily", "daily_basic", "stk_limit", "adj_factor")
BENCHMARKS = ("000300.SH", "000905.SH")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lifecycle(vendor_lifecycle: dict) -> pd.DataFrame:
    frames = [
        pd.read_parquet(FORMAL / "stock_basic" / f"list_status={status}" / "part.parquet", columns=["ts_code", "list_date", "delist_date"])
        for status in ("L", "D", "P")
    ]
    table = pd.concat(frames, ignore_index=True).set_index("ts_code")
    if table.index.duplicated().any():
        raise ValueError("stock_basic has duplicate ts_code lifecycle rows")
    allowed = {"000022.SZ", "000043.SZ", "300114.SZ"}
    supplied = {item["ts_code"] for item in vendor_lifecycle["codes"]}
    if supplied != allowed or vendor_lifecycle["status"] != "candidate_verified":
        raise ValueError("vendor lifecycle supplement is not the frozen three-code candidate")
    for item in vendor_lifecycle["codes"]:
        table.loc[item["ts_code"]] = [item["list_date"], item["delist_date"]]
    table["list_date"] = pd.to_numeric(table["list_date"])
    table["delist_date"] = pd.to_numeric(table["delist_date"]).fillna(99991231)
    return table


def _guard_hash() -> str:
    config = yaml.safe_load((ROOT / "backend/config/market_regime_thresholds.yaml").read_text())
    semantic = {key: config[key] for key in (
        "version", "candidate_rules", "stress_windows", "normal_window",
        "zero_gap_rule", "normal_window_block_ratio_max", "required_pit_inputs",
    )}
    return hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()


def _snapshot_hash(sw_parts: list[dict], vendor_candidate_path: Path, universe_path: Path) -> str:
    hashes = [_sha256(vendor_candidate_path), _sha256(universe_path)]
    for interface in (*REQUIRED_DAILY, "trade_cal", "stock_basic", "stock_st", "suspend_d"):
        hashes.extend(sidecar.read_text().strip() for sidecar in sorted((FORMAL / interface).rglob("*.sha256")))
    for benchmark in BENCHMARKS:
        hashes.extend(sidecar.read_text().strip() for sidecar in sorted((FORMAL / "index_daily" / f"ts_code={benchmark}").rglob("*.sha256")))
    hashes.extend(part["sha256"] for part in sw_parts)
    return hashlib.sha256("|".join(sorted(hashes)).encode()).hexdigest()


def _algorithm_hash() -> str:
    """Compute deterministic hash of qualification algorithm implementation."""
    core_src = (ROOT / "scripts/sw2021_pit_qualification_core.py").read_bytes()
    qualifier_src = (ROOT / "scripts/qualify_sw2021_pit_package.py").read_bytes()
    
    # Combine sources with clear delimiter
    combined = b"CORE:" + core_src + b"|QUALIFIER:" + qualifier_src
    return hashlib.sha256(combined).hexdigest()


def _qualification_package_id(scope_hash: str, template_hash: str, requirements_hash: str, 
                              snapshot_hash: str, algorithm_hash: str) -> str:
    """Compute deterministic qualification package ID.
    
    Binds: scope + template + data requirements + snapshot + algorithm.
    Different algorithm → different package ID even if scope unchanged.
    """
    canonical = {
        "qualification_schema_version": "v1_circular_fix",
        "scope_hash": scope_hash,
        "template_hash": template_hash,
        "data_requirements_hash": requirements_hash,
        "snapshot_hash": snapshot_hash,
        "algorithm_hash": algorithm_hash,
    }
    payload = json.dumps(canonical, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def run_qualification() -> dict:
    from backend.services.strategy_template_library import get_template_by_id

    template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
    if template is None:
        raise ValueError("missing relative_strength_rotation_shsz_sw2021_v1 template")
    market_scope = template.strategy_config_payload.get("market_scope", [])
    minimum_history_trading_days = template.strategy_config_payload.get("minimum_history_trading_days", 0)
    universe_path = SW_DIR / "sw2021_universe_candidate.json"
    universe = json.loads(universe_path.read_text())
    if universe["status"] != "candidate_universe_ready" or universe["checked_trade_days"] != 2554:
        raise ValueError("SW2021 universe candidate is not full-window ready")
    vendor_candidate_path = VENDOR_DIR / "security_lifecycle_candidate.json"
    vendor_lifecycle = json.loads(vendor_candidate_path.read_text())
    lifecycle = _lifecycle(vendor_lifecycle)
    membership_manifest = json.loads((SW_DIR / "manifest.json").read_text())
    sw_parts = [part for part in membership_manifest["partitions"] if part["src"] == "SW2021"]
    memberships = pd.concat([
        pd.read_parquet(SW_DIR / part["name"], columns=["ts_code", "l1_code", "in_date", "out_date"])
        for part in sw_parts
    ], ignore_index=True)
    memberships["in_date"] = pd.to_numeric(memberships["in_date"])
    memberships["out_date"] = pd.to_numeric(memberships["out_date"]).fillna(99991231)
    calendar = pd.read_parquet(FORMAL / "trade_cal" / "part.parquet")
    days = sorted(pd.to_numeric(calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"]).astype(int).tolist())
    starts, ends = build_events(memberships, days)
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
        "minimum_history_trading_days": minimum_history_trading_days,
    }
    requirements_hash = hashlib.sha256(json.dumps(requirements, sort_keys=True).encode()).hexdigest()
    guard_hash = _guard_hash()
    snapshot_hash = _snapshot_hash(sw_parts, vendor_candidate_path, universe_path)
    algorithm_hash = _algorithm_hash()
    
    scope_hash = hashlib.sha256(
        f"{template.frozen_template_hash}|{guard_hash}|{requirements_hash}|{snapshot_hash}".encode()
    ).hexdigest()[:16]
    
    qualification_package_id = _qualification_package_id(
        scope_hash, template.frozen_template_hash, requirements_hash, snapshot_hash, algorithm_hash
    )

    active: dict[str, Counter] = {}
    gaps: list[str] = []
    gap_counts = defaultdict(lambda: {"message_count": 0, "stock_day_count": 0})
    stats = {interface: {"partitions": 0, "rows": 0} for interface in REQUIRED_DAILY}
    stats.update({f"index_daily_{benchmark}": {"partitions": 0, "rows": 0} for benchmark in BENCHMARKS})
    candidate_before_market_scope = excluded_pre = excluded_no_industry = lifecycle_unknown = 0
    out_of_scope_bse = out_of_scope_other = expected_after_market_scope = 0
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=5) as readers:
      for index, date in enumerate(days):
        active = step_active(active, ends, starts, index)
        daily_path = FORMAL / "daily" / f"trade_date={date}" / "part.parquet"
        if not daily_path.exists():
            gaps.append(f"daily partition missing {date}")
            continue
        daily = pd.read_parquet(daily_path, columns=["ts_code", "trade_date"])
        stats["daily"]["partitions"] += 1
        stats["daily"]["rows"] += len(daily)
        if set(daily["trade_date"].astype(str)) != {str(date)}:
            gaps.append(f"daily date mismatch {date}")
            continue
        # Expected universe independent of daily rows
        expected, pre_count, no_industry_count, _, ambiguous = eligible_codes_independent(lifecycle, active, date)
        
        # Check for daily codes missing lifecycle (data quality)
        daily_codes = set(daily["ts_code"].dropna())
        unknown_count = len(daily_codes - set(lifecycle.index))
        candidate_before_market_scope += len(expected)
        
        # ponytail: apply market scope
        expected_in_scope, bse_codes, other_codes = apply_market_scope(expected, market_scope)
        out_of_scope_bse += len(bse_codes)
        out_of_scope_other += len(other_codes)
        expected_after_market_scope += len(expected_in_scope)
        
        excluded_pre += pre_count
        excluded_no_industry += no_industry_count
        lifecycle_unknown += unknown_count
        if unknown_count:
            gaps.append(f"{date}: {unknown_count} daily codes lack lifecycle")
            gap_counts["lifecycle"]["message_count"] += 1
            gap_counts["lifecycle"]["stock_day_count"] += unknown_count
        if ambiguous:
            gaps.append(f"{date}: {len(ambiguous)} codes have multiple SW2021 L1 memberships")
            gap_counts["multiple_l1"]["message_count"] += 1
            gap_counts["multiple_l1"]["stock_day_count"] += len(ambiguous)
        read_jobs = {}
        for interface in REQUIRED_DAILY[1:]:
            path = FORMAL / interface / f"trade_date={date}" / "part.parquet"
            if not path.exists():
                gaps.append(f"{interface} partition missing {date}")
            else:
                read_jobs[interface] = readers.submit(pd.read_parquet, path, columns=["ts_code", "trade_date"])
        for benchmark in BENCHMARKS:
            path = FORMAL / "index_daily" / f"ts_code={benchmark}" / f"trade_date={date}" / "part.parquet"
            if not path.exists():
                gaps.append(f"benchmark {benchmark} partition missing {date}")
            else:
                read_jobs[f"index_daily_{benchmark}"] = readers.submit(pd.read_parquet, path, columns=["trade_date"])
        for interface in REQUIRED_DAILY[1:]:
            future = read_jobs.get(interface)
            if future is None:
                continue
            frame = future.result()
            stats[interface]["partitions"] += 1
            stats[interface]["rows"] += len(frame)
            if set(frame["trade_date"].astype(str)) != {str(date)}:
                gaps.append(f"{interface} date mismatch {date}")
            missing = expected_in_scope - set(frame["ts_code"])
            if missing:
                gaps.append(f"{date}: {interface} missing {len(missing)} expected codes")
                gap_counts[interface]["message_count"] += 1
                gap_counts[interface]["stock_day_count"] += len(missing)
        for interface in ("stock_st", "suspend_d"):
            if not (FORMAL / interface / f"trade_date={date}" / "part.parquet").exists():
                gaps.append(f"{interface} sparse partition missing {date}")
        for benchmark in BENCHMARKS:
            key = f"index_daily_{benchmark}"
            future = read_jobs.get(key)
            if future is None:
                continue
            frame = future.result()
            stats[key]["partitions"] += 1
            stats[key]["rows"] += len(frame)
            if len(frame) != 1 or set(frame["trade_date"].astype(str)) != {str(date)}:
                gaps.append(f"benchmark {benchmark} invalid {date}")
        if (index + 1) % 100 == 0:
            print(f"[qualification] {index + 1}/{len(days)} days elapsed={perf_counter() - started:.1f}s", flush=True)

    result = {
        "status": "formal_qualified" if not gaps else "not_qualified",
        "qualification_package_id": qualification_package_id,
        "algorithm_hash": algorithm_hash,
        "scope_hash": scope_hash,
        "template_hash": template.frozen_template_hash,
        "guard_config_hash": guard_hash,
        "data_requirements_hash": requirements_hash,
        "snapshot_hash": snapshot_hash,
        "guard_state": "candidate",
        "checked_trade_days": len(days),
        "candidate_stock_days_before_market_scope": candidate_before_market_scope,
        "out_of_scope_bse_stock_days": out_of_scope_bse,
        "out_of_scope_other_market_stock_days": out_of_scope_other,
        "expected_stock_days_after_market_scope": expected_after_market_scope,
        "excluded_pre_listing_stock_days": excluded_pre,
        "excluded_no_pit_industry_stock_days": excluded_no_industry,
        "lifecycle_unknown_stock_days": lifecycle_unknown,
        "interface_stats": stats,
        "blocking_gap_count": len(gaps),
        "gap_counts_by_type": dict(gap_counts),
        "first_gap": gaps[0] if gaps else None,
        "first_unexplained_gap": gaps[0] if gaps else None,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "not_authorized_for_b6_oos_promotion_or_signal": True,
    }
    output = ROOT / "data/pit/formal_packages" / qualification_package_id
    if output.exists():
        raise RuntimeError(
            f"Qualification package {qualification_package_id} already exists. "
            f"Cannot overwrite existing package. Path: {output}"
        )
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(result, indent=2))
    report = "# Formal SW2021 PIT Qualification\n\n" + "\n".join(
        f"- {key}: {value}" for key, value in result.items() if key != "interface_stats"
    ) + "\n\n## Interface statistics\n" + "\n".join(
        f"- {key}: {value['partitions']} partitions, {value['rows']} rows" for key, value in stats.items()
    ) + "\n\nGuard remains candidate. This result never authorizes B6, OOS, promotion, or a signal.\n"
    (output / "QUALIFICATION_REPORT.md").write_text(report)
    return result


if __name__ == "__main__":
    result = run_qualification()
    print(json.dumps({key: result[key] for key in ("status", "checked_trade_days", "blocking_gap_count", "first_gap")}, indent=2))
    sys.exit(0 if result["status"] == "formal_qualified" else 1)
