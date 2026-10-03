"""Independently verify a v3 B5 four-result bundle and its source bindings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.services.v3_b5_bundle import (
    PAYLOAD_FILES,
    independent_verifier_identity,
    verify_b5_bundle,
)
from backend.services.v3_b5_types import RESULT_TYPES
from scripts.publish_v3_b5_bundle import ROOT, load_verified_results


def verify_verified_b5_bundle(
    repo_root: Path,
    bundle_dir: Path,
    *,
    cost_dir: Path | None = None,
    comparison_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        source_payloads = load_verified_results(repo_root, cost_dir=cost_dir, comparison_dir=comparison_dir)
        result = verify_b5_bundle(Path(repo_root), Path(bundle_dir))
        if result.get("status") != "verified":
            return result
        manifest = json.loads((Path(bundle_dir) / "manifest.json").read_text(encoding="utf-8"))
        verifier_identity = independent_verifier_identity()
        if manifest.get("verifier_identity") != verifier_identity:
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
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    response = verify_verified_b5_bundle(ROOT, args.bundle_dir)
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    if response.get("status") != "verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
