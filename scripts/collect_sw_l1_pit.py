"""SW L1 PIT membership collection - by industry batch."""
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

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


def collect_sw_l1():
    """Collect SW L1 membership by industry batch."""
    config = TushareConfig.from_env()
    config.requests_per_minute = 160
    client = TushareClient(config)
    
    out_dir = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    report = []
    request_count = 0
    partitions = []
    total_rows = 0
    truncations = []
    
    # Get L1 industries
    l1_industries = []
    for src in ["SW2014", "SW2021"]:
        df = client.pro.index_classify(level="L1", src=src)
        request_count += 1
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                l1_industries.append({
                    "src": src,
                    "l1_code": row["index_code"],
                    "l1_name": row["industry_name"]
                })
    
    report.append(f"Found {len(l1_industries)} L1 industries\n")
    
    # Collect by L1 + is_new
    for l1 in l1_industries:
        for is_new in ["Y", "N"]:
            df = client.pro.index_member_all(l1_code=l1["l1_code"], is_new=is_new)
            request_count += 1
            
            if df is None or df.empty:
                continue
            
            row_count = len(df)
            
            # Check truncation
            if row_count == 5000:
                truncations.append(f"{l1['l1_code']} is_new={is_new}")
                report.append(f"⚠️ Truncation: {l1['l1_code']} {is_new} = 5000 rows\n")
                return {
                    "status": "suspected_truncation",
                    "truncations": truncations,
                    "request_count": request_count
                }
            
            # Check required fields
            required = {"ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new"}
            missing = required - set(df.columns)
            if missing:
                report.append(f"❌ Missing fields: {missing} in {l1['l1_code']} {is_new}\n")
                return {
                    "status": "not_collected",
                    "error": f"Missing fields: {missing}",
                    "request_count": request_count
                }
            
            # Write partition
            partition_name = f"{l1['src']}_{l1['l1_code']}_is_new_{is_new}.parquet"
            partition_path = out_dir / partition_name
            df.to_parquet(partition_path, index=False)
            
            # Sidecar
            sha256 = hashlib.sha256(partition_path.read_bytes()).hexdigest()
            (partition_path.with_suffix(".parquet.sha256")).write_text(sha256)
            
            partitions.append({
                "name": partition_name,
                "l1_code": l1["l1_code"],
                "l1_name": l1["l1_name"],
                "src": l1["src"],
                "is_new": is_new,
                "row_count": row_count,
                "sha256": sha256
            })
            
            total_rows += row_count
            report.append(f"✓ {partition_name}: {row_count} rows\n")
    
    # Merge Y+N and check conflicts
    all_dfs = []
    for p in out_dir.glob("*.parquet"):
        all_dfs.append(pd.read_parquet(p))
    
    merged = pd.concat(all_dfs, ignore_index=True)
    
    # Check same date conflicts
    conflicts = []
    check_dates = ["20160104", "20200309", "20241017", "20260710"]
    coverage_check = []
    
    for check_date in check_dates:
        valid = merged[
            (merged["in_date"].astype(str) <= check_date) &
            ((merged["out_date"].isna()) | (merged["out_date"].astype(str) >= check_date))
        ]
        
        # Group by ts_code, count unique l1_code
        grouped = valid.groupby("ts_code")["l1_code"].nunique()
        multi_l1 = grouped[grouped > 1]
        
        if len(multi_l1) > 0:
            conflicts.append({
                "date": check_date,
                "stocks_with_multiple_l1": len(multi_l1),
                "samples": multi_l1.head(5).to_dict()
            })
        
        coverage_check.append({
            "date": check_date,
            "checked_stocks": len(valid["ts_code"].unique()),
            "conflicts": len(multi_l1)
        })
    
    # Check SW overlap
    sw2014_codes = set([l1["l1_code"] for l1 in l1_industries if l1["src"] == "SW2014"])
    sw2021_codes = set([l1["l1_code"] for l1 in l1_industries if l1["src"] == "SW2021"])
    overlap = sw2014_codes & sw2021_codes
    
    manifest = {
        "status": "not_collected" if conflicts else "collected_verified",
        "collected_at": datetime.now().isoformat(),
        "request_count": request_count,
        "l1_count": len(l1_industries),
        "partition_count": len(partitions),
        "total_rows": total_rows,
        "truncations": truncations,
        "conflicts": len(conflicts),
        "conflict_details": conflicts if conflicts else [],
        "sw_overlap": {
            "sw2014_l1_count": len(sw2014_codes),
            "sw2021_l1_count": len(sw2021_codes),
            "overlap_l1_codes": sorted(overlap)
        },
        "coverage_check": coverage_check,
        "partitions": partitions
    }
    
    if conflicts:
        manifest["status"] = "not_collected"
        report.append(f"\n❌ Found {len(conflicts)} date(s) with conflicts\n")
    
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    # Report
    doc = f"""# SW L1 PIT Collection

**Status:** {manifest['status']}  
**Collected:** {manifest['collected_at']}  
**Requests:** {request_count}

## Summary
- L1 industries: {len(l1_industries)}
- Partitions: {len(partitions)}
- Total rows: {total_rows:,}
- Truncations: {len(truncations)}
- Conflicts: {len(conflicts)}

## SW Taxonomy
- SW2014: {len(sw2014_codes)} L1
- SW2021: {len(sw2021_codes)} L1
- Overlap codes: {len(overlap)}

## Coverage Check
"""
    
    for c in coverage_check:
        doc += f"- {c['date']}: {c['checked_stocks']} stocks, {c['conflicts']} conflicts\n"
    
    doc += "\n" + "".join(report)
    
    (Path("docs/verification") / "SW_L1_PIT_COLLECTION.md").write_text(doc)
    
    return manifest


if __name__ == "__main__":
    result = collect_sw_l1()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["status"] == "collected_verified" else 1)
