"""Publish formal PIT membership snapshot from SW2021 source parquet.

Owner-approved implementation. Reads only SW2021 membership parquet bound by
coverage, validates structure, proves include_delisted, and publishes write-once
immutable artifact.

Does NOT:
- derive from coverage/expected universe/current constituents
- collect new data or patch holes
- modify formal data manifest
- authorize B6/OOS
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq


# Fixed constants from design
SNAPSHOT_ID_001_RETIRED = "pims_traderlens_v2_shsz_sw2021_pit_001"  # Permanently retired
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_002"  # Only prospective ID
FORMAL_DATA_SNAPSHOT_ID = "ds_traderlens_v2_shsz_pit_001"
FORMAL_DATA_SEMANTIC_HASH = "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
UNIVERSE_REFERENCE_ID = "uref_traderlens_v2_shsz_sw2021_pit_001"
UNIVERSE_RULE_TYPE = "point_in_time_membership"
MEMBERSHIP_SOURCE = "sw2021_tushare_l1_partitions"
VENDOR_SCOPE_DISCLOSURE = "sw2021_l1_only"  # Only SW2021 L1 membership partitions consumed

# Owner-approved date policy: formal validation window is 2016-01-04 onwards
DATE_POLICY_MIN = date(2016, 1, 4)

# Expected source hashes from coverage binding
EXPECTED_SW2021_MEMBERSHIP_MANIFEST_SHA256 = "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3"
EXPECTED_SW2021_CANDIDATE_SHA256 = "8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994"
EXPECTED_UNIVERSE_DEFINITION_HASH = "55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of file bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_hash(obj: dict, exclude_keys: set[str]) -> str:
    """Compute SHA-256 of canonical JSON (sorted keys, no whitespace, UTF-8)."""
    filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_source_bindings(repo_root: Path) -> dict:
    """Verify all source manifest hashes and bindings before reading parquet."""
    
    # 1. Verify formal data manifest
    formal_data_path = repo_root / "data/pit/data_snapshot_manifests" / FORMAL_DATA_SNAPSHOT_ID / "manifest.json"
    if not formal_data_path.exists():
        raise FileNotFoundError(f"Formal data manifest not found: {formal_data_path}")
    
    formal_data = json.loads(formal_data_path.read_text(encoding="utf-8"))
    if formal_data["snapshot_id"] != FORMAL_DATA_SNAPSHOT_ID:
        raise ValueError(f"Formal data snapshot_id mismatch: {formal_data['snapshot_id']}")
    if formal_data["semantic_hash"] != FORMAL_DATA_SEMANTIC_HASH:
        raise ValueError(f"Formal data semantic_hash mismatch: {formal_data['semantic_hash']}")
    if UNIVERSE_REFERENCE_ID not in formal_data.get("universe_reference_ids", []):
        raise ValueError(f"Universe reference {UNIVERSE_REFERENCE_ID} not in formal data manifest")
    
    # 2. Verify universe reference
    uref_path = repo_root / "data/pit/universe_references" / UNIVERSE_REFERENCE_ID / "manifest.json"
    if not uref_path.exists():
        raise FileNotFoundError(f"Universe reference not found: {uref_path}")
    
    uref = json.loads(uref_path.read_text(encoding="utf-8"))
    if uref["universe_reference_id"] != UNIVERSE_REFERENCE_ID:
        raise ValueError(f"Universe reference ID mismatch: {uref['universe_reference_id']}")
    if uref.get("provenance_only") is not True:
        raise ValueError("Universe reference must be provenance_only")
    if uref["universe_definition_hash"] != EXPECTED_UNIVERSE_DEFINITION_HASH:
        raise ValueError(f"Universe definition hash mismatch: {uref['universe_definition_hash']}")
    
    # 3. Verify SW2021 membership manifest
    sw2021_manifest_path = repo_root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json"
    if not sw2021_manifest_path.exists():
        raise FileNotFoundError(f"SW2021 membership manifest not found: {sw2021_manifest_path}")
    
    actual_membership_hash = sha256_file(sw2021_manifest_path)
    if actual_membership_hash != EXPECTED_SW2021_MEMBERSHIP_MANIFEST_SHA256:
        raise ValueError(f"SW2021 membership manifest hash mismatch: {actual_membership_hash}")
    
    membership_manifest = json.loads(sw2021_manifest_path.read_text(encoding="utf-8"))
    if membership_manifest["status"] != "collected_verified":
        raise ValueError(f"SW2021 membership status invalid: {membership_manifest['status']}")
    
    # 4. Verify SW2021 candidate
    sw2021_candidate_path = sw2021_manifest_path.parent / "sw2021_universe_candidate.json"
    if not sw2021_candidate_path.exists():
        raise FileNotFoundError(f"SW2021 candidate not found: {sw2021_candidate_path}")
    
    actual_candidate_hash = sha256_file(sw2021_candidate_path)
    if actual_candidate_hash != EXPECTED_SW2021_CANDIDATE_SHA256:
        raise ValueError(f"SW2021 candidate hash mismatch: {actual_candidate_hash}")
    
    candidate = json.loads(sw2021_candidate_path.read_text(encoding="utf-8"))
    if candidate["status"] != "candidate_universe_ready":
        raise ValueError(f"SW2021 candidate status invalid: {candidate['status']}")
    if candidate["universe_definition_hash"] != EXPECTED_UNIVERSE_DEFINITION_HASH:
        raise ValueError(f"Candidate universe definition hash mismatch: {candidate['universe_definition_hash']}")
    
    return {
        "membership_manifest": membership_manifest,
        "candidate": candidate,
        "sw2021_manifest_path": sw2021_manifest_path,
    }


def load_and_validate_records(
    sw2021_manifest_path: Path,
    membership_manifest: dict,
    snapshot_date: date,
) -> tuple[list[dict], dict]:
    """Load membership records from source parquet and validate structure.
    
    Returns:
        (records, validation_result)
    """
    
    partitions = membership_manifest.get("partitions", [])
    if not partitions:
        raise ValueError("No partitions in membership manifest")
    
    all_records = []
    seen_identities = {}  # (symbol, effective_from, effective_to, l1_code) -> [source_provenance_list]
    errors = []
    
    source_dir = sw2021_manifest_path.parent
    
    for partition_meta in partitions:
        parquet_filename = partition_meta["name"]
        src_version = partition_meta["src"]
        
        # CORRECTIVE: Reject SW2014, only accept SW2021
        if src_version != "SW2021":
            # This is expected filtering, not an error - skip silently
            continue
        
        parquet_path = source_dir / parquet_filename
        
        if not parquet_path.exists():
            errors.append(f"Missing parquet: {parquet_filename}")
            continue
        
        # Read parquet
        table = pq.read_table(parquet_path)
        df = table.to_pandas()
        
        for _, row in df.iterrows():
            symbol = row["ts_code"]
            in_date_str = row["in_date"]
            out_date_str = row.get("out_date")
            l1_index_code = row["l1_code"]
            is_new = row["is_new"]
            
            # Parse dates
            effective_from = datetime.strptime(str(int(in_date_str)), "%Y%m%d").date()
            
            # Handle out_date which might be None, NaN, or numeric
            effective_to = None
            if out_date_str is not None:
                # Check for pandas NaN or similar
                import math
                if not (isinstance(out_date_str, float) and math.isnan(out_date_str)):
                    effective_to = datetime.strptime(str(int(out_date_str)), "%Y%m%d").date()
            
            # Validate interval
            if effective_to is not None and effective_to < effective_from:
                errors.append(f"{symbol}: effective_to < effective_from ({effective_to} < {effective_from})")
                continue
            
            # Apply date policy: only consume records from DATE_POLICY_MIN onwards
            if effective_from < DATE_POLICY_MIN:
                # Skip records before 2016-01-04 (outside formal validation window)
                continue
            
            # Validate horizon
            if effective_from > snapshot_date:
                errors.append(f"{symbol}: effective_from > snapshot_date ({effective_from} > {snapshot_date})")
                continue
            
            if effective_to is not None and effective_to > snapshot_date:
                errors.append(f"{symbol}: effective_to > snapshot_date ({effective_to} > {snapshot_date})")
                continue
            
            # Canonical identity (membership state, not partition metadata)
            identity = (symbol, effective_from, effective_to, l1_index_code)
            source_provenance = f"{src_version}_{l1_index_code}_is_new_{is_new}"
            
            # Merge identical membership states from different source versions
            if identity in seen_identities:
                seen_identities[identity].append(source_provenance)
                continue
            
            seen_identities[identity] = [source_provenance]
            
            record = {
                "symbol": symbol,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "source": source_provenance,  # Will be updated after dedup
                "snapshot_id": SNAPSHOT_ID,
            }
            all_records.append(record)
    
    # Update source field with merged provenance
    for rec in all_records:
        identity = (rec["symbol"], rec["effective_from"], rec["effective_to"], rec["source"].split("_")[1])
        provenances = seen_identities.get(identity)
        if provenances and len(provenances) > 1:
            rec["source"] = ";".join(sorted(set(provenances)))
    
    # Check for overlapping intervals per symbol (closed interval semantics)
    symbol_intervals = {}
    for rec in all_records:
        sym = rec["symbol"]
        if sym not in symbol_intervals:
            symbol_intervals[sym] = []
        symbol_intervals[sym].append(rec)
    
    for sym, intervals in symbol_intervals.items():
        sorted_intervals = sorted(intervals, key=lambda r: (r["effective_from"], r["effective_to"] or date.max))
        
        for i in range(len(sorted_intervals) - 1):
            curr = sorted_intervals[i]
            next_rec = sorted_intervals[i + 1]
            
            curr_end = curr["effective_to"] if curr["effective_to"] is not None else snapshot_date
            next_start = next_rec["effective_from"]
            
            # Closed interval: overlap if curr_end >= next_start
            if curr_end >= next_start:
                errors.append(
                    f"{sym}: overlapping intervals [{curr['effective_from']}, {curr['effective_to']}] "
                    f"and [{next_rec['effective_from']}, {next_rec['effective_to']}]"
                )
    
    validation = {
        "total_records": len(all_records),
        "unique_symbols": len(symbol_intervals),
        "errors": errors,
        "has_delisted": any(r["effective_to"] is not None for r in all_records),
    }
    
    return all_records, validation


def prove_include_delisted(records: list[dict], validation: dict) -> tuple[bool, str]:
    """Prove include_delisted from source records.
    
    Returns:
        (proved, reason)
    """
    if not validation["has_delisted"]:
        return False, "No delisted records found (all effective_to=None)"
    
    # Additional check: ensure we have both listed and delisted
    delisted_count = sum(1 for r in records if r["effective_to"] is not None)
    active_count = sum(1 for r in records if r["effective_to"] is None)
    
    if delisted_count == 0:
        return False, "Zero delisted records"
    
    if active_count == 0:
        return False, "Zero active records (suspicious)"
    
    return True, f"Proved: {delisted_count} delisted + {active_count} active records"


def write_records_parquet(records: list[dict], output_path: Path):
    """Write records to parquet with correct schema."""
    import pyarrow as pa
    
    # Convert to pyarrow table
    symbols = [r["symbol"] for r in records]
    effective_froms = [r["effective_from"] for r in records]
    effective_tos = [r["effective_to"] for r in records]
    sources = [r["source"] for r in records]
    snapshot_ids = [r["snapshot_id"] for r in records]
    
    table = pa.table({
        "symbol": symbols,
        "effective_from": effective_froms,
        "effective_to": effective_tos,
        "source": sources,
        "snapshot_id": snapshot_ids,
    })
    
    pq.write_table(table, output_path)


def publish_snapshot(repo_root: Path, snapshot_date: date) -> dict:
    """Publish formal PIT membership snapshot.
    
    Returns:
        result dict with status, paths, hashes
    """
    
    # Step 1: Verify bindings
    print("Step 1: Verifying source bindings...")
    bindings = verify_source_bindings(repo_root)
    print("✓ Source bindings verified")
    
    # Step 2: Check if trying to republish retired _001
    if SNAPSHOT_ID == SNAPSHOT_ID_001_RETIRED:
        retired_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_001_RETIRED
        if retired_dir.exists():
            print(f"✗ Cannot republish retired snapshot {SNAPSHOT_ID_001_RETIRED}")
            return {
                "status": "retired_snapshot_rejected",
                "snapshot_id": SNAPSHOT_ID_001_RETIRED,
                "message": f"{SNAPSHOT_ID_001_RETIRED} is permanently retired audit evidence and must not be republished",
            }
    
    # Step 3: Check if _002 already published
    output_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID
    if output_dir.exists():
        print(f"⚠ Snapshot {SNAPSHOT_ID} already exists, checking if already_published...")
        # TODO: Recompute all input hashes and verify unchanged
        # For now, return already_published
        return {
            "status": "already_published",
            "snapshot_id": SNAPSHOT_ID,
            "message": f"{SNAPSHOT_ID} already published (recomputation not yet implemented)",
        }
    
    # Step 4: Load and validate records
    print("Step 2: Loading and validating records...")
    records, validation = load_and_validate_records(
        bindings["sw2021_manifest_path"],
        bindings["membership_manifest"],
        snapshot_date,
    )
    
    if validation["errors"]:
        print(f"✗ Validation failed with {len(validation['errors'])} errors:")
        for err in validation["errors"][:10]:
            print(f"  - {err}")
        if len(validation["errors"]) > 10:
            print(f"  ... and {len(validation['errors']) - 10} more")
        raise ValueError(f"Structural validation failed: {len(validation['errors'])} errors")
    
    print(f"✓ Loaded {validation['total_records']} records, {validation['unique_symbols']} symbols")
    
    # Step 4: Prove include_delisted
    print("Step 3: Proving include_delisted...")
    proved, reason = prove_include_delisted(records, validation)
    if not proved:
        raise ValueError(f"Cannot prove include_delisted=true: {reason}")
    print(f"✓ {reason}")
    
    # Step 5: Compute date range
    all_dates = []
    for r in records:
        all_dates.append(r["effective_from"])
        if r["effective_to"] is not None:
            all_dates.append(r["effective_to"])
    
    min_date = min(all_dates)
    max_date = max(all_dates)
    
    # Step 6: Create temporary staging directory
    print("Step 4: Creating temporary staging directory...")
    staging_dir = repo_root / "data/pit/pit_membership_snapshots" / f".tmp_{SNAPSHOT_ID}"
    if staging_dir.exists():
        import shutil
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 7: Write records parquet to staging
        print("Step 5: Writing records parquet to staging...")
        records_path = staging_dir / "records.parquet"
        write_records_parquet(records, records_path)
        records_hash = sha256_file(records_path)
        print(f"✓ Records written: {records_hash}")
        
        # Step 8: Build manifest
        print("Step 6: Building manifest...")
        manifest = {
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_date": snapshot_date.isoformat(),
            "universe_rule_type": UNIVERSE_RULE_TYPE,
            "membership_source": MEMBERSHIP_SOURCE,
            "vendor_scope_disclosure": VENDOR_SCOPE_DISCLOSURE,
            "date_policy_min": DATE_POLICY_MIN.isoformat(),
            "include_delisted": True,
            "frozen": True,
            "quality_status": "ok",
            "gaps": ["availability_limited"],
            "record_count": validation["total_records"],
            "unique_symbols": validation["unique_symbols"],
            "date_range_min": min_date.isoformat(),
            "date_range_max": max_date.isoformat(),
            "formal_data_snapshot_id": FORMAL_DATA_SNAPSHOT_ID,
            "formal_data_semantic_hash": FORMAL_DATA_SEMANTIC_HASH,
            "universe_reference_id": UNIVERSE_REFERENCE_ID,
            "sw2021_membership_manifest_sha256": EXPECTED_SW2021_MEMBERSHIP_MANIFEST_SHA256,
            "sw2021_candidate_sha256": EXPECTED_SW2021_CANDIDATE_SHA256,
            "universe_definition_hash": EXPECTED_UNIVERSE_DEFINITION_HASH,
            "records_parquet_sha256": records_hash,
            "schema_version": "v1",
            "interval_semantics": "closed_inclusive",
            "manifest_published_at": datetime.now().isoformat(),
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
        }
        
        # Step 9: Compute canonical content hash
        exclude_keys = {"canonical_content_hash", "manifest_published_at"}
        canonical_hash = canonical_json_hash(manifest, exclude_keys)
        manifest["canonical_content_hash"] = canonical_hash
        
        # Step 10: Write manifest to staging
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_raw_hash = sha256_file(manifest_path)
        print(f"✓ Manifest written: {manifest_raw_hash}")
        
        # Step 11: Write sidecars to staging
        (staging_dir / "manifest.json.sha256").write_text(f"{manifest_raw_hash}  manifest.json\n", encoding="utf-8")
        (staging_dir / "records.parquet.sha256").write_text(f"{records_hash}  records.parquet\n", encoding="utf-8")
        print("✓ Sidecars written")
        
        # Step 12: Atomic rename from staging to final
        print("Step 7: Atomic rename to final location...")
        final_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID
        if final_dir.exists():
            # Race condition: another process published while we were building
            import shutil
            shutil.rmtree(staging_dir)
            return {
                "status": "already_published",
                "snapshot_id": SNAPSHOT_ID,
                "message": f"{SNAPSHOT_ID} was published by another process during staging",
            }
        
        staging_dir.rename(final_dir)
        print(f"✓ Atomic rename complete: {final_dir}")
        
        return {
            "status": "published",
            "output_dir": str(final_dir),
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_date": snapshot_date.isoformat(),
            "record_count": validation["total_records"],
            "unique_symbols": validation["unique_symbols"],
            "include_delisted": True,
            "canonical_content_hash": canonical_hash,
            "manifest_raw_hash": manifest_raw_hash,
            "records_hash": records_hash,
        }
    
    except Exception as e:
        # Clean up staging on any error
        import shutil
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise


def main():
    repo_root = Path(__file__).parent.parent
    snapshot_date = date.today()
    
    print(f"Publishing PIT membership snapshot: {SNAPSHOT_ID}")
    print(f"Snapshot date: {snapshot_date}")
    print()
    
    result = publish_snapshot(repo_root, snapshot_date)
    
    print()
    print("=" * 60)
    print("Publication complete")
    print(f"Status: {result['status']}")
    
    if result["status"] == "retired_snapshot_exists":
        print(f"✗ {result['message']}")
        return 3  # Distinct exit code for retired blocking
    
    if result["status"] == "source_contract_blockers":
        print(f"✗ {result['message']}")
        print("\nBlockers:")
        for blocker in result["blockers"]:
            print(f"  - {blocker}")
        print("\nSee: docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md")
        return 4  # Distinct exit code for source contract blockers
    
    if result.get("output_dir"):
        print(f"Output: {result['output_dir']}")
    if result["status"] == "published":
        print(f"Records: {result['record_count']}")
        print(f"Symbols: {result['unique_symbols']}")
        print(f"Include delisted: {result['include_delisted']}")
        print(f"Canonical content hash: {result['canonical_content_hash']}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
