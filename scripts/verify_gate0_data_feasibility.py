"""
Gate 0 PIT Data Feasibility Verification Script - V2

Collects 2019-2025 market data to verify Tushare interface access.
NOT formal qualification (requires 2010-present).

Usage:
    # Phase B/C worker
    python scripts/verify_gate0_data_feasibility.py collect --worker-id=1 --start-year=2019 --end-year=2020
    
    # Phase D coordinator
    python scripts/verify_gate0_data_feasibility.py merge
    python scripts/verify_gate0_data_feasibility.py probe
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env.local
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from backend.services.strategy_template_library import get_template_by_id


def compute_snapshot_id(template_id: str, template_hash: str, data_req_hash: str) -> str:
    """Snapshot ID = sha256(template_hash + data_req_hash)[:16]."""
    payload = f"{template_hash}:{data_req_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def compute_data_requirements_hash(data_requirements: dict) -> str:
    """Hash data requirements (excluding runtime metadata)."""
    canonical = json.dumps(data_requirements, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:32]


def get_data_requirements() -> dict:
    """Freeze data requirements for relative_strength_rotation_v1 template."""
    return {
        "template_id": "relative_strength_rotation_v1",
        "interfaces": {
            "daily": {"fields": "ts_code,trade_date,open,high,low,close,vol,amount"},
            "daily_basic": {"fields": "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv"},
            "stk_limit": {"fields": "ts_code,trade_date,up_limit,down_limit"},
            "adj_factor": {"fields": "ts_code,trade_date,adj_factor"},
            "index_daily": {"fields": "ts_code,trade_date,close,vol,amount"},
            "trade_cal": {"fields": "exchange,cal_date,is_open,pretrade_date"},
            "stock_basic": {"fields": "ts_code,symbol,name,market,exchange,list_status,list_date,delist_date"},
            "stock_st": {"fields": "ts_code,name,trade_date,type"},  # ponytail: 2016-01-04+ ST daily list
            "namechange": {"fields": "ts_code,name,start_date,end_date"},
            "suspend_d": {"fields": "native_default"},  # ponytail: uses ts_code,trade_date,suspend_timing,suspend_type
            "index_classify": {"fields": "index_code,industry_code,level,is_pub"},
            "index_member_all": {"fields": "ts_code,l1_code,l1_name,in_date,out_date,is_new"},  # ponytail: merge Y/N
        },
        "benchmarks": ["000300.SH", "000905.SH"],  # CSI 300, CSI 500
        "control_group": {
            "type": "same_sw_l1_industry_excluding_self",
            "source": "index_member_all",
            "fields": "ts_code,l1_code,l1_name,in_date,out_date,is_new",
            "pit_rule": "merge is_new=Y/N, filter by in_date <= as_of_date AND (out_date IS NULL OR out_date >= as_of_date)",
        },
        "guard_rules": {
            "min_avg_amount_20d": 50000000,
            "market_regime_allowed": ["green", "yellow"],
        },
    }


def get_vendor_industry_data_requirements() -> dict:
    """ponytail: vendor industry variant"""
    project_root = Path(__file__).parent.parent
    vendor_dir = project_root / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
    
    # ponytail: read real package hash from manifest
    manifest_path = vendor_dir / "manifest.json"
    with open(manifest_path) as f:
        vendor_manifest = json.load(f)
    package_hash = vendor_manifest["package_sha256"]
    
    base = get_data_requirements()
    base["template_id"] = "relative_strength_rotation_vendor_industry_v1"
    base["control_group"] = {
        "type": "same_vendor_daily_industry_excluding_self",
        "source": "vendor_daily_industry_v1",
    }
    base["vendor"] = {
        "package_hash": package_hash,
        "industry_semantics_hash": hashlib.sha256(
            (vendor_dir / "industry_semantics.json").read_bytes()
        ).hexdigest(),
        "provides": ["name", "industry"],
        "rejected": ["是否ST", "均线", "涨幅", "量比", "涨停", "估值", "市值"]
    }
    return base


def get_staging_path(snapshot_id: str, worker_id: int) -> Path:
    """Get worker staging directory."""
    project_root = Path(__file__).parent.parent
    return project_root / "data" / "pit" / "tushare" / ".staging" / snapshot_id / f"worker_{worker_id}"


def get_snapshot_path(snapshot_id: str) -> Path:
    """Get final snapshot directory."""
    project_root = Path(__file__).parent.parent
    return project_root / "data" / "pit" / "tushare" / snapshot_id


def collect_worker_data(worker_id: int, start_year: int, end_year: int) -> dict[str, Any]:
    """Phase B/C: Collect data for assigned years."""
    config = TushareConfig.from_env()
    client = TushareClient(config)
    
    template = get_template_by_id("relative_strength_rotation_v1")
    if not template:
        raise ValueError("Template not found")
    
    data_req = get_data_requirements()
    data_req_hash = compute_data_requirements_hash(data_req)
    snapshot_id = compute_snapshot_id(template.template_id, template.template_hash, data_req_hash)
    
    staging_dir = get_staging_path(snapshot_id, worker_id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "worker_id": worker_id,
        "snapshot_id": snapshot_id,
        "start_year": start_year,
        "end_year": end_year,
        "interfaces": {},
        "errors": [],
    }
    
    # Collect market data (Phase B) or lifecycle data (Phase C)
    if worker_id <= 3:  # Phase B: market data
        stats["interfaces"] = _collect_market_data(client, data_req, staging_dir, start_year, end_year)
    else:  # Phase C: lifecycle data
        stats["interfaces"] = _collect_lifecycle_data(client, data_req, staging_dir, worker_id)
    
    # Write worker stats
    stats_path = staging_dir / "worker_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    
    return stats


def _collect_market_data(client: TushareClient, data_req: dict, staging_dir: Path, start_year: int, end_year: int) -> dict:
    """Collect daily/daily_basic/stk_limit/adj_factor/index_daily - minimal feasibility sample."""
    interfaces = {}
    
    # Trade calendar first
    cal_result = _collect_interface(client, "trade_cal", data_req["interfaces"]["trade_cal"], 
                                     {"exchange": "SSE", "start_date": f"{start_year}0101", "end_date": f"{end_year}1231"})
    interfaces["trade_cal"] = cal_result
    if cal_result["status"] == "ok":
        cal_df = cal_result["data"]
        _save_parquet(staging_dir / "trade_cal.parquet", cal_df)
    else:
        return interfaces  # Can't proceed without calendar
    
    # Stock list
    stock_result = _collect_interface(client, "stock_basic", data_req["interfaces"]["stock_basic"],
                                      {"exchange": "", "list_status": "L"})
    interfaces["stock_basic"] = stock_result
    if stock_result["status"] != "ok":
        return interfaces
    
    # ponytail: 1 sample per board by prefix
    stock_df = stock_result["data"]
    samples = {
        'main': stock_df[stock_df['ts_code'].str.startswith('60')].iloc[0]['ts_code'],
        'chinext': stock_df[stock_df['ts_code'].str.startswith('30')].iloc[0]['ts_code'],
        'star': stock_df[stock_df['ts_code'].str.startswith(('688', '689'))].iloc[0]['ts_code'],
    }
    stock_codes = list(samples.values())
    _save_parquet(staging_dir / "stock_basic.parquet", stock_result["data"])
    
    # ponytail: 1 month sample per year per interface
    for interface in ["daily", "daily_basic", "stk_limit", "adj_factor"]:
        interface_data = []
        for year in range(start_year, end_year + 1):
            # Just January each year
            for ts_code in stock_codes:
                result = _collect_interface(client, interface, data_req["interfaces"][interface],
                                            {"ts_code": ts_code, "start_date": f"{year}0101", "end_date": f"{year}0131"})
                if result["status"] == "ok" and len(result["data"]) > 0:
                    interface_data.append(result["data"])
                    break  # First success proves interface works
        
        if interface_data:
            combined = pd.concat(interface_data, ignore_index=True)
            _save_parquet(staging_dir / f"{interface}.parquet", combined)
            interfaces[interface] = {"status": "ok", "row_count": len(combined), "coverage": f"{start_year}-{end_year}"}
        else:
            interfaces[interface] = {"status": "empty", "row_count": 0}
    
    # Index data for benchmarks - 1 year sample
    index_data = []
    for idx in data_req["benchmarks"]:
        result = _collect_interface(client, "index_daily", data_req["interfaces"]["index_daily"],
                                    {"ts_code": idx, "start_date": f"{start_year}0101", "end_date": f"{start_year}1231"})
        if result["status"] == "ok":
            index_data.append(result["data"])
    
    if index_data:
        combined = pd.concat(index_data, ignore_index=True)
        _save_parquet(staging_dir / "index_daily.parquet", combined)
        interfaces["index_daily"] = {"status": "ok", "row_count": len(combined)}
    
    return interfaces


def _collect_lifecycle_data(client: TushareClient, data_req: dict, staging_dir: Path, worker_id: int) -> dict:
    """Phase C: Collect lifecycle/membership data."""
    interfaces = {}
    
    if worker_id == 4:  # Stock lifecycle
        for interface in ["stock_basic", "namechange"]:
            result = _collect_interface(client, interface, data_req["interfaces"][interface], {})
            interfaces[interface] = result
            if result["status"] == "ok":
                _save_parquet(staging_dir / f"{interface}.parquet", result["data"])
        
        # ponytail: suspend_d quarterly 2019-2025, monthly if quarter hits 5000
        suspend_partitions = []
        for year in range(2019, 2026):
            for q_start, q_end in [("0101", "0331"), ("0401", "0630"), ("0701", "0930"), ("1001", "1231")]:
                result = _collect_interface(client, "suspend_d", data_req["interfaces"]["suspend_d"],
                                           {"start_date": f"{year}{q_start}", "end_date": f"{year}{q_end}"})
                if result["status"] == "ok":
                    if len(result["data"]) == 5000:
                        # ponytail: quarterly truncated, refine to monthly
                        import calendar
                        q_month_start = int(q_start[:2])
                        months = []
                        for offset in range(3):
                            m = q_month_start + offset
                            last_day = calendar.monthrange(year, m)[1]
                            months.append((f"{m:02d}01", f"{m:02d}{last_day}"))
                        
                        for m_start, m_end in months:
                            m_result = _collect_interface(client, "suspend_d", data_req["interfaces"]["suspend_d"],
                                                         {"start_date": f"{year}{m_start}", "end_date": f"{year}{m_end}"})
                            if m_result["status"] == "ok":
                                suspend_partitions.append(m_result["data"])
                    else:
                        suspend_partitions.append(result["data"])
        
        if suspend_partitions:
            combined = pd.concat(suspend_partitions, ignore_index=True)
            # ponytail: check final for any 5000-row partition
            max_partition = combined.groupby(pd.to_datetime(combined['trade_date'], format='%Y%m%d').dt.to_period('M')).size().max()
            if max_partition == 5000:
                interfaces["suspend_d"] = {"status": "truncated", "row_count": len(combined), "reason": "monthly partition hit 5000 limit"}
            else:
                _save_parquet(staging_dir / "suspend_d.parquet", combined)
                interfaces["suspend_d"] = {"status": "ok", "row_count": len(combined), "partitions": len(suspend_partitions)}
        else:
            interfaces["suspend_d"] = {"status": "empty", "row_count": 0}
    
    elif worker_id == 5:  # Index membership
        for interface in ["index_classify", "index_member_all"]:
            result = _collect_interface(client, interface, data_req["interfaces"][interface], {})
            interfaces[interface] = result
            if result["status"] == "ok":
                _save_parquet(staging_dir / f"{interface}.parquet", result["data"])
    
    elif worker_id == 6:  # Completeness check
        interfaces["completeness"] = {"status": "ok", "note": "Stats only, no data collected"}
    
    return interfaces


def _collect_interface(client: TushareClient, api_name: str, fields_config: dict, params: dict) -> dict:
    """Query Tushare interface and return result."""
    try:
        fields = fields_config.get("fields")
        # ponytail: suspend_d needs native call
        if fields == "native_default":
            df = getattr(client.pro, api_name)(**params)
        else:
            df = client.query(api_name, fields=fields, **params)
        
        if df is None or len(df) == 0:
            return {"status": "empty", "row_count": 0, "params": params}
        
        return {
            "status": "ok",
            "row_count": len(df),
            "params": params,
            "data": df,
        }
    except Exception as e:
        error_msg = str(e)
        if "2002" in error_msg or "permission" in error_msg.lower():
            return {"status": "permission_denied", "error": error_msg, "params": params}
        return {"status": "error", "error": error_msg, "params": params}


def _save_parquet(path: Path, df: pd.DataFrame) -> None:
    """Save DataFrame to Parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")


def _write_verified_partition(path: Path, df: pd.DataFrame) -> bool:
    """Atomically land a Parquet partition; return True only for a hash-verified resume skip."""
    digest_path = path.with_suffix(path.suffix + ".sha256")
    if path.exists() and digest_path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest_path.read_text().strip() == digest:
            return True
        raise ValueError(f"Partition hash mismatch: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    df.to_parquet(partial, index=False, engine="pyarrow")
    partial.replace(path)
    digest_path.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    return False


def _call_formal_api(
    client: TushareClient,
    api_name: str,
    *,
    allow_empty: bool,
    **params: Any,
) -> pd.DataFrame:
    """Call a native Tushare endpoint, retrying transient empty required inputs."""
    last_error: Exception | None = None
    for attempt in range(client.config.retry_attempts):
        try:
            client._enforce_rate_limit()
            frame = getattr(client.pro, api_name)(**params)
            if frame is None:
                raise ValueError(f"{api_name} returned None")
            if frame.empty and not allow_empty:
                raise ValueError(f"{api_name} returned an empty required partition")
            return frame
        except Exception as error:
            last_error = error
            if attempt < client.config.retry_attempts - 1:
                time.sleep(client.config.retry_delay_seconds * (2**attempt))
    raise ValueError(f"Formal collection API failed: {api_name}; error={last_error}")


def _formal_api_allows_empty(api_name: str) -> bool:
    """Event feeds and stock-status partitions may correctly have no rows."""
    return api_name in {"stock_basic", "stock_st", "suspend_d", "namechange", "index_member_all"}


def formal_collect(max_days: int | None = None) -> dict:
    """Collect the scope-matching formal window, resumably, without qualifying it."""
    plan = run_formal_plan()
    if plan["status"] != "ready_to_collect":
        raise ValueError(f"Formal plan not ready: {plan}")
    config = TushareConfig.from_env()
    config.requests_per_minute = 160
    config.retry_attempts = 2
    client = TushareClient(config)
    snapshot_id = hashlib.sha256(
        f"{plan['template_hash']}:{plan['guard_config_hash']}:{plan['data_requirements_hash']}".encode()
    ).hexdigest()[:16]
    root = get_staging_path(snapshot_id, 0) / "formal"
    def call(api_name: str, *, allow_empty: bool = True, **params: Any) -> pd.DataFrame:
        return _call_formal_api(client, api_name, allow_empty=allow_empty, **params)

    cal = call("trade_cal", allow_empty=False, exchange="SSE", start_date=plan["window_start"], end_date=plan["last_closed_trading_day"])
    _write_verified_partition(root / "trade_cal" / "part.parquet", cal)
    stocks: list[str] = []
    stock_fields = get_data_requirements()["interfaces"]["stock_basic"]["fields"]
    for status in ("L", "D", "P"):
        stock_df = call("stock_basic", allow_empty=_formal_api_allows_empty("stock_basic"), exchange="", list_status=status, fields=stock_fields)
        _write_verified_partition(root / "stock_basic" / f"list_status={status}" / "part.parquet", stock_df)
        if "ts_code" in stock_df:
            stocks.extend(stock_df["ts_code"].dropna().astype(str).tolist())
    stocks = sorted(set(stocks))
    for source in ("SW2014", "SW2021"):
        directory = call("index_classify", allow_empty=False, level="L1", src=source)
        _write_verified_partition(root / "index_classify" / f"src={source}" / "part.parquet", directory)
    days = sorted(str(value) for value in cal.loc[cal["is_open"].astype(int) == 1, "cal_date"])
    if max_days is not None:
        days = days[:max_days]
    completed = 0
    for trade_date in days:
        for iface in ("daily", "daily_basic", "stk_limit", "adj_factor", "stock_st"):
            path = root / iface / f"trade_date={trade_date}" / "part.parquet"
            if path.exists() and path.with_suffix(".parquet.sha256").exists():
                _write_verified_partition(path, pd.DataFrame())
                continue
            df = call(iface, allow_empty=_formal_api_allows_empty(iface), trade_date=trade_date)
            if iface != "stock_st" and (df.empty or set(df["trade_date"].astype(str)) != {trade_date}):
                raise ValueError(f"{iface} date mismatch or empty for {trade_date}")
            _write_verified_partition(path, df)
        for benchmark in get_data_requirements()["benchmarks"]:
            df = call("index_daily", allow_empty=False, ts_code=benchmark, trade_date=trade_date)
            if df.empty or set(df["trade_date"].astype(str)) != {trade_date}:
                raise ValueError(f"index_daily date mismatch or empty for {benchmark} {trade_date}")
            _write_verified_partition(root / "index_daily" / f"ts_code={benchmark}" / f"trade_date={trade_date}" / "part.parquet", df)
        suspended = call("suspend_d", trade_date=trade_date)
        _write_verified_partition(root / "suspend_d" / f"trade_date={trade_date}" / "part.parquet", suspended)
        completed += 1
        (root / "progress.json").write_text(json.dumps({"status": "formal_collect_started", "completed_days": completed, "total_days": len(days), "snapshot_id": snapshot_id}))
    if max_days is None:
        for ts_code in stocks:
            names = call("namechange", ts_code=ts_code)
            _write_verified_partition(root / "namechange" / f"ts_code={ts_code}" / "part.parquet", names)
            for is_new in ("Y", "N"):
                members = call("index_member_all", ts_code=ts_code, is_new=is_new)
                _write_verified_partition(root / "index_member_all" / f"is_new={is_new}" / f"ts_code={ts_code}" / "part.parquet", members)
    return {"status": "formal_collect_started", "snapshot_id": snapshot_id, "completed_days": completed, "total_days": len(days), "root": str(root)}


def merge_staging(snapshot_id: str) -> dict:
    """Phase D: Merge all worker staging to final snapshot."""
    staging_root = Path(__file__).parent.parent / "data" / "pit" / "tushare" / ".staging" / snapshot_id
    final_dir = get_snapshot_path(snapshot_id)
    
    if not staging_root.exists():
        raise ValueError(f"Staging directory not found: {staging_root}")
    
    final_dir.mkdir(parents=True, exist_ok=True)
    
    # Merge worker outputs
    all_stats = []
    for worker_dir in staging_root.glob("worker_*"):
        stats_file = worker_dir / "worker_stats.json"
        if stats_file.exists():
            with open(stats_file) as f:
                all_stats.append(json.load(f))
        
        # Copy Parquet files
        for parquet in worker_dir.glob("*.parquet"):
            dest = final_dir / parquet.name
            if dest.exists():
                # Merge DataFrames
                existing = pd.read_parquet(dest)
                new = pd.read_parquet(parquet)
                combined = pd.concat([existing, new], ignore_index=True).drop_duplicates()
                combined.to_parquet(dest, index=False, engine="pyarrow")
            else:
                shutil.copy(parquet, dest)
    
    # Generate manifest
    # ponytail: recompute interface_status from final merged files, not stale worker stats
    interface_status = {}
    for parquet in final_dir.glob("*.parquet"):
        iface = parquet.stem
        df = pd.read_parquet(parquet)
        interface_status[iface] = {"status": "ok", "row_count": len(df)}
    
    # ponytail: check for truncated status from worker stats (data wasn't written if truncated)
    for stat in all_stats:
        for iface, iface_stat in stat.get("interfaces", {}).items():
            if iface_stat.get("status") == "truncated":
                interface_status[iface] = iface_stat
    
    manifest = {
        "snapshot_id": snapshot_id,
        "provider": "tushare",
        "retrieval_date": str(date.today()),
        "data_requirements_hash": compute_data_requirements_hash(get_data_requirements()),
        "worker_stats": all_stats,
        "interfaces_probed": list(interface_status.keys()),
        "interface_status": interface_status,
    }
    
    manifest_path = final_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    # Compute manifest hash
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (final_dir / "manifest.sha256").write_text(manifest_hash)
    
    return manifest


def run_feasibility_probe(snapshot_id: str) -> dict:
    """Phase D: Run feasibility probe on merged data."""
    final_dir = get_snapshot_path(snapshot_id)
    manifest_path = final_dir / "manifest.json"
    
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {manifest_path}")
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Check critical interfaces
    critical_interfaces = ["daily", "daily_basic", "trade_cal", "stock_basic"]
    missing = [iface for iface in critical_interfaces if iface not in manifest["interfaces_probed"]]
    
    if missing:
        return {
            "gate0_status": "not_qualified",
            "gate0_reason": f"Missing critical interfaces: {missing}",
            "feasibility_probe_passed": False,
        }
    
    # ponytail: Check for truncated interfaces
    if "interface_status" in manifest:
        truncated = [k for k, v in manifest["interface_status"].items() if v.get("status") == "truncated"]
        if truncated:
            return {
                "gate0_status": "truncated",
                "gate0_reason": f"Truncated interfaces: {truncated}",
                "feasibility_probe_passed": False,
                "truncated_details": {k: manifest["interface_status"][k] for k in truncated},
            }
    
    # Check data files exist
    for iface in critical_interfaces:
        parquet_path = final_dir / f"{iface}.parquet"
        if not parquet_path.exists():
            return {
                "gate0_status": "not_qualified",
                "gate0_reason": f"Missing data file: {iface}.parquet",
                "feasibility_probe_passed": False,
            }
    
    # Check coverage (2019-2025 for feasibility)
    trade_cal_df = pd.read_parquet(final_dir / "trade_cal.parquet")
    coverage_start = trade_cal_df["cal_date"].min()
    coverage_end = trade_cal_df["cal_date"].max()
    
    result = {
        "gate0_status": "feasibility_probe_passed",
        "gate0_reason": None,
        "feasibility_probe_passed": True,
        "coverage_start": str(coverage_start),
        "coverage_end": str(coverage_end),
        "interfaces_probed": manifest["interfaces_probed"],
        "note": "2019-2025 feasibility only, NOT formal_qualified (requires 2010-present)",
    }
    
    # Update manifest with probe results
    manifest.update(result)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    # ponytail: recompute hash after updating manifest
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (final_dir / "manifest.sha256").write_text(manifest_hash)
    
    return result


def run_formal_plan() -> dict:
    """Check if formal scope can be frozen."""
    config = TushareConfig.from_env()
    client = TushareClient(config)
    
    result = {"status": "ready_to_collect", "window_start": "20160104"}
    
    # Get last closed trading day from trade_cal
    try:
        cal_df = client.query("trade_cal", fields="exchange,cal_date,is_open", exchange="SSE", 
                             start_date="20160104", end_date=date.today().strftime("%Y%m%d"))
        # ponytail: sort ascending, take last
        trading_days = sorted(cal_df[cal_df["is_open"] == 1]["cal_date"].astype(str).tolist())
        if trading_days:
            result["last_closed_trading_day"] = trading_days[-1]
        else:
            result["status"] = "blocked"
            result["blockers"] = [{"item": "trade_cal", "reason": "No trading days found"}]
    except Exception as e:
        result["status"] = "blocked"
        result["blockers"] = [{"item": "trade_cal", "reason": str(e)}]
    
    # Compute hashes
    from backend.services.strategy_template_library import get_template_by_id
    import yaml
    
    template = get_template_by_id("relative_strength_rotation_v1")
    result["template_hash"] = template.frozen_template_hash if template else None
    result["data_requirements_hash"] = compute_data_requirements_hash(get_data_requirements())
    
    with open(Path(__file__).parent.parent / "backend/config/market_regime_thresholds.yaml") as f:
        guard_cfg = yaml.safe_load(f)
    semantic = {k: guard_cfg[k] for k in ["version", "candidate_rules", "stress_windows", "normal_window", 
                                           "zero_gap_rule", "normal_window_block_ratio_max", "required_pit_inputs"]}
    result["guard_config_hash"] = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    
    return result


def run_formal_qualify_daily() -> dict:
    """Real formal daily PIT qualification with all audit rules."""
    project_root = Path(__file__).parent.parent
    formal_dir = project_root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
    vendor_dir = project_root / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
    
    # Get new vendor_industry template (not old v1)
    from backend.services.strategy_template_library import get_template_by_id
    template = get_template_by_id("relative_strength_rotation_vendor_industry_v1")
    if not template:
        return {"status": "not_qualified", "blocker": "template not found: relative_strength_rotation_vendor_industry_v1"}
    
    template_hash = template.frozen_template_hash
    
    # Compute guard config hash
    with open(project_root / "backend/config/market_regime_thresholds.yaml") as f:
        guard_cfg = yaml.safe_load(f)
    semantic = {k: guard_cfg[k] for k in ["version", "candidate_rules", "stress_windows", "normal_window", 
                                           "zero_gap_rule", "normal_window_block_ratio_max", "required_pit_inputs"]}
    guard_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    
    # Compute data requirements hash
    req = get_vendor_industry_data_requirements()
    req_hash = compute_data_requirements_hash(req)
    
    # Compute snapshot hash from real sidecar hashes
    tushare_hashes = []
    for iface in ["daily", "daily_basic", "stk_limit", "adj_factor", "trade_cal", "stock_basic", "index_classify", "stock_st", "suspend_d"]:
        iface_dir = formal_dir / iface
        if not iface_dir.exists():
            return {"status": "not_qualified", "blocker": f"Tushare interface missing: {iface}"}
        
        # Collect all partition hashes
        for sidecar in sorted(iface_dir.rglob("*.sha256")):
            tushare_hashes.append(sidecar.read_text().strip())
    
    # Add vendor hashes
    vendor_hashes = [
        req["vendor"]["package_hash"],
        req["vendor"]["industry_semantics_hash"]
    ]
    
    # Benchmark index_daily partitions
    for bench in ["000300.SH", "000905.SH"]:
        bench_dir = formal_dir / "index_daily" / f"ts_code={bench}"
        if not bench_dir.exists():
            return {"status": "not_qualified", "blocker": f"benchmark {bench} directory missing"}
        for sidecar in sorted(bench_dir.rglob("*.sha256")):
            tushare_hashes.append(sidecar.read_text().strip())
    
    snapshot_hash = hashlib.sha256("|".join(sorted(tushare_hashes + vendor_hashes)).encode()).hexdigest()
    
    # Compute scope hash
    scope_hash = hashlib.sha256(f"{template_hash}|{guard_hash}|{req_hash}|{snapshot_hash}".encode()).hexdigest()[:16]
    
    # Read trade calendar
    cal_path = formal_dir / "trade_cal" / "part.parquet"
    if not cal_path.exists():
        return {"status": "not_qualified", "blocker": "trade_cal partition missing"}
    
    cal_df = pd.read_parquet(cal_path)
    trading_days = sorted(cal_df[cal_df["is_open"].astype(int) == 1]["cal_date"].astype(str).tolist())
    
    gaps = []
    interface_row_counts = {}
    
    for trade_date in trading_days:
        # Check daily/daily_basic/stk_limit/adj_factor exist and date matches
        for iface in ["daily", "daily_basic", "stk_limit", "adj_factor"]:
            part_path = formal_dir / iface / f"trade_date={trade_date}" / "part.parquet"
            if not part_path.exists():
                gaps.append(f"{iface} missing for {trade_date}")
                continue
            
            df = pd.read_parquet(part_path)
            if not df.empty:
                dates = df["trade_date"].astype(str).unique()
                if set(dates) != {trade_date}:
                    gaps.append(f"{iface} date mismatch for {trade_date}: got {dates}")
        
        # stock_st and suspend_d sparse: empty partition OK
        for sparse_iface in ["stock_st", "suspend_d"]:
            part_path = formal_dir / sparse_iface / f"trade_date={trade_date}" / "part.parquet"
            if not part_path.exists():
                gaps.append(f"{sparse_iface} partition missing for {trade_date}")
        
        # Benchmarks must have exactly one row per day
        for bench in ["000300.SH", "000905.SH"]:
            bench_path = formal_dir / "index_daily" / f"ts_code={bench}" / f"trade_date={trade_date}" / "part.parquet"
            if not bench_path.exists():
                gaps.append(f"benchmark {bench} missing for {trade_date}")
                continue
            
            df = pd.read_parquet(bench_path)
            if df.empty or set(df["trade_date"].astype(str)) != {trade_date}:
                gaps.append(f"benchmark {bench} date mismatch or empty for {trade_date}")
        
        # Vendor daily snapshot must exist
        # ponytail: vendor CSV is in project root "不复权" directory, path from manifest
        with open(vendor_dir / "manifest.json") as f:
            vendor_manifest = json.load(f)
        
        # Find file for this trade_date
        vendor_file = None
        for file_entry in vendor_manifest["files"]:
            if file_entry["date"] == trade_date:
                vendor_file = project_root / file_entry["path"]
                break
        
        if vendor_file is None or not vendor_file.exists():
            gaps.append(f"vendor snapshot missing for {trade_date}")
            continue
        
        # Validate vendor name and industry non-empty
        try:
            # ponytail: try utf-8-sig first (BOM), fallback to gbk
            try:
                vendor_df = pd.read_csv(vendor_file, encoding='utf-8-sig')
            except UnicodeDecodeError:
                vendor_df = pd.read_csv(vendor_file, encoding='gbk')
            if vendor_df.empty:
                gaps.append(f"vendor snapshot empty for {trade_date}")
                continue
            if '代码' not in vendor_df.columns or '名称' not in vendor_df.columns or '所属行业' not in vendor_df.columns:
                gaps.append(f"vendor missing required columns for {trade_date}")
                continue
            if vendor_df['代码'].duplicated().any():
                gaps.append(f"vendor duplicate codes for {trade_date}")
            if vendor_df['名称'].isna().any() or (vendor_df['名称'] == '').any():
                gaps.append(f"vendor empty name for {trade_date}")
            if vendor_df['所属行业'].isna().any() or (vendor_df['所属行业'] == '').any():
                gaps.append(f"vendor empty industry for {trade_date}")
        except Exception as e:
            gaps.append(f"vendor read error for {trade_date}: {str(e)}")
    
    # Collect interface stats
    for iface in ["daily", "daily_basic", "stk_limit", "adj_factor", "stock_st", "suspend_d"]:
        total_rows = 0
        partition_count = 0
        for part in sorted((formal_dir / iface).rglob("part.parquet")):
            df = pd.read_parquet(part)
            total_rows += len(df)
            partition_count += 1
        interface_row_counts[iface] = {"partitions": partition_count, "rows": total_rows}
    
    for bench in ["000300.SH", "000905.SH"]:
        total_rows = 0
        partition_count = 0
        bench_dir = formal_dir / "index_daily" / f"ts_code={bench}"
        if bench_dir.exists():
            for part in sorted(bench_dir.rglob("part.parquet")):
                df = pd.read_parquet(part)
                total_rows += len(df)
                partition_count += 1
        interface_row_counts[f"index_daily_{bench}"] = {"partitions": partition_count, "rows": total_rows}
    
    if gaps:
        result = {
            "status": "not_qualified",
            "blocker": f"Found {len(gaps)} gaps",
            "first_gap": gaps[0],
            "total_gaps": len(gaps),
            "checked_trade_days": len(trading_days),
            "scope_hash": scope_hash,
            "template_hash": template_hash,
            "guard_config_hash": guard_hash,
            "data_requirements_hash": req_hash,
            "snapshot_hash": snapshot_hash,
            "interface_stats": interface_row_counts
        }
    else:
        result = {
            "status": "formal_qualified",
            "checked_trade_days": len(trading_days),
            "scope_hash": scope_hash,
            "template_hash": template_hash,
            "guard_config_hash": guard_hash,
            "data_requirements_hash": req_hash,
            "snapshot_hash": snapshot_hash,
            "coverage_start": trading_days[0],
            "coverage_end": trading_days[-1],
            "interface_stats": interface_row_counts
        }
    
    # Write manifest
    out_dir = project_root / "data/pit/formal_packages" / scope_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "manifest.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    # Write report
    if result["status"] == "formal_qualified":
        report = f"""# Formal Daily PIT Qualification

**Scope:** {scope_hash}  
**Status:** {result['status']}  
**Template:** relative_strength_rotation_vendor_industry_v1  
**Coverage:** {result['coverage_start']} to {result['coverage_end']}  
**Checked:** {result['checked_trade_days']} trading days

## Scope Keys
- Template: {template_hash}
- Guard config: {guard_hash}
- Data requirements: {req_hash}
- Snapshot: {snapshot_hash}

## Interface Stats
"""
        for iface, stats in result["interface_stats"].items():
            report += f"- {iface}: {stats['partitions']} partitions, {stats['rows']} rows\n"
    else:
        report = f"""# Formal Daily PIT Qualification

**Scope:** {scope_hash}  
**Status:** {result['status']}  
**Blocker:** {result['blocker']}  
**Checked:** {result['checked_trade_days']} trading days

## Scope Keys
- Template: {template_hash}
- Guard config: {guard_hash}
- Data requirements: {req_hash}
- Snapshot: {snapshot_hash}

## Gaps
Total: {result['total_gaps']}  
First: {result['first_gap']}

## Interface Stats
"""
        for iface, stats in result["interface_stats"].items():
            report += f"- {iface}: {stats['partitions']} partitions, {stats['rows']} rows\n"
    
    (project_root / "docs/verification" / "FORMAL_DAILY_PIT_QUALIFICATION.md").write_text(report)
    
    return result


def formal_collect_single_day(trade_date: str, staging_dir: Path, client: TushareClient, req: dict) -> dict:
    """Collect all required interfaces for one trading day."""
    stats = {"trade_date": trade_date, "interfaces": {}, "errors": []}
    
    # Daily market: daily, daily_basic, stk_limit, adj_factor, stock_st
    for iface in ["daily", "daily_basic", "stk_limit", "adj_factor"]:
        df = getattr(client.pro, iface)(trade_date=trade_date)
        if len(df) > 0 and str(df["trade_date"].iloc[0]) != trade_date:
            stats["errors"].append(f"{iface} date mismatch: got {df['trade_date'].iloc[0]}")
            continue
        _save_parquet(staging_dir / f"{iface}_{trade_date}.parquet", df)
        stats["interfaces"][iface] = {"rows": len(df), "hash": hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()[:16]}
    
    df_st = client.pro.stock_st(trade_date=trade_date)
    _save_parquet(staging_dir / f"stock_st_{trade_date}.parquet", df_st)
    stats["interfaces"]["stock_st"] = {"rows": len(df_st), "hash": hashlib.sha256(df_st.to_csv(index=False).encode()).hexdigest()[:16] if len(df_st) > 0 else "empty"}
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Gate 0 PIT data feasibility verification")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Collect command
    collect_parser = subparsers.add_parser("collect", help="Collect data as worker")
    collect_parser.add_argument("--worker-id", type=int, required=True)
    collect_parser.add_argument("--start-year", type=int, required=True)
    collect_parser.add_argument("--end-year", type=int, required=True)
    
    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge worker outputs")
    merge_parser.add_argument("--snapshot-id", type=str, required=True)
    
    # Probe command
    probe_parser = subparsers.add_parser("probe", help="Run feasibility probe")
    probe_parser.add_argument("--snapshot-id", type=str, required=True)
    
    # Formal qualify daily
    qualify_parser = subparsers.add_parser("formal-qualify-daily", help="Qualify formal daily PIT package")
    
    args = parser.parse_args()
    
    if args.command == "collect":
        stats = collect_worker_data(args.worker_id, args.start_year, args.end_year)
        print(json.dumps(stats, indent=2, default=str))
    
    elif args.command == "merge":
        manifest = merge_staging(args.snapshot_id)
        print(json.dumps(manifest, indent=2))
    
    elif args.command == "probe":
        result = run_feasibility_probe(args.snapshot_id)
        print(json.dumps(result, indent=2))
    
    elif args.command == "formal-plan":
        result = run_formal_plan()
        print(json.dumps(result, indent=2))
    
    elif args.command == "formal-qualify-daily":
        result = run_formal_qualify_daily()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result["status"] == "formal_qualified" else 1)

    elif args.command == "formal-collect":
        print(json.dumps(formal_collect(args.max_days), indent=2))


if __name__ == "__main__":
    main()
