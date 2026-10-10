"""Build a V2 availability-bounded qualification successor from metadata only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.strategy_template_library import get_template_by_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_successor(
    predecessor_manifest_path: Path,
    coverage_manifest_path: Path,
    coverage_sidecar_path: Path,
    coverage_by_code_path: Path,
    coverage_by_date_path: Path,
    unavailable_path: Path,
    scope_freeze_path: Path,
    output_dir: Path,
) -> dict:
    """Publish one immutable successor after validating only explicit metadata inputs."""
    predecessor = json.loads(predecessor_manifest_path.read_text(encoding="utf-8"))
    predecessor_hash = _sha256(predecessor_manifest_path)
    coverage = json.loads(coverage_manifest_path.read_text(encoding="utf-8"))
    coverage_hash = _sha256(coverage_manifest_path)
    coverage_sidecar = coverage_sidecar_path.read_text(encoding="utf-8").strip()

    if predecessor.get("status") != "not_qualified":
        raise ValueError("Predecessor status must be not_qualified")
    if coverage_hash != coverage_sidecar:
        raise ValueError("Coverage sidecar mismatch")
    if coverage.get("status") != "coverage_published":
        raise ValueError("Coverage must be coverage_published")
    if coverage.get("build_completion", {}).get("status") != "completed":
        raise ValueError("Coverage build must be completed")
    if coverage.get("build_completion", {}).get("structural_validation") != "passed":
        raise ValueError("Coverage structural validation must be passed")
    if coverage.get("structural_errors") != []:
        raise ValueError("Coverage has structural errors")
    if coverage.get("input_qualification_package_id") != predecessor["qualification_package_id"]:
        raise ValueError("Coverage predecessor package mismatch")
    if coverage.get("input_manifest_content_hashes", {}).get("qualification_manifest.json") != predecessor_hash:
        raise ValueError("Coverage predecessor content hash mismatch")
    for coverage_key, predecessor_key in (
        ("input_scope_hash", "scope_hash"),
        ("input_template_hash", "template_hash"),
        ("input_data_requirements_hash", "data_requirements_hash"),
        ("input_snapshot_hash", "snapshot_hash"),
    ):
        if coverage.get(coverage_key) != predecessor[predecessor_key]:
            raise ValueError(f"Coverage/predecessor mismatch: {coverage_key}")

    expected = coverage["expected_stock_days"]
    complete = coverage["complete_stock_days"]
    unavailable = coverage["unavailable_stock_days"]
    if complete + unavailable != expected:
        raise ValueError("Coverage arithmetic mismatch")

    coverage_by_code_hash = _sha256(coverage_by_code_path)
    coverage_by_date_hash = _sha256(coverage_by_date_path)
    unavailable_hash = _sha256(unavailable_path)
    if coverage_by_code_hash != coverage["coverage_by_code_hash"]:
        raise ValueError("coverage_by_code parquet hash mismatch")
    if coverage_by_date_hash != coverage["coverage_by_date_hash"]:
        raise ValueError("coverage_by_date parquet hash mismatch")
    if unavailable_hash != coverage["unavailable_parquet_hash"]:
        raise ValueError("unavailable parquet hash mismatch")

    template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
    if template is None:
        raise ValueError("Template not found")
    if template.frozen_template_hash != predecessor["template_hash"]:
        raise ValueError("Template/predecessor hash mismatch")
    if template.frozen_template_hash != coverage["input_template_hash"]:
        raise ValueError("Template/coverage hash mismatch")

    payload = {
        "successor_schema_version": "v1",
        "status": "availability_bounded_qualified",
        "predecessor_qualification_package_id": predecessor["qualification_package_id"],
        "predecessor_manifest_sha256": predecessor_hash,
        "predecessor_original_status": predecessor["status"],
        "predecessor_scope_hash": predecessor["scope_hash"],
        "predecessor_template_hash": predecessor["template_hash"],
        "predecessor_data_requirements_hash": predecessor["data_requirements_hash"],
        "predecessor_snapshot_hash": predecessor["snapshot_hash"],
        "predecessor_guard_config_hash": predecessor["guard_config_hash"],
        "predecessor_algorithm_hash": predecessor["algorithm_hash"],
        "scope_freeze_sha256": _sha256(scope_freeze_path),
        "coverage_package_id": coverage["coverage_hash"],
        "coverage_manifest_sha256": coverage_hash,
        "coverage_detached_sidecar_sha256": coverage_sidecar,
        "coverage_algorithm_hash": coverage["algorithm_hash"],
        "coverage_schema_version": coverage["coverage_schema"]["coverage_schema_version"],
        "coverage_structural_validation": coverage["build_completion"]["structural_validation"],
        "coverage_structural_errors": coverage["structural_errors"],
        "coverage_expected_stock_days": expected,
        "coverage_complete_stock_days": complete,
        "coverage_unavailable_stock_days": unavailable,
        "coverage_field_missing_counts": coverage["field_missing_counts"],
        "coverage_by_code_sha256": coverage_by_code_hash,
        "coverage_by_date_sha256": coverage_by_date_hash,
        "coverage_unavailable_sha256": unavailable_hash,
        "coverage_template_hash": coverage["input_template_hash"],
        "template_id": template.template_id,
        "template_version": template.version,
        "template_hash": template.frozen_template_hash,
        "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": True,
    }
    successor_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    successor_dir = output_dir / successor_id
    if successor_dir.exists():
        raise RuntimeError(f"Successor {successor_id} already exists at {successor_dir}")

    successor_dir.mkdir(parents=True)
    payload["successor_id"] = successor_id
    manifest_path = successor_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (successor_dir / "manifest.json.sha256").write_text(_sha256(manifest_path), encoding="utf-8")

    from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor

    result = verify_successor(
        successor_dir,
        predecessor_manifest_path=predecessor_manifest_path,
        coverage_manifest_path=coverage_manifest_path,
        coverage_sidecar_path=coverage_sidecar_path,
        coverage_by_code_path=coverage_by_code_path,
        coverage_by_date_path=coverage_by_date_path,
        unavailable_path=unavailable_path,
        scope_freeze_path=scope_freeze_path,
    )
    if result["status"] != "valid":
        raise RuntimeError(f"Successor verification failed: {result['reason']}")
    return {"status": "availability_bounded_qualified", "successor_id": successor_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor-manifest", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--coverage-sidecar", type=Path, required=True)
    parser.add_argument("--coverage-by-code", type=Path, required=True)
    parser.add_argument("--coverage-by-date", type=Path, required=True)
    parser.add_argument("--unavailable", type=Path, required=True)
    parser.add_argument("--scope-freeze", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_successor(
        predecessor_manifest_path=args.predecessor_manifest,
        coverage_manifest_path=args.coverage_manifest,
        coverage_sidecar_path=args.coverage_sidecar,
        coverage_by_code_path=args.coverage_by_code,
        coverage_by_date_path=args.coverage_by_date,
        unavailable_path=args.unavailable,
        scope_freeze_path=args.scope_freeze,
        output_dir=args.output_root,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
