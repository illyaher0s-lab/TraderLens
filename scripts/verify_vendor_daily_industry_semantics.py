#!/usr/bin/env python3
"""Vendor daily industry semantics audit."""
import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


def main():
    start = time.time()
    vendor_dir = Path("D:/Codex/TraderLens/不复权")
    snapshot_dir = Path("data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e")
    
    # ponytail: verify hashes match manifest
    with open(snapshot_dir / "manifest.json") as f:
        manifest = json.load(f)
    
    print(f"Verifying {len(manifest['files'])} file hashes...")
    for entry in manifest["files"]:
        csv_path = vendor_dir.parent / entry["path"]
        actual = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            print(f"FAIL: Hash mismatch {entry['date']}")
            return 1
    
    # ponytail: stream industry sequences per code
    print("Building industry sequences...")
    sequences = defaultdict(list)  # code → [(date, industry)]
    
    for entry in manifest["files"]:
        csv_path = vendor_dir.parent / entry["path"]
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row["代码"]
                sequences[code].append((entry["date"], row["所属行业"]))
    
    # ponytail: detect changes
    changes = []
    flaps = []
    
    for code, seq in sequences.items():
        seq.sort()  # by date
        for i in range(1, len(seq)):
            prev_date, prev_ind = seq[i-1]
            curr_date, curr_ind = seq[i]
            if prev_ind != curr_ind:
                changes.append((code, prev_date, curr_date, prev_ind, curr_ind))
                
                # ponytail: check flap (A→B→A within 5 days)
                if i+1 < len(seq):
                    next_date, next_ind = seq[i+1]
                    if next_ind == prev_ind and int(next_date) - int(prev_date) <= 5:
                        flaps.append((code, prev_date, next_date, prev_ind, curr_ind))
    
    status = "observed_daily_snapshot_candidate" if changes else "industry_pit_semantics_unproven"
    
    result = {
        "snapshot_id": "vendor_8e64285ae2fdea2e",
        "status": status,
        "total_codes": len(sequences),
        "codes_with_changes": len(set(c[0] for c in changes)),
        "total_changes": len(changes),
        "total_flaps": len(flaps),
        "change_samples": changes[:20],
        "flap_samples": flaps[:20]
    }
    
    with open(snapshot_dir / "industry_semantics.json", "w") as f:
        json.dump(result, f, indent=2)
    
    report = f"""# Vendor Daily Industry Semantics

**Snapshot:** vendor_8e64285ae2fdea2e  
**Status:** {status}

## Results
- Codes: {len(sequences)}
- Codes with changes: {len(set(c[0] for c in changes))}
- Total changes: {len(changes)}
- Flaps: {len(flaps)}

## Change Samples
{chr(10).join(f"- {c[0]}: {c[1]}→{c[2]} ({c[3]}→{c[4]})" for c in changes[:20]) or "None"}

## Flap Samples
{chr(10).join(f"- {f[0]}: {f[1]}→{f[2]} ({f[3]}→{f[4]}→{f[3]})" for f in flaps[:20]) or "None"}
"""
    (Path("docs/verification") / "VENDOR_DAILY_INDUSTRY_SEMANTICS.md").write_text(report)
    
    elapsed = time.time() - start
    print(f"OK {status} ({elapsed:.1f}s)")
    print(f"OK Changes: {len(changes)}, Codes: {len(set(c[0] for c in changes))}, Flaps: {len(flaps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
