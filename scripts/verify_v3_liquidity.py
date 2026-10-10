from __future__ import annotations
import hashlib, json, math
from datetime import date, timedelta
from pathlib import Path
from scripts.qualify_v3_liquidity import ALGORITHM, canonical, parse_day, sha, sha_bytes, _files, _rows, _load_codes, _load_calendar, _qualified_scope, _check_one, _source_inventory, _load_scope, _stock_basic_inventory, _load_overlay

def verify(artifact_dir: Path, *, daily_root: Path, suspend_root: Path, calendar: Path, lifecycle: Path, daily_index: Path, suspend_index: Path, membership_records: Path, stock_basic_root: Path, corrective_overlay: Path | None = None) -> dict:
    try:
        manifest_path=artifact_dir/"manifest.json"; raw=manifest_path.read_bytes(); manifest=json.loads(raw)
        if sha_bytes(raw) != manifest_path.with_name("manifest.json.sha256").read_text().split()[0]: return {"status":"invalid","reason":"manifest sidecar"}
        if manifest["algorithm"] != ALGORITHM or manifest["algorithm_hash"] != sha_bytes(canonical(ALGORITHM)): return {"status":"invalid","reason":"algorithm binding"}
        if manifest["calendar"]["sha256"] != sha(calendar): return {"status":"invalid","reason":"calendar binding"}
        if manifest["lifecycle"]["sha256"] != sha(lifecycle) or manifest["lifecycle"]["successor_id"] != "49b09326f35936c6": return {"status":"invalid","reason":"lifecycle binding"}
        if manifest["sources"]["daily"]["index_sha256"] != sha(daily_index) or manifest["sources"]["suspend_d"]["index_sha256"] != sha(suspend_index): return {"status":"invalid","reason":"source index binding"}
        start=parse_day(manifest["scope"]["start"]); end=parse_day(manifest["scope"]["end"]); scope,common,life=_load_scope(membership_records,stock_basic_root,calendar,lifecycle,start,end)
        window_dates=[parse_day(x) for x in manifest["scope"]["window_dates"]]
        if manifest["sources"]["daily"]["inventory"] != _source_inventory(daily_root,start,end,dates=window_dates): return {"status":"invalid","reason":"daily source inventory"}
        if manifest["sources"]["suspend_d"]["inventory"] != _source_inventory(suspend_root,start,end,dates=window_dates): return {"status":"invalid","reason":"suspend source inventory"}
        if manifest["sources"]["stock_basic"]["inventory"] != _stock_basic_inventory(stock_basic_root): return {"status":"invalid","reason":"stock_basic inventory"}
        if corrective_overlay is not None:
            overlay_manifest=Path(corrective_overlay) / "manifest.json" if Path(corrective_overlay).is_dir() else Path(corrective_overlay)
            om=json.loads(overlay_manifest.read_bytes())
            bound=manifest["sources"].get("corrective_overlay",{})
            if bound.get("sha256") != sha(overlay_manifest) or bound.get("manifest_sha256") != sha(overlay_manifest) or bound.get("artifact_id") != om.get("artifact_id") or bound.get("entry_set") != om.get("authorized_faults") or bound.get("entries") != om.get("entries"):
                return {"status":"invalid","reason":"corrective overlay binding"}
            _load_overlay(corrective_overlay)
        stats={"expected_scope_count":len(scope),"complete_count":0,"unavailable_ineligible_count":0,"data_fault_count":0,"first_data_fault":None}
        cache={}
        for symbol,execution in scope:
            list_date=life[symbol][0]
            status=_check_one(symbol,execution,common,daily_root,suspend_root,list_date,cache,_load_overlay(corrective_overlay)); stats[status+"_count"]=stats.get(status+"_count",0)+1
        if stats != manifest["scope"]["stats"]: return {"status":"invalid","reason":f"scope stats mismatch: {stats}"}
        if stats["data_fault_count"] != 0: return {"status":"invalid","reason":"data_fault"}
        payload={k:v for k,v in manifest.items() if k!="artifact_id"}
        if sha_bytes(canonical(payload))[:16] != manifest["artifact_id"]: return {"status":"invalid","reason":"artifact id"}
        return {"status":"verified","artifact_id":manifest["artifact_id"]}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status":"invalid","reason":str(exc)}
