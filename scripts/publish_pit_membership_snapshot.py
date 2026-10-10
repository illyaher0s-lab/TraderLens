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
SNAPSHOT_ID_002_INVALID = "pims_traderlens_v2_shsz_sw2021_pit_002"  # Invalid: applied date filtering
SNAPSHOT_ID_003_INVALID = "pims_traderlens_v2_shsz_sw2021_pit_003"  # Invalid: missing source_partition_audit
SNAPSHOT_ID_004_INVALID = "pims_traderlens_v2_shsz_sw2021_pit_004"  # Invalid: null source_manifest_sha256
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"  # Current prospective ID
FORMAL_DATA_SNAPSHOT_ID = "ds_traderlens_v2_shsz_pit_001"
FORMAL_DATA_SEMANTIC_HASH = "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
UNIVERSE_REFERENCE_ID = "uref_traderlens_v2_shsz_sw2021_pit_001"
UNIVERSE_RULE_TYPE = "point_in_time_membership"
MEMBERSHIP_SOURCE = "sw2021_tushare_l1_partitions"

# Owner-approved structured disclosure (Task 3)
VENDOR_SCOPE_DISCLOSURE = {
    "historical_membership_scope": "vendor_provided_unverified",
    "disclosure_text": (
        "This snapshot preserves all membership records from bound source partitions "
        "(Tushare index_member_all SW2021). TraderLens does not independently verify "
        "that the vendor's historical membership data constitutes a complete registry "
        "of all market-wide delisted securities. Vendor coverage boundaries, if any, "
        "are not contractually documented."
    ),
}

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
    snapshot_id: str,
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
    taxonomy_out_of_scope = []  # SW2014 partitions explicitly enumerated but not read
    source_partition_audit = []  # Track source partition -> published record mapping
    
    source_dir = sw2021_manifest_path.parent
    
    for partition_meta in partitions:
        parquet_filename = partition_meta["name"]

        declared_src = partition_meta.get("src")
        if parquet_filename.startswith("SW2021_"):
            filename_src = "SW2021"
        elif parquet_filename.startswith("SW2014_"):
            filename_src = "SW2014"
        else:
            errors.append(f"Unknown taxonomy prefix in {parquet_filename}")
            continue

        if declared_src not in {"SW2021", "SW2014"}:
            errors.append(f"Unknown taxonomy src {declared_src!r} in {parquet_filename}")
            continue
        if declared_src != filename_src:
            errors.append(
                f"Taxonomy mismatch in {parquet_filename}: src={declared_src}, "
                f"filename_prefix={filename_src}"
            )
            continue

        src_version = declared_src
        source_manifest_sha256 = partition_meta["sha256"]  # Manifest declares this
        source_record_count = partition_meta["row_count"]  # Manifest declares this
        
        # Independently compute file hash and row count for SW2021
        source_file_sha256 = None
        source_file_row_count = None
        
        if src_version == "SW2021":
            parquet_path = source_dir / parquet_filename
            if parquet_path.exists():
                source_file_sha256 = sha256_file(parquet_path)
                try:
                    table = pq.read_table(parquet_path)
                    source_file_row_count = len(table)
                except Exception as e:
                    errors.append(f"Failed to read {parquet_filename}: {e}")
                    continue
        
        # Task 3: SW2014 taxonomy out of scope (enumerated, zero reads)
        if src_version == "SW2014":
            taxonomy_out_of_scope.append({
                "name": parquet_filename,
                "src": src_version,
                "hash": partition_meta.get("hash"),
                "row_count": partition_meta.get("row_count"),
            })
            source_partition_audit.append({
                "partition_name": parquet_filename,
                "source_manifest_sha256": source_manifest_sha256,
                "source_file_sha256": None,  # SW2014 not read
                "source_record_count": source_record_count,
                "source_file_row_count": None,  # SW2014 not read
                "published_record_count": 0,
                "taxonomy_status": "out_of_scope_sw2014",
            })
            continue
        
        # Only SW2021 accepted
        if src_version != "SW2021":
            errors.append(f"Unknown taxonomy: {src_version} in {parquet_filename}")
            continue
        
        parquet_path = source_dir / parquet_filename
        
        if not parquet_path.exists():
            errors.append(f"Missing parquet: {parquet_filename}")
            continue
        
        # Read parquet
        table = pq.read_table(parquet_path)
        df = table.to_pandas()
        
        records_before = len(all_records)
        
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
            
            # Task 3: No date filtering - preserve all source records
            # Validation window is consumption boundary, not publication filter
            
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
            
            # Duplicate detection: fail loud, no silent merge
            if identity in seen_identities:
                prev_provenance = seen_identities[identity]
                errors.append(
                    f"Duplicate identity {symbol} [{effective_from}, {effective_to}] {l1_index_code}: "
                    f"seen in {prev_provenance}, now in {source_provenance}"
                )
                continue
            
            seen_identities[identity] = source_provenance
            
            record = {
                "symbol": symbol,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "source": source_provenance,  # Will be updated after dedup
                "snapshot_id": snapshot_id,
            }
            all_records.append(record)
        
        # Record audit trail for this partition
        records_after = len(all_records)
        published_count = records_after - records_before
        
        # Compute canonical_record_identity_hash for this partition
        partition_records = all_records[records_before:records_after]
        canonical_identities = []
        for rec in partition_records:
            # Canonical identity: (symbol, effective_from, effective_to, l1_code)
            # Extract l1_code from source provenance (format: "SW2021_{l1_code}_is_new_{Y/N}")
            l1_code = rec["source"].split("_")[1]  # SW2021_801010.SI_is_new_Y -> 801010.SI
            identity_tuple = (
                rec["symbol"],
                rec["effective_from"].isoformat(),
                rec["effective_to"].isoformat() if rec["effective_to"] else None,
                l1_code,
            )
            canonical_identities.append(identity_tuple)
        
        # Sort for determinism and compute hash
        canonical_identities_sorted = sorted(canonical_identities)
        canonical_payload = json.dumps(canonical_identities_sorted, separators=(",", ":"))
        canonical_hash = hashlib.sha256(canonical_payload.encode()).hexdigest()
        
        source_partition_audit.append({
            "partition_name": parquet_filename,
            "source_manifest_sha256": source_manifest_sha256,
            "source_file_sha256": source_file_sha256,
            "source_record_count": source_record_count,
            "source_file_row_count": source_file_row_count,
            "published_record_count": published_count,
            "taxonomy_status": "sw2021_accepted",
            "canonical_record_identity_hash": canonical_hash,
        })
    
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
        "taxonomy_out_of_scope": taxonomy_out_of_scope,
        "source_partition_audit": source_partition_audit,
    }
    
    return all_records, validation


def prove_include_delisted(records: list[dict], validation: dict) -> tuple[bool, str]:
    """Prove include_delisted from source-record retention.
    
    include_delisted=true means: snapshot preserves all source records,
    regardless of whether any have effective_to (delisted status).
    
    Returns:
        (proved, reason)
    """
    # Proof: all source records are retained (no filtering applied)
    # This is already validated by load_and_validate_records()
    # which enforces structural integrity and applies no date/status filtering
    
    delisted_count = sum(1 for r in records if r["effective_to"] is not None)
    active_count = sum(1 for r in records if r["effective_to"] is None)
    
    return True, f"Source-record retention proved: {validation['total_records']} records ({delisted_count} delisted, {active_count} active)"


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


def publish_snapshot(
    repo_root: Path,
    snapshot_date: date | str,  # ponytail: accept str for test convenience
    _test_snapshot_id: str | None = None,
    _test_output_root: Path | None = None,
    _test_source_manifest: Path | None = None,
) -> dict:
    """Publish formal PIT membership snapshot."""

    # ponytail: parse string date
    if isinstance(snapshot_date, str):
        snapshot_date = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
    
    # ponytail: test overrides skip production bindings
    snapshot_id = _test_snapshot_id or SNAPSHOT_ID
    output_base = _test_output_root or (repo_root / "data/pit/pit_membership_snapshots")
    
    # Step 1: Verify bindings (skip if test manifest provided)
    if _test_source_manifest:
        sw2021_membership_manifest_path = _test_source_manifest
    else:
        print("Step 1: Verifying source bindings...")
        bindings = verify_source_bindings(repo_root)
        print("[PASS] Source bindings verified")
        sw2021_membership_manifest_path = bindings["sw2021_manifest_path"]
    
    # Step 2: Check if trying to republish retired _001 or invalid _002
    if snapshot_id == SNAPSHOT_ID_001_RETIRED:
        retired_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_001_RETIRED
        if retired_dir.exists():
            print(f"[REJECTED] Cannot republish retired snapshot {SNAPSHOT_ID_001_RETIRED}")
            return {
                "status": "retired_snapshot_rejected",
                "snapshot_id": SNAPSHOT_ID_001_RETIRED,
                "message": f"{SNAPSHOT_ID_001_RETIRED} is permanently retired audit evidence and must not be republished",
            }
    # Check for invalid _002/_003 publication attempt
    if snapshot_id == SNAPSHOT_ID_002_INVALID:
        invalid_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_002_INVALID
        if invalid_dir.exists():
            print(f"[REJECTED] Cannot republish invalid snapshot {SNAPSHOT_ID_002_INVALID}")
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": SNAPSHOT_ID_002_INVALID,
                "message": f"{SNAPSHOT_ID_002_INVALID} is unaccepted (applied date filtering to source records)",
                "reason": "Applied DATE_POLICY_MIN filter during publication",
            }
    
    if snapshot_id == SNAPSHOT_ID_003_INVALID:
        invalid_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_003_INVALID
        if invalid_dir.exists():
            print(f"[REJECTED] Cannot republish invalid snapshot {SNAPSHOT_ID_003_INVALID}")
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": SNAPSHOT_ID_003_INVALID,
                "message": f"{SNAPSHOT_ID_003_INVALID} is unaccepted (missing source_partition_audit)",
                "reason": "Lacks source-to-record provenance binding and partition audit trail",
            }
    
    if snapshot_id == SNAPSHOT_ID_004_INVALID:
        invalid_dir = repo_root / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_004_INVALID
        if invalid_dir.exists():
            print(f"[REJECTED] Cannot republish invalid snapshot {SNAPSHOT_ID_004_INVALID}")
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": SNAPSHOT_ID_004_INVALID,
                "message": f"{SNAPSHOT_ID_004_INVALID} is unaccepted (null source_manifest_sha256 due to historical bug)",
                "reason": "Used .get('hash') instead of ['sha256'], resulting in null source binding",
            }
    # Step 3: Check if already published
    output_dir = output_base / snapshot_id
    if output_dir.exists():
        print(f"[INFO] Snapshot {snapshot_id} already exists, verifying input hashes...")
        
        # Read existing manifest
        existing_manifest_path = output_dir / "manifest.json"
        if not existing_manifest_path.exists():
            raise ValueError(f"Published snapshot exists but manifest missing: {existing_manifest_path}")
        
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        existing_audit = existing_manifest.get("source_partition_audit", [])
        
        # Read current source manifest
        current_manifest = json.loads(sw2021_membership_manifest_path.read_text(encoding="utf-8"))
        current_partitions = {p["name"]: p for p in current_manifest.get("partitions", [])}
        
        # Compare source hashes
        hash_matches = True
        mismatches = []
        
        for audit_entry in existing_audit:
            partition_name = audit_entry["partition_name"]
            existing_sha = audit_entry.get("source_manifest_sha256")

            # Legacy _004 has null sha256 due to historical bug (used .get("hash") instead of ["sha256"])
            # Treat null as unmatchable to force content_conflict and prevent silent republication
            if existing_sha is None:
                hash_matches = False
                mismatches.append(f"{partition_name}: existing sha256 is null (legacy bug)")
                continue
            
            if partition_name not in current_partitions:
                hash_matches = False
                mismatches.append(f"{partition_name}: missing in current source")
                continue
            
            current_sha = current_partitions[partition_name]["sha256"]
            if current_sha != existing_sha:
                hash_matches = False
                mismatches.append(f"{partition_name}: hash changed ({existing_sha[:8]} -> {current_sha[:8]})")
        
        if hash_matches:
            # Verify artifact integrity before returning already_published
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent))
            from verify_pit_membership_snapshot import verify_snapshot
            
            verify_result = verify_snapshot(repo_root, snapshot_id, snapshots_root=output_base)
            if verify_result["status"] != "verified":
                print(f"[REJECTED] Artifact integrity check failed: {verify_result['status']}")
                errors = verify_result.get("errors", [])
                if errors:
                    for err in errors[:3]:  # Show first 3 errors
                        print(f"  - {err}")
                return {
                    "status": "content_conflict",
                    "snapshot_id": snapshot_id,
                    "message": f"{snapshot_id} exists but artifact is corrupted or tampered",
                    "verification_error": verify_result,
                }
            
            print(f"[PASS] All source hashes match and artifact verified, {snapshot_id} already published")
            return {
                "status": "already_published",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} already published with identical source hashes",
            }
        else:
            print("[REJECTED] Source content conflict detected:")
            for m in mismatches:
                print(f"  - {m}")
            return {
                "status": "content_conflict",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} exists but source content has changed",
                "conflicts": mismatches,
            }
    
    # Step 4: Load and validate records
    print("Step 2: Loading and validating records...")
    membership_manifest = json.loads(sw2021_membership_manifest_path.read_text(encoding="utf-8"))
    records, validation = load_and_validate_records(
        sw2021_membership_manifest_path,
        membership_manifest,
        snapshot_date,
        snapshot_id,
    )
    
    if validation["errors"]:
        print(f"[REJECTED] Validation failed with {len(validation['errors'])} errors:")
        for err in validation["errors"][:10]:
            print(f"  - {err}")
        if len(validation["errors"]) > 10:
            print(f"  ... and {len(validation['errors']) - 10} more")
        return {
            "status": "validation_failed",
            "message": f"Structural validation failed: {len(validation['errors'])} errors",
            "errors": validation["errors"],
        }
    
    print(f"[PASS] Loaded {validation['total_records']} records, {validation['unique_symbols']} symbols")
    
    # Step 4: Prove include_delisted
    print("Step 3: Proving include_delisted...")
    proved, reason = prove_include_delisted(records, validation)
    if not proved:
        raise ValueError(f"Cannot prove include_delisted=true: {reason}")
    print(f"[PASS] {reason}")
    
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
    staging_dir = output_base / f".tmp_{snapshot_id}"
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
        print(f"[PASS] Records written: {records_hash}")
        
        # Step 8: Build manifest
        print("Step 6: Building manifest...")
        manifest = {
            "snapshot_id": snapshot_id,
            "snapshot_date": snapshot_date.isoformat(),
            "universe_rule_type": UNIVERSE_RULE_TYPE,
            "membership_source": MEMBERSHIP_SOURCE,
            "source_contract": "tushare_sw_l1_member_v2",
            "vendor_scope_disclosure": VENDOR_SCOPE_DISCLOSURE,
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
            "taxonomy_out_of_scope_count": len(validation["taxonomy_out_of_scope"]),
            "source_partition_audit": validation["source_partition_audit"],
            "source_to_record_mapping_hash": hashlib.sha256(
                json.dumps(validation["source_partition_audit"], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
        
        # Step 9: Compute canonical content hash
        exclude_keys = {"canonical_content_hash", "manifest_published_at"}
        canonical_hash = canonical_json_hash(manifest, exclude_keys)
        manifest["canonical_content_hash"] = canonical_hash
        
        # Step 10: Write manifest to staging
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_raw_hash = sha256_file(manifest_path)
        print(f"[PASS] Manifest written: {manifest_raw_hash}")
        
        # Step 11: Write sidecars to staging
        (staging_dir / "manifest.json.sha256").write_text(f"{manifest_raw_hash}  manifest.json\n", encoding="utf-8")
        (staging_dir / "records.parquet.sha256").write_text(f"{records_hash}  records.parquet\n", encoding="utf-8")
        print("[PASS] Sidecars written")
        
        # Step 11: Atomic move to final location
        print("Step 8: Atomic move to final location...")
        final_dir = output_base / snapshot_id
        if final_dir.exists():
            # Race condition: another process published while we were staging
            import shutil
            shutil.rmtree(staging_dir)
            return {
                "status": "already_published",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} was published by another process during staging",
            }
        staging_dir.rename(final_dir)
        
        print(f"[PASS] Published {snapshot_id}")
        return {
            "status": "published",
            "snapshot_id": snapshot_id,
            "output_dir": str(final_dir),
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

    status = result["status"]
    print()
    print("=" * 60)
    print(f"Status: {status}")

    if status in {"published", "already_published"}:
        print("[PASS] Publication complete")
        if result.get("output_dir"):
            print(f"Output: {result['output_dir']}")
    if status == "published":
        print(f"Records: {result['record_count']}")
        print(f"Symbols: {result['unique_symbols']}")
        print(f"Include delisted: {result['include_delisted']}")
        print(f"Canonical content hash: {result['canonical_content_hash']}")
        print("=" * 60)
        return 0
    if status == "already_published":
        print("=" * 60)
        return 0

    print(f"[REJECTED] {result.get('message', status)}")
    print("=" * 60)
    return 3


if __name__ == "__main__":
    sys.exit(main())
