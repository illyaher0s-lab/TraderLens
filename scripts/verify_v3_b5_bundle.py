"""Independently verify a v3 B5 four-result bundle and its source bindings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.services.v3_b5_bundle import (
    PAYLOAD_FILES,
    independent_verifier_identity,
    _resolve_code_root,
    verify_b5_bundle,
)
from backend.services.v3_b5_types import RESULT_TYPES
from scripts.publish_v3_b5_bundle import ROOT, load_verified_results


def verify_verified_b5_bundle(
    repo_root: Path,
    bundle_dir: Path,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    expected_bundle_id: str | None = None,
    expected_bundle_manifest_sha256: str | None = None,
    cost_dir: Path | None = None,
    comparison_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
) -> dict[str, Any]:
    try:
        code_root = Path(code_root) if code_root is not None else Path(__file__).resolve().parents[1]
        code_root = _resolve_code_root(code_root)
        artifact_root = Path(artifact_root if artifact_root is not None else repo_root).resolve()
        bundle_dir = Path(bundle_dir)
        manifest_bytes = (bundle_dir / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        actual_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if expected_bundle_id is not None and (
            bundle_dir.name != expected_bundle_id or manifest.get("bundle_id") != expected_bundle_id
        ):
            return {"status": "invalid", "reason": "bundle ID does not match the requested ID"}
        if expected_bundle_manifest_sha256 is not None and actual_manifest_sha256 != expected_bundle_manifest_sha256:
            return {"status": "invalid", "reason": "bundle manifest hash does not match the requested hash"}
        has_strategy_scope = isinstance(manifest.get("lineage"), dict) and (
            "strategy_scoped_universe" in manifest["lineage"]
        )
        lineage = manifest.get("lineage", {})
        scope_binding = lineage.get("strategy_scoped_universe", {}) if isinstance(lineage, dict) else {}
        source_payloads = load_verified_results(
            artifact_root,
            code_root=code_root,
            artifact_root=artifact_root,
            cost_dir=cost_dir,
            comparison_dir=comparison_dir,
            strategy_scope_root=strategy_scope_root,
            include_strategy_scope=has_strategy_scope,
            expected_scope_id=scope_binding.get("snapshot_id") if has_strategy_scope else None,
            expected_scope_manifest_sha256=scope_binding.get("manifest_sha256") if has_strategy_scope else None,
        )
        result = verify_b5_bundle(
            artifact_root,
            bundle_dir,
            code_root=code_root,
            artifact_root=artifact_root,
            strategy_scope_root=strategy_scope_root,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_manifest_sha256=expected_bundle_manifest_sha256,
        )
        if result.get("status") != "verified":
            return result
        verifier_identity = result.get("verifier_identity")
        if not isinstance(verifier_identity, dict) or manifest.get("verifier_identity") != verifier_identity:
            return {"status": "invalid", "reason": "independent verifier identity mismatch"}
        for result_type in RESULT_TYPES:
            path = Path(bundle_dir) / PAYLOAD_FILES[result_type]
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload != source_payloads[result_type]:
                return {"status": "invalid", "reason": f"source result mismatch: {result_type}"}
            ref = manifest["results"][result_type]
            if ref["payload_id"] != source_payloads[result_type]["payload_id"] or ref["canonical_payload_sha256"] != source_payloads[result_type]["canonical_payload_sha256"]:
                return {"status": "invalid", "reason": f"source result reference mismatch: {result_type}"}
        return {
            **result,
            "authorization_scope": manifest["authorization_scope"],
            "not_authorized_for_b6_oos_gate_promotion_signal": manifest[
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ],
            "verifier_identity": verifier_identity,
            "lineage": manifest["lineage"],
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--strategy-scope-root", type=Path)
    args = parser.parse_args()
    bundle_dir = args.artifact_root / "data/pit/v3_b5_validation_bundles" / args.bundle_id
    response = verify_verified_b5_bundle(
        args.artifact_root,
        bundle_dir,
        code_root=args.code_root,
        artifact_root=args.artifact_root,
        expected_bundle_id=args.bundle_id,
        expected_bundle_manifest_sha256=args.manifest_sha256,
        strategy_scope_root=args.strategy_scope_root,
    )
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    if response.get("status") != "verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
