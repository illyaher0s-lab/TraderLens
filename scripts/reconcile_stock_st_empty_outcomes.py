#!/usr/bin/env python3
"""
stock_st Empty Outcome Reconciliation - Task 3

Independently verify 172 empty stock_st partitions by re-calling Tushare API.
Produces canonical outcome manifest for independent acceptance.

Ponytail: no framework, stdlib only, single-pass reconciler.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ponytail: load env
env_file = Path(__file__).parent.parent / ".env.local"
for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
import pyarrow.parquet as pq


def reconcile_empty_dates(repo_root: Path, output_path: Path):
    """Reconcile 172 empty dates with fresh API calls."""
    
    formal = repo_root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/stock_st"
    
    # ponytail: find empty partitions
    all_dates = sorted([d.name.replace("trade_date=", "") for d in formal.iterdir() if d.is_dir()])
    empty_dates = []
    for d in all_dates:
        t = pq.read_table(formal / f"trade_date={d}/part.parquet")
        if len(t) == 0:
            empty_dates.append(d)
    
    print(f"Found {len(empty_dates)} empty partitions out of {len(all_dates)} total")
    
    # ponytail: call API for each empty date
    config = TushareConfig.from_env()
    client = TushareClient(config)
    
    outcomes = []
    for i, d in enumerate(empty_dates, 1):
        try:
            start = time.time()
            df = client.pro.stock_st(trade_date=d)
            elapsed_ms = int((time.time() - start) * 1000)
            
            # ponytail: classify outcome
            if len(df) > 0:
                print(f"ERROR: {d} now returns {len(df)} rows (was empty)")
                sys.exit(1)
            
            # ponytail: hash canonical response
            response_hash = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()
            
            outcomes.append({
                "date": d,
                "outcome": "success_empty",
                "row_count": 0,
                "response_hash": response_hash,
                "requested_at": datetime.utcnow().isoformat() + "Z",
                "elapsed_ms": elapsed_ms,
            })
            
            if i % 20 == 0:
                print(f"Progress: {i}/{len(empty_dates)}")
            
            time.sleep(0.3)  # ponytail: rate limit
            
        except Exception as e:
            print(f"ERROR reconciling {d}: {e}")
            sys.exit(1)
    
    # ponytail: save canonical outcomes
    output = {
        "schema_version": "stock_st_empty_outcomes.v1",
        "total_empty_dates": len(empty_dates),
        "reconciliation_completed_at": datetime.utcnow().isoformat() + "Z",
        "outcomes": outcomes,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, sort_keys=True)
    
    print(f"Wrote {len(outcomes)} outcomes to {output_path}")
    return output


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    output = repo_root / "data/pit/.staging/stock_st_empty_outcomes.json"
    reconcile_empty_dates(repo_root, output)
