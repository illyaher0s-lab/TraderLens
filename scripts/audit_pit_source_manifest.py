"""Audit production source manifest: verify SW2021 partition hashes, enumerate SW2014 metadata."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_source_manifest(repo_root: Path):
    """Read production source manifest and verify SW2021 partition hashes.
    
    Returns audit result with:
    - sw2021_verified: list of verified partitions with hash match
    - sw2021_mismatches: list of partitions with hash conflicts
    - sw2014_metadata: list of SW2014 partitions (metadata only, zero reads)
    """
    manifest_path = repo_root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    
    sw2021_verified = []
    sw2021_mismatches = []
    sw2014_metadata = []
    
    partitions = manifest.get("partitions", [])
    if not partitions:
        raise ValueError("No partitions in manifest")
    
    for p in partitions:
        name = p["name"]
        src = p["src"]
        expected_sha256 = p["sha256"]
        row_count = p["row_count"]
        
        if src == "SW2021":
            # Verify file hash
            file_path = base_dir / name
            if not file_path.exists():
                sw2021_mismatches.append({"partition_name": name, "error": "file_not_found"})
                continue
            
            actual_hash = sha256_file(file_path)
            if actual_hash == expected_sha256:
                sw2021_verified.append({
                    "partition_name": name,
                    "source_manifest_sha256": actual_hash,
                    "source_record_count": row_count,
                })
            else:
                sw2021_mismatches.append({
                    "partition_name": name,
                    "expected_sha256": expected_sha256,
                    "actual_sha256": actual_hash,
                    "conflict": "hash_mismatch",
                })
        
        elif src == "SW2014":
            # Metadata only, no file read (zero-read commitment)
            sw2014_metadata.append({
                "partition_name": name,
                "source_record_count": row_count,
                "taxonomy_status": "out_of_scope_sw2014",
            })
    
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "sw2021_verified": sw2021_verified,
        "sw2021_mismatches": sw2021_mismatches,
        "sw2014_metadata": sw2014_metadata,
        "total_partitions": len(partitions),
    }


if __name__ == "__main__":
    repo = Path(__file__).parent.parent.resolve()
    result = audit_source_manifest(repo)
    
    print(f"[AUDIT] Production Source Manifest")
    print(f"  Manifest: {result['manifest_path']}")
    print(f"  Manifest SHA256: {result['manifest_sha256']}")
    print(f"  Total partitions: {result['total_partitions']}")
    print(f"  SW2021 verified: {len(result['sw2021_verified'])}")
    print(f"  SW2021 mismatches: {len(result['sw2021_mismatches'])}")
    print(f"  SW2014 metadata (zero-read): {len(result['sw2014_metadata'])}")
    
    if result['sw2021_mismatches']:
        print("\n[ERROR] Hash mismatches found:")
        for m in result['sw2021_mismatches']:
            print(f"  - {m}")
        sys.exit(1)
    
    expected_sw2021 = 61
    expected_sw2014 = 53
    if len(result['sw2021_verified']) != expected_sw2021:
        print(f"\n[ERROR] Expected {expected_sw2021} SW2021 partitions, got {len(result['sw2021_verified'])}")
        sys.exit(1)
    if len(result['sw2014_metadata']) != expected_sw2014:
        print(f"\n[ERROR] Expected {expected_sw2014} SW2014 partitions, got {len(result['sw2014_metadata'])}")
        sys.exit(1)
    
    print("\n[PASS] All source partition hashes verified")
    print(f"  ✓ {expected_sw2021} SW2021 partitions hash-matched")
    print(f"  ✓ {expected_sw2014} SW2014 partitions enumerated (zero parquet reads)")
