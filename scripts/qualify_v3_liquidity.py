from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from scripts.v3_liquidity_source_adapter import resolve_source_amount

ALGORITHM_ID = "avg_amount_20d_shsz_common_v1"
ALGORITHM = {"algorithm_id": ALGORITHM_ID, "window_trading_days": 20, "execution_day_excluded": True, "source_field": "daily.amount", "source_unit": "thousand_yuan", "yuan_multiplier": 1000, "threshold_yuan": 50_000_000, "suspended_day_amount_yuan": 0, "minimum_history_trading_days": 20, "insufficient_history": "unavailable_ineligible", "suspension_evidence_source": "suspend_d", "other_missing": "data_fault", "partial_mean_allowed": False, "window_extension_allowed": False}

def canonical(v: object) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha(path: Path) -> str: return sha_bytes(path.read_bytes())
def read_json(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8"))
def parse_day(v: str) -> date: return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
def day_text(v: date) -> str: return v.strftime("%Y%m%d")

def _files(root: Path, day: date) -> list[Path]:
    return sorted((root / f"trade_date={day_text(day)}").glob("*.parquet"))
def _rows(root: Path, day: date) -> list[dict]:
    import pyarrow.parquet as pq
    files = _files(root, day)
    if not files: raise FileNotFoundError(f"missing partition: {root.name} {day_text(day)}")
    return pq.read_table(files[0]).to_pylist()
def _index(root: Path) -> dict:
    entries = []
    for p in sorted(root.rglob("*.parquet")):
        entries.append({"path": p.relative_to(root).as_posix(), "sha256": sha(p), "byte_size": p.stat().st_size})
    return {"root": root.name, "entry_count": len(entries), "entries": entries, "content_hash": sha_bytes(canonical(entries))}
def _source_inventory(root: Path, start: date, end: date, *, dates: list[date] | None = None) -> dict:
    entries = []
    for p in sorted(root.glob("trade_date=*/part.parquet")):
        raw = p.parent.name.removeprefix("trade_date=")
        d = parse_day(raw)
        if (dates is not None and d in dates) or (dates is None and start <= d <= end):
            entries.append({"path": p.relative_to(root).as_posix(), "sha256": sha(p), "byte_size": p.stat().st_size})
    return {"entry_count": len(entries), "content_hash": sha_bytes(canonical(entries)), "entries": entries}

def _stock_basic_inventory(root: Path, files: list[Path] | None = None) -> dict:
    files = files or sorted(root.rglob("part.parquet"))
    return {"files": [{"path": p.relative_to(root).as_posix(), "sha256": sha(p)} for p in files if p.exists()]}

def _load_codes(lifecycle: Path) -> list[dict]:
    data = read_json(lifecycle)
    if data.get("successor_id") != "49b09326f35936c6": raise ValueError("lifecycle successor binding mismatch")
    if data.get("qualification_status") != "bounded_qualified_vendor_lifecycle": raise ValueError("lifecycle not qualified")
    return data["codes"]

def _load_calendar(calendar: Path) -> list[date]:
    data = read_json(calendar)
    c = data["comparison"]
    parquet=calendar.with_name(data["parquet"]["path"])
    if sha(parquet) != data["parquet"]["sha256"]: raise ValueError("calendar parquet hash mismatch")
    import pyarrow.parquet as pq
    rows=pq.read_table(parquet, columns=["cal_date","is_open"]).to_pylist()
    dates=sorted(parse_day(str(r["cal_date"])) for r in rows if int(r["is_open"]) == 1)
    if dates and (dates[0] != parse_day(c["common_first_date"]) or dates[-1] != parse_day(c["common_last_date"]) or len(dates) != c["common_open_count"]): raise ValueError("common calendar bounds/count mismatch")
    return dates

def _qualified_scope(codes: list[dict], start: date, end: date) -> list[tuple[str, date]]:
    out=[]
    for item in codes:
        list_date=parse_day(item["list_date"])
        delist=parse_day(item["delist_date"]) if item.get("delist_date") else None
        for d in (start + timedelta(days=i) for i in range((end-start).days+1)):
            if list_date <= d and (delist is None or d < delist): out.append((item["ts_code"], d))
    return out

def _membership_scope(membership_records: Path, codes: list[dict], start: date, end: date) -> list[tuple[str, date]]:
    import pyarrow.parquet as pq
    rows=pq.read_table(membership_records, columns=["symbol","effective_from","effective_to"]).to_pylist()
    lifecycle={x["ts_code"]:(parse_day(x["list_date"]), parse_day(x["delist_date"]) if x.get("delist_date") else None) for x in codes}
    out=[]
    for d in (start + timedelta(days=i) for i in range((end-start).days+1)):
        for row in rows:
            s=row["symbol"]; ef=row["effective_from"]; et=row.get("effective_to")
            if s not in lifecycle or ef > d or (et is not None and d > et): continue
            lf,ld=lifecycle[s]
            if lf <= d and (ld is None or d < ld): out.append((s,d))
    return sorted(set(out))

def _formal_lifecycle(stock_basic_root: Path) -> dict[str, tuple[date, date | None]]:
    import pyarrow.parquet as pq
    result={}
    for status in ("L", "D", "P"):
        for row in pq.read_table(stock_basic_root / f"list_status={status}" / "part.parquet", columns=["ts_code","list_date","delist_date"]).to_pylist():
            if row["ts_code"] in result: raise ValueError(f"duplicate stock_basic lifecycle: {row['ts_code']}")
            result[row["ts_code"]]=(parse_day(str(row["list_date"])), parse_day(str(row["delist_date"])) if row.get("delist_date") else None)
    return result

def _load_scope(membership_records: Path, stock_basic_root: Path, calendar: Path, lifecycle: Path, start: date, end: date):
    common=_load_calendar(calendar); life=_formal_lifecycle(stock_basic_root); _load_codes(lifecycle)
    import pyarrow.parquet as pq
    rows=pq.read_table(membership_records, columns=["symbol","effective_from","effective_to"]).to_pylist()
    scope=sorted({(r["symbol"],d) for d in (start+timedelta(days=i) for i in range((end-start).days+1)) for r in rows if r["symbol"] in life and r["effective_from"]<=d and (r.get("effective_to") is None or d<=r["effective_to"]) and life[r["symbol"]][0]<=d and (life[r["symbol"]][1] is None or d<life[r["symbol"]][1])})
    return scope, common, life

def _load_overlay(path: Path | None) -> dict[tuple[str,date], set[str]]:
    if path is None: return {}
    path=Path(path)
    manifest=path / "manifest.json" if path.is_dir() else path
    raw=manifest.read_bytes(); data=json.loads(raw)
    if data.get("schema_version") != "v3_liquidity_suspend_corrective.v1" or data.get("status") != "published":
        raise ValueError("invalid corrective overlay schema")
    if path.is_dir():
        sidecar=manifest.with_name("manifest.json.sha256")
        if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_bytes(raw):
            raise ValueError("corrective overlay sidecar")
        payload={k:v for k,v in data.items() if k != "artifact_id"}
        if data.get("artifact_id") != sha_bytes(canonical(payload))[:16]:
            raise ValueError("corrective overlay artifact id")
    entries=data.get("entries", [])
    allowed={tuple(x) for x in data.get("authorized_faults", [])}
    actual={(e["symbol"],e["trade_date"],e["execution_date"]) for e in entries}
    if actual != allowed or len(entries) != len(allowed):
        raise ValueError("corrective overlay entry set")
    for e in entries:
        canonical_row={"ts_code":e["symbol"],"trade_date":e["trade_date"],"suspend_type":e["source_row"]["suspend_type"]}
        if e["source_row"] != canonical_row or e["corrected_canonical_sha256"] != sha_bytes(canonical(canonical_row)):
            raise ValueError("corrective overlay corrected content")
    return {(e["symbol"],parse_day(e["trade_date"])): {e["symbol"]} for e in entries}

def _check_one(symbol: str, execution: date, common: list[date], daily_root: Path, suspend_root: Path, list_date: date, cache: dict | None = None, overlay: dict | None = None) -> str:
    window=[d for d in common if list_date <= d < execution][-20:]
    if len(window) != 20: return "unavailable_ineligible"
    cache = cache if cache is not None else {}
    for d in window:
        try:
            key=("suspend", d)
            if key not in cache:
                indexed = {}
                for row in _rows(suspend_root, d):
                    indexed.setdefault(row.get("ts_code"), []).append(row)
                cache[key] = indexed
            suspend_rows = list(cache[key].get(symbol, []))
            if overlay and (symbol, d) in overlay:
                suspend_rows.append({"suspend_type": "S"})
        except (OSError, KeyError, TypeError, ValueError): return "data_fault"
        try:
            key=("daily", d)
            if key not in cache: cache[key]={r["ts_code"]: r for r in _rows(daily_root,d)}
            decision = resolve_source_amount(daily_row=cache[key].get(symbol), suspend_rows=suspend_rows)
            if decision["status"] == "data_fault": return "data_fault"
        except (OSError, KeyError, TypeError, ValueError): return "data_fault"
    return "complete"

def _manifest_payload(*, template_hash: str, data_requirements_hash: str, calendar: Path, lifecycle: Path, daily_root: Path, suspend_root: Path, daily_index: Path, suspend_index: Path, membership_records: Path, stock_basic_root: Path, corrective_overlay: Path | None, start: date, end: date, window_dates: list[date], stats: dict) -> dict:
    sources={"daily":{"index_path":daily_index.name,"index_sha256":sha(daily_index),"inventory":_source_inventory(daily_root,start,end,dates=window_dates)},"suspend_d":{"index_path":suspend_index.name,"index_sha256":sha(suspend_index),"inventory":_source_inventory(suspend_root,start,end,dates=window_dates)},"membership_records":{"path":membership_records.name,"sha256":sha(membership_records)},"stock_basic":{"root":stock_basic_root.name,"inventory":_stock_basic_inventory(stock_basic_root)}}
    if corrective_overlay is not None:
        overlay_manifest=Path(corrective_overlay) / "manifest.json" if Path(corrective_overlay).is_dir() else Path(corrective_overlay)
        overlay_data=read_json(overlay_manifest)
        sources["corrective_overlay"]={"path":str(Path(corrective_overlay).name),"sha256":sha(overlay_manifest),"manifest_sha256":sha(overlay_manifest),"artifact_id":overlay_data["artifact_id"],"entry_set":overlay_data["authorized_faults"],"entries":overlay_data["entries"]}
    return {"schema_version":"v3_liquidity_qualification.v1", "status":"published", "algorithm":ALGORITHM, "algorithm_hash":sha_bytes(canonical(ALGORITHM)), "template":{"template_id":"relative_strength_rotation_shsz_sw2021_v3","template_version":"v3","template_hash":template_hash,"data_requirements_hash":data_requirements_hash}, "calendar":{"path":calendar.name,"sha256":sha(calendar),"artifact_id":read_json(calendar).get("artifact_id"),"range":{"start":day_text(start),"end":day_text(end)}}, "lifecycle":{"path":lifecycle.name,"sha256":sha(lifecycle),"successor_id":"49b09326f35936c6"}, "sources":sources, "scope":{"start":day_text(start),"end":day_text(end),"window_dates":[day_text(d) for d in window_dates],"universe":"PIT membership snapshot intersected with formal stock_basic lifecycle","stats":stats}}

def qualify(*, daily_root: Path, suspend_root: Path, calendar: Path, lifecycle: Path, daily_index: Path, suspend_index: Path, output_root: Path, template_hash: str, data_requirements_hash: str, source_range: tuple[date,date], membership_records: Path | None = None, stock_basic_root: Path | None = None, corrective_overlay: Path | None = None) -> dict:
    start,end=source_range; common=_load_calendar(calendar); codes=_load_codes(lifecycle)
    if membership_records and stock_basic_root:
        import pyarrow.parquet as pq
        lifecycle_map=_formal_lifecycle(stock_basic_root)
        rows=pq.read_table(membership_records, columns=["symbol","effective_from","effective_to"]).to_pylist()
        scope=sorted({(r["symbol"],d) for d in (start+timedelta(days=i) for i in range((end-start).days+1)) for r in rows if r["symbol"] in lifecycle_map and r["effective_from"]<=d and (r.get("effective_to") is None or d<=r["effective_to"]) and lifecycle_map[r["symbol"]][0]<=d and (lifecycle_map[r["symbol"]][1] is None or d<lifecycle_map[r["symbol"]][1])})
    else:
        scope=_membership_scope(membership_records,codes,start,end) if membership_records else _qualified_scope(codes,start,end)
    stats={"expected_scope_count":len(scope),"complete_count":0,"unavailable_ineligible_count":0,"data_fault_count":0,"first_data_fault":None}
    cache={}; overlay=_load_overlay(corrective_overlay)
    lifecycle_dates=_formal_lifecycle(stock_basic_root) if stock_basic_root else {}
    for symbol,execution in scope:
        status=_check_one(symbol,execution,common,daily_root,suspend_root,lifecycle_dates.get(symbol, (next((parse_day(x["list_date"]) for x in codes if x["ts_code"]==symbol),start), None))[0],cache,overlay)
        stats[status+"_count"] = stats.get(status+"_count",0)+1
        if status=="data_fault" and stats["first_data_fault"] is None: stats["first_data_fault"]={"ts_code":symbol,"execution_date":day_text(execution)}
    if stats["data_fault_count"]: raise ValueError(f"data_fault: {stats['first_data_fault']}")
    if not scope: raise ValueError("unavailable_ineligible: empty actual membership scope")
    if membership_records is None or stock_basic_root is None: raise ValueError("membership and formal stock_basic bindings are required")
    window_dates=sorted({d for symbol,execution in scope for d in [x for x in common if lifecycle_dates[symbol][0] <= x < execution][-20:]})
    payload=_manifest_payload(template_hash=template_hash,data_requirements_hash=data_requirements_hash,calendar=calendar,lifecycle=lifecycle,daily_root=daily_root,suspend_root=suspend_root,daily_index=daily_index,suspend_index=suspend_index,membership_records=membership_records,stock_basic_root=stock_basic_root,corrective_overlay=corrective_overlay,start=start,end=end,window_dates=window_dates,stats=stats)
    artifact_id=sha_bytes(canonical(payload))[:16]; payload["artifact_id"]=artifact_id
    target=output_root/artifact_id
    if target.exists(): raise FileExistsError(f"immutable artifact exists: {target}")
    target.mkdir(parents=True); raw=canonical(payload); (target/"manifest.json").write_bytes(raw); (target/"manifest.json.sha256").write_text(sha_bytes(raw)+"  manifest.json\n",encoding="utf-8")
    return {"artifact_id":artifact_id,**payload,**stats}
