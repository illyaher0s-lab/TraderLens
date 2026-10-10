from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def _sha_bytes(v): return hashlib.sha256(v).hexdigest()
def _sha(p): return _sha_bytes(Path(p).read_bytes())

def publish_suspend_corrective(output_root: Path, *, faults: list[dict], rows: list[dict], original_partition_hashes: dict[str,str], response_hash: str, request: dict | None = None, fetched_at: str | None = None, authorized_faults: list[dict] | None = None) -> dict:
    authorized_faults = authorized_faults if authorized_faults is not None else faults
    allowed={(x["symbol"],x["missing_date"],x["execution_date"]) for x in authorized_faults}
    actual={(x["symbol"],x["missing_date"],x["execution_date"]) for x in faults}
    if not actual <= allowed: raise ValueError("unauthorized corrective fault")
    by_key={(r.get("ts_code"),str(r.get("trade_date")).replace("-","")[:8]):r for r in rows}
    entries=[]
    for fault in faults:
        key=(fault["symbol"],fault["missing_date"]); row=by_key.get(key)
        if row is None: raise ValueError("data_fault: source row missing")
        if row.get("daily_amount") is not None: raise ValueError("conflict: daily row and suspend row")
        if row.get("suspend_type") not in ("S","P"): raise ValueError("data_fault: source does not prove suspension")
        canonical={"ts_code":fault["symbol"],"trade_date":fault["missing_date"],"suspend_type":row["suspend_type"]}
        entries.append({"symbol":fault["symbol"],"trade_date":fault["missing_date"],"execution_date":fault["execution_date"],"source_row":canonical,"original_partition_sha256":original_partition_hashes[fault["missing_date"]],"corrected_canonical_sha256":_sha_bytes(_canon(canonical))})
    payload={"schema_version":"v3_liquidity_suspend_corrective.v1","status":"published","source":"tushare","request":request or {},"fetched_at":fetched_at or datetime.now(timezone.utc).isoformat(),"response_sha256":response_hash,"authorized_faults":sorted(allowed),"entries":sorted(entries,key=lambda x:(x["trade_date"],x["symbol"]))}
    aid=_sha_bytes(_canon(payload))[:16]; payload["artifact_id"]=aid; target=Path(output_root)/aid
    if target.exists(): raise FileExistsError(f"immutable artifact exists: {target}")
    target.mkdir(parents=True); raw=_canon(payload); (target/'manifest.json').write_bytes(raw); (target/'manifest.json.sha256').write_text(f"{_sha_bytes(raw)}  manifest.json\n",encoding='utf-8')
    return {"artifact_id":aid,"status":"published",**payload}

def verify_suspend_corrective(artifact_dir: Path, *, faults: list[dict], response_hash: str) -> dict:
    try:
        p=Path(artifact_dir)/'manifest.json'; raw=p.read_bytes(); m=json.loads(raw)
        if _sha_bytes(raw)!=(Path(artifact_dir)/'manifest.json.sha256').read_text().split()[0]: return {"status":"invalid","reason":"sidecar"}
        if m["response_sha256"]!=response_hash: return {"status":"invalid","reason":"response hash"}
        allowed={(x["symbol"],x["missing_date"],x["execution_date"]) for x in faults}
        if set(map(tuple,m["authorized_faults"])) != allowed: return {"status":"invalid","reason":"authorized faults"}
        if len(m["entries"]) != len(faults): return {"status":"invalid","reason":"entry count"}
        return {"status":"verified","artifact_id":m["artifact_id"]}
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as exc: return {"status":"invalid","reason":str(exc)}
