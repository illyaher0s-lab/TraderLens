"""Independently verify the exact v3 availability-bounded successor."""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path

from scripts.build_v3_availability_bounded_qualification_successor import _bound_inputs, _canonical, _sha
from scripts.publish_v3_formal_snapshot import COVERAGE_DIR, EVIDENCE_DIR, SCOPE_DIR, TEMPLATE


def _invalid(reason: str) -> dict:
    return {"status": "invalid", "reason": reason}


def verify_successor(
    successor_dir: Path,
    *,
    formal_snapshot_dir: Path,
    coverage_dir: Path = COVERAGE_DIR,
    scope_dir: Path = SCOPE_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
) -> dict:
    try:
        manifest_path = Path(successor_dir) / "manifest.json"
        sidecar = Path(successor_dir) / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar.exists():
            return _invalid("successor manifest or sidecar missing")
        if sidecar.read_text(encoding="utf-8").split()[0] != _sha(manifest_path):
            return _invalid("successor sidecar mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("successor_schema_version") != "v3_availability_bounded_qualification_successor.v1":
            return _invalid("v3 successor schema mismatch")
        if manifest.get("status") != "availability_bounded_qualified":
            return _invalid("successor status mismatch")
        if manifest.get("authorization_scope") != "b6_coverage_bound" or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection") is not False:
            return _invalid("successor authorization mismatch")
        inputs = _bound_inputs(Path(formal_snapshot_dir), Path(coverage_dir), Path(scope_dir), Path(evidence_dir))
        coverage = inputs["coverage"]
        expected = {
            "successor_schema_version": manifest["successor_schema_version"],
            "status": manifest["status"],
            "authorization_scope": manifest["authorization_scope"],
            "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": False,
            "template": TEMPLATE,
            "scope": {"artifact_id": coverage["scope_freeze"]["artifact_id"], "manifest_sha256": inputs["scope_hash"]},
            "formal_snapshot": {"snapshot_id": inputs["snapshot"]["snapshot_id"], "semantic_hash": inputs["snapshot"]["semantic_hash"], "manifest_sha256": inputs["snapshot_hash"]},
            "coverage": {"artifact_id": coverage["artifact_id"], "manifest_sha256": inputs["coverage_hash"], "files": coverage["files"], "stats": coverage["coverage"], "algorithm_hash": coverage["liquidity_algorithm"]["algorithm_hash"]},
            "source_adapter": coverage["source_adapter"],
            "suspension_evidence": {"artifact_id": inputs["evidence"]["artifact_id"], "manifest_sha256": inputs["evidence_hash"]},
            "lineage": {"b3": {"artifact_id": inputs["b3"]["artifact_id"], "manifest_sha256": inputs["b3_hash"], "authorization_scope": inputs["b3"]["authorization_scope"]}, "lifecycle": {"successor_id": inputs["lifecycle"]["successor_id"], "manifest_sha256": inputs["lifecycle_hash"]}, "membership": {"snapshot_id": inputs["membership"]["snapshot_id"], "manifest_sha256": inputs["membership_hash"], "records_sha256": inputs["membership_records_hash"]}},
            "execution_scope": coverage["execution_scope"],
            "source_scope": coverage["source_scope"],
            "source_inventory": {key: {"content_hash": value["content_hash"], "entry_count": value["entry_count"]} for key, value in coverage["sources"].items() if key in ("daily", "adj_factor", "suspend_d")},
        }
        expected["not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection"] = False
        payload = {key: value for key, value in manifest.items() if key != "successor_id"}
        if payload != expected:
            return _invalid("successor binding mismatch")
        computed_id = hashlib.sha256(_canonical(payload)).hexdigest()[:16]
        if manifest.get("successor_id") != computed_id:
            return _invalid("successor ID mismatch")
        return {"status": "valid", "successor_id": computed_id, "manifest_sha256": _sha(manifest_path)}
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return _invalid(str(error))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--successor-dir", type=Path, required=True)
    parser.add_argument("--formal-snapshot-dir", type=Path, required=True)
    parser.add_argument("--coverage-dir", type=Path, default=COVERAGE_DIR)
    parser.add_argument("--scope-dir", type=Path, default=SCOPE_DIR)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    args = parser.parse_args(argv)
    result = verify_successor(
        args.successor_dir,
        formal_snapshot_dir=args.formal_snapshot_dir,
        coverage_dir=args.coverage_dir,
        scope_dir=args.scope_dir,
        evidence_dir=args.evidence_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
