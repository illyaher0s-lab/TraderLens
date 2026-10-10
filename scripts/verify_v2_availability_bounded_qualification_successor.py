"""Independently verify a V2 availability-bounded qualification successor."""
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


def _invalid(reason: str) -> dict:
    return {"status": "invalid", "reason": reason}


def verify_successor(
    successor_dir: Path,
    *,
    predecessor_manifest_path: Path,
    coverage_manifest_path: Path,
    coverage_sidecar_path: Path,
    coverage_by_code_path: Path,
    coverage_by_date_path: Path,
    unavailable_path: Path,
    scope_freeze_path: Path,
) -> dict:
    """Verify successor bytes against every explicitly supplied bound input."""
    try:
        manifest_path = successor_dir / "manifest.json"
        sidecar_path = successor_dir / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            return _invalid("successor manifest or sidecar missing")
        if _sha256(manifest_path) != sidecar_path.read_text(encoding="utf-8").strip():
            return _invalid("successor sidecar mismatch")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "availability_bounded_qualified":
            return _invalid("successor status mismatch")
        if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection") is not True:
            return _invalid("successor authorization guard missing")

        predecessor_hash = _sha256(predecessor_manifest_path)
        predecessor = json.loads(predecessor_manifest_path.read_text(encoding="utf-8"))
        if predecessor.get("status") != "not_qualified":
            return _invalid("predecessor status mismatch")
        predecessor_fields = {
            "predecessor_qualification_package_id": predecessor["qualification_package_id"],
            "predecessor_manifest_sha256": predecessor_hash,
            "predecessor_original_status": predecessor["status"],
            "predecessor_scope_hash": predecessor["scope_hash"],
            "predecessor_template_hash": predecessor["template_hash"],
            "predecessor_data_requirements_hash": predecessor["data_requirements_hash"],
            "predecessor_snapshot_hash": predecessor["snapshot_hash"],
            "predecessor_guard_config_hash": predecessor["guard_config_hash"],
            "predecessor_algorithm_hash": predecessor["algorithm_hash"],
        }
        for key, value in predecessor_fields.items():
            if manifest.get(key) != value:
                return _invalid(f"predecessor binding mismatch: {key}")

        coverage_hash = _sha256(coverage_manifest_path)
        coverage_sidecar = coverage_sidecar_path.read_text(encoding="utf-8").strip()
        if coverage_hash != coverage_sidecar:
            return _invalid("coverage sidecar mismatch")
        coverage = json.loads(coverage_manifest_path.read_text(encoding="utf-8"))
        if coverage.get("status") != "coverage_published":
            return _invalid("coverage publication status mismatch")
        if coverage.get("build_completion", {}).get("status") != "completed":
            return _invalid("coverage completion status mismatch")
        if coverage.get("build_completion", {}).get("structural_validation") != "passed":
            return _invalid("coverage structural validation mismatch")
        if coverage.get("structural_errors") != []:
            return _invalid("coverage structural errors present")
        if coverage.get("input_qualification_package_id") != predecessor["qualification_package_id"]:
            return _invalid("coverage predecessor package mismatch")
        if coverage.get("input_manifest_content_hashes", {}).get("qualification_manifest.json") != predecessor_hash:
            return _invalid("coverage predecessor content hash mismatch")
        for coverage_key, predecessor_key in (
            ("input_scope_hash", "scope_hash"),
            ("input_template_hash", "template_hash"),
            ("input_data_requirements_hash", "data_requirements_hash"),
            ("input_snapshot_hash", "snapshot_hash"),
        ):
            if coverage.get(coverage_key) != predecessor[predecessor_key]:
                return _invalid(f"coverage/predecessor mismatch: {coverage_key}")

        expected = coverage["expected_stock_days"]
        complete = coverage["complete_stock_days"]
        unavailable = coverage["unavailable_stock_days"]
        if complete + unavailable != expected:
            return _invalid("coverage arithmetic mismatch")
        coverage_fields = {
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
            "coverage_by_code_sha256": _sha256(coverage_by_code_path),
            "coverage_by_date_sha256": _sha256(coverage_by_date_path),
            "coverage_unavailable_sha256": _sha256(unavailable_path),
            "coverage_template_hash": coverage["input_template_hash"],
        }
        if coverage_fields["coverage_by_code_sha256"] != coverage["coverage_by_code_hash"]:
            return _invalid("coverage_by_code parquet hash mismatch")
        if coverage_fields["coverage_by_date_sha256"] != coverage["coverage_by_date_hash"]:
            return _invalid("coverage_by_date parquet hash mismatch")
        if coverage_fields["coverage_unavailable_sha256"] != coverage["unavailable_parquet_hash"]:
            return _invalid("unavailable parquet hash mismatch")
        for key, value in coverage_fields.items():
            if manifest.get(key) != value:
                return _invalid(f"coverage binding mismatch: {key}")

        if manifest.get("scope_freeze_sha256") != _sha256(scope_freeze_path):
            return _invalid("scope freeze hash mismatch")

        template = get_template_by_id(manifest.get("template_id", ""))
        if template is None:
            return _invalid("template ID is not resolvable")
        if manifest.get("template_version") != template.version:
            return _invalid("template version mismatch")
        if manifest.get("template_hash") != template.frozen_template_hash:
            return _invalid("template hash mismatch")
        if template.frozen_template_hash != predecessor["template_hash"]:
            return _invalid("template/predecessor hash mismatch")
        if template.frozen_template_hash != coverage["input_template_hash"]:
            return _invalid("template/coverage hash mismatch")

        payload = {key: value for key, value in manifest.items() if key != "successor_id"}
        computed_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        if manifest.get("successor_id") != computed_id:
            return _invalid("successor ID mismatch")
        return {"status": "valid", "successor_id": manifest["successor_id"]}
    except (KeyError, OSError, json.JSONDecodeError, TypeError) as error:
        return _invalid(f"input unreadable: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--successor-dir", type=Path, required=True)
    parser.add_argument("--predecessor-manifest", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--coverage-sidecar", type=Path, required=True)
    parser.add_argument("--coverage-by-code", type=Path, required=True)
    parser.add_argument("--coverage-by-date", type=Path, required=True)
    parser.add_argument("--unavailable", type=Path, required=True)
    parser.add_argument("--scope-freeze", type=Path, required=True)
    args = parser.parse_args()
    result = verify_successor(
        args.successor_dir,
        predecessor_manifest_path=args.predecessor_manifest,
        coverage_manifest_path=args.coverage_manifest,
        coverage_sidecar_path=args.coverage_sidecar,
        coverage_by_code_path=args.coverage_by_code,
        coverage_by_date_path=args.coverage_by_date,
        unavailable_path=args.unavailable,
        scope_freeze_path=args.scope_freeze,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
