"""Verify V2 formal snapshot manifest and universe reference."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_universe_reference(ref_dir: Path) -> dict:
    """Verify universe reference manifest."""
    manifest_path = ref_dir / "manifest.json"
    sidecar_path = ref_dir / "manifest.json.sha256"
    
    if not manifest_path.exists():
        return {"status": "invalid", "reason": "manifest missing"}
    if not sidecar_path.exists():
        return {"status": "invalid", "reason": "sidecar missing"}
    
    manifest_hash = _sha256(manifest_path)
    sidecar_content = sidecar_path.read_text().strip()
    if manifest_hash != sidecar_content:
        return {"status": "invalid", "reason": "sidecar mismatch"}
    
    manifest = json.loads(manifest_path.read_text())
    required_fields = ["universe_reference_id", "sw2021_membership_manifest_sha256", 
                      "sw2021_universe_candidate_sha256", "universe_definition_hash",
                      "source_taxonomy", "provenance_only", 
                      "not_authorized_for_b6_oos_gate_promotion_signal"]
    for field in required_fields:
        if field not in manifest:
            return {"status": "invalid", "reason": f"missing field {field}"}
    
    if not manifest["provenance_only"]:
        return {"status": "invalid", "reason": "provenance_only must be true"}
    if not manifest["not_authorized_for_b6_oos_gate_promotion_signal"]:
        return {"status": "invalid", "reason": "not_authorized must be true"}
    
    return {"status": "valid", "universe_reference_id": manifest["universe_reference_id"]}


def verify_data_snapshot(snap_dir: Path, expected_semantic_hash: str) -> dict:
    """Verify data snapshot manifest."""
    manifest_path = snap_dir / "manifest.json"
    sidecar_path = snap_dir / "manifest.json.sha256"
    
    if not manifest_path.exists():
        return {"status": "invalid", "reason": "manifest missing"}
    if not sidecar_path.exists():
        return {"status": "invalid", "reason": "sidecar missing"}
    
    manifest_hash = _sha256(manifest_path)
    sidecar_content = sidecar_path.read_text().strip()
    if manifest_hash != sidecar_content:
        return {"status": "invalid", "reason": "sidecar mismatch"}
    
    manifest = json.loads(manifest_path.read_text())
    
    # Verify semantic_hash
    if manifest["semantic_hash"] != expected_semantic_hash:
        return {"status": "invalid", "reason": "semantic_hash mismatch"}
    
    # Verify fixed fields
    if manifest["provider"] != "mixed_vendor_tushare":
        return {"status": "invalid", "reason": "provider must be mixed_vendor_tushare"}
    if manifest["retrieval_date"] is not None:
        return {"status": "invalid", "reason": "retrieval_date must be None"}
    if manifest["retrieval_date_status"] != "unknown":
        return {"status": "invalid", "reason": "retrieval_date_status must be unknown"}
    if manifest["quality_status"] != "ok":
        return {"status": "invalid", "reason": "quality_status must be ok"}
    if manifest["gaps"] != ["availability_limited"]:
        return {"status": "invalid", "reason": "gaps must be ['availability_limited']"}
    if manifest["universe_snapshot_ids"] != []:
        return {"status": "invalid", "reason": "universe_snapshot_ids must be empty"}
    if not manifest.get("universe_reference_ids"):
        return {"status": "invalid", "reason": "universe_reference_ids missing"}
    if not manifest["not_authorized_for_b6_oos_gate_promotion_signal"]:
        return {"status": "invalid", "reason": "not_authorized must be true"}
    
    # Verify coverage_disclosure
    if "coverage_disclosure" not in manifest:
        return {"status": "invalid", "reason": "coverage_disclosure missing"}
    
    disclosure = manifest["coverage_disclosure"]
    if disclosure["expected_stock_days"] != disclosure["complete_stock_days"] + disclosure["unavailable_stock_days"]:
        return {"status": "invalid", "reason": "coverage arithmetic mismatch"}
    
    # Verify field_missing_counts sorted
    field_names = [item[0] for item in disclosure["field_missing_counts"]]
    if field_names != sorted(field_names):
        return {"status": "invalid", "reason": "field_missing_counts not sorted"}
    
    # Verify manifest_content_hash
    manifest_copy = manifest.copy()
    content_hash = manifest_copy.pop("manifest_content_hash")
    recomputed = hashlib.sha256(json.dumps(manifest_copy, sort_keys=True).encode()).hexdigest()
    if content_hash != recomputed:
        return {"status": "invalid", "reason": "manifest_content_hash mismatch"}
    
    return {"status": "valid", "snapshot_id": manifest["snapshot_id"]}


def verify_bound_publication(args: argparse.Namespace) -> dict:
    """Re-read all bound inputs; artifact-only checks are intentionally insufficient."""
    try:
        coverage_hash = _sha256(args.coverage_manifest)
        if args.coverage_sidecar.read_text(encoding="utf-8").strip() != coverage_hash:
            return {"status": "invalid", "reason": "coverage sidecar mismatch"}
        coverage = json.loads(args.coverage_manifest.read_text(encoding="utf-8"))
        predecessor_hash = _sha256(args.predecessor_manifest)
        predecessor = json.loads(args.predecessor_manifest.read_text(encoding="utf-8"))
        successor = json.loads(args.successor_manifest.read_text(encoding="utf-8"))

        if (
            coverage.get("status") != "coverage_published"
            or coverage.get("build_completion", {}).get("status") != "completed"
            or coverage.get("build_completion", {}).get("structural_validation") != "passed"
            or coverage.get("structural_errors")
            or coverage["complete_stock_days"] + coverage["unavailable_stock_days"] != coverage["expected_stock_days"]
        ):
            return {"status": "invalid", "reason": "coverage structural or arithmetic mismatch"}

        if coverage["input_manifest_content_hashes"].get("qualification_manifest.json") != predecessor_hash:
            return {"status": "invalid", "reason": "predecessor manifest binding mismatch"}
        for coverage_key, predecessor_key, successor_key in (
            ("input_scope_hash", "scope_hash", "predecessor_scope_hash"),
            ("input_template_hash", "template_hash", "predecessor_template_hash"),
            ("input_snapshot_hash", "snapshot_hash", "predecessor_snapshot_hash"),
            ("input_data_requirements_hash", "data_requirements_hash", "predecessor_data_requirements_hash"),
        ):
            if coverage[coverage_key] != predecessor[predecessor_key] or successor[successor_key] != predecessor[predecessor_key]:
                return {"status": "invalid", "reason": f"cross-binding mismatch: {coverage_key}"}
        if successor["status"] != "availability_bounded_qualified":
            return {"status": "invalid", "reason": "successor status mismatch"}
        if _sha256(args.scope_freeze) != successor["scope_freeze_sha256"]:
            return {"status": "invalid", "reason": "scope-freeze hash mismatch"}

        source_paths = {
            "sw2021_membership_manifest.json": args.sw2021_membership_manifest,
            "sw2021_universe_candidate.json": args.sw2021_universe_candidate,
            "vendor_snapshot_manifest.json": args.vendor_manifest,
            "vendor_lifecycle_candidate.json": args.vendor_lifecycle_candidate,
        }
        source_hashes = {name: _sha256(path) for name, path in source_paths.items()}
        for name, value in source_hashes.items():
            if coverage["input_manifest_content_hashes"].get(name) != value:
                return {"status": "invalid", "reason": f"source binding mismatch: {name}"}

        snapshot = json.loads((args.data_snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
        if dict(snapshot.get("source_manifest_hashes", ())) != source_hashes:
            return {"status": "invalid", "reason": "snapshot source hashes mismatch"}
        if snapshot["coverage_disclosure"]["coverage_manifest_sha256"] != coverage_hash:
            return {"status": "invalid", "reason": "snapshot coverage hash mismatch"}
        expected_disclosure = {
            "coverage_package_id": coverage["coverage_hash"],
            "coverage_manifest_sha256": coverage_hash,
            "expected_stock_days": coverage["expected_stock_days"],
            "complete_stock_days": coverage["complete_stock_days"],
            "unavailable_stock_days": coverage["unavailable_stock_days"],
            "field_missing_counts": [list(item) for item in sorted(coverage["field_missing_counts"].items())],
        }
        if snapshot["coverage_disclosure"] != expected_disclosure:
            return {"status": "invalid", "reason": "coverage disclosure mismatch"}

        reference = json.loads((args.universe_reference_dir / "manifest.json").read_text(encoding="utf-8"))
        if (
            reference["sw2021_membership_manifest_sha256"] != source_hashes["sw2021_membership_manifest.json"]
            or reference["sw2021_universe_candidate_sha256"] != source_hashes["sw2021_universe_candidate.json"]
        ):
            return {"status": "invalid", "reason": "universe reference binding mismatch"}

        import pyarrow.parquet as pq
        table = pq.read_table(args.coverage_by_date, columns=["trade_date", "expected_codes", "complete_codes", "unavailable_codes"])
        rows = table.to_pydict()
        dates = sorted(set(rows["trade_date"]))
        disclosure = snapshot["coverage_disclosure"]
        if (
            _sha256(args.coverage_by_date) != coverage["coverage_by_date_hash"]
            or len(dates) != 2554
            or dates[0] != 20160104
            or dates[-1] != 20260710
            or sum(rows["expected_codes"]) != disclosure["expected_stock_days"]
            or sum(rows["complete_codes"]) != disclosure["complete_stock_days"]
            or sum(rows["unavailable_codes"]) != disclosure["unavailable_stock_days"]
        ):
            return {"status": "invalid", "reason": "coverage-by-date aggregate mismatch"}
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": str(exc)}
    return {"status": "valid"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-reference-dir", type=Path, required=True)
    parser.add_argument("--data-snapshot-dir", type=Path, required=True)
    parser.add_argument("--predecessor-manifest", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--coverage-sidecar", type=Path, required=True)
    parser.add_argument("--coverage-by-date", type=Path, required=True)
    parser.add_argument("--successor-manifest", type=Path, required=True)
    parser.add_argument("--sw2021-membership-manifest", type=Path, required=True)
    parser.add_argument("--sw2021-universe-candidate", type=Path, required=True)
    parser.add_argument("--vendor-manifest", type=Path, required=True)
    parser.add_argument("--vendor-lifecycle-candidate", type=Path, required=True)
    parser.add_argument("--scope-freeze", type=Path, required=True)
    parser.add_argument("--expected-semantic-hash", default="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e")
    args = parser.parse_args()
    
    results = {}
    
    uref_result = verify_universe_reference(args.universe_reference_dir)
    results["universe_reference"] = uref_result
    if uref_result["status"] != "valid":
        print(json.dumps(results))
        return 1

    ds_result = verify_data_snapshot(args.data_snapshot_dir, args.expected_semantic_hash)
    results["data_snapshot"] = ds_result
    if ds_result["status"] != "valid":
        print(json.dumps(results))
        return 1

    binding_result = verify_bound_publication(args)
    results["input_bindings"] = binding_result
    if binding_result["status"] != "valid":
        print(json.dumps(results))
        return 1
    
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
