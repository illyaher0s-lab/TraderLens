"""Independent verifier for the v3 execution-semantics supplement."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.publish_v3_execution_semantics import (
    ROOT,
    PREDECESSOR_ID,
    PREDECESSOR_MANIFEST_SHA256,
    SCHEMA,
    _canonical,
    _sha,
    _sha_bytes,
    build_payload,
)


HISTORICAL_PREDECESSORS = {
    "680cd55c91254667": "c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39",
    "708dbfa1c5601113": "f9dfaa281518070be6875d1cea5fe07c17f5e22f8366d0af9bced64b7bc6a9c8",
    "dc6ba0ca0df66624": "338a03bea0a3e723448954bfa869ee32354b8cbb149d8089bfc500e7f3888456",
    PREDECESSOR_ID: PREDECESSOR_MANIFEST_SHA256,
}


def _invalid(reason: str) -> dict:
    return {"status": "invalid", "reason": reason}


def verify_v3_execution_semantics(
    supplement_dir: Path,
    *,
    repo_root: Path = ROOT,
    source_root: Path | None = None,
) -> dict:
    try:
        supplement_dir = Path(supplement_dir)
        manifest_path = supplement_dir / "manifest.json"
        sidecar_path = supplement_dir / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            return _invalid("supplement manifest or sidecar missing")
        manifest_hash = _sha(manifest_path)
        if sidecar_path.read_text(encoding="utf-8").split()[0] != manifest_hash:
            return _invalid("supplement sidecar mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        supplement_id = manifest.get("supplement_id")
        if supplement_id != supplement_dir.name:
            return _invalid("supplement directory identity mismatch")
        if manifest.get("schema_version") != SCHEMA:
            return _invalid("supplement schema mismatch")
        if manifest.get("status") != "published" or manifest.get("authorization_scope") != "v3_manual_trading_execution":
            return _invalid("supplement status or authorization mismatch")
        if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False:
            return _invalid("supplement authorization disclosure mismatch")

        historical_manifest_sha256 = HISTORICAL_PREDECESSORS.get(supplement_id)
        if historical_manifest_sha256 is not None:
            if manifest_hash != historical_manifest_sha256:
                return _invalid("historical predecessor bytes mismatch")
            return {
                "status": "superseded",
                "reason": "historical supplement is immutable and not current",
                "supplement_id": supplement_id,
                "path": str(supplement_dir),
                "manifest_sha256": manifest_hash,
            }

        payload = {key: value for key, value in manifest.items() if key != "supplement_id"}
        expected = build_payload(Path(repo_root), source_root=source_root)
        if payload != expected:
            return _invalid("supplement binding or source hash mismatch")
        expected_id = _sha_bytes(_canonical(expected))[:16]
        if manifest.get("supplement_id") != expected_id:
            return _invalid("supplement identity mismatch")
        return {
            "status": "verified",
            "supplement_id": expected_id,
            "path": str(supplement_dir),
            "manifest_sha256": manifest_hash,
            "source_bindings_verified": len(manifest["source_bindings"]),
            "criteria_envelope_hash": manifest["criteria"]["envelope_hash"],
            "protocol_snapshot_id": manifest["protocol"]["protocol_snapshot_id"],
            "strategy_revision_id": manifest["strategy"]["strategy_revision_id"],
            "data_snapshot_hash": manifest["data_chain"]["formal_snapshot"]["semantic_hash"],
        }
    except (OSError, UnicodeDecodeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _invalid(str(error))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("supplement_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_v3_execution_semantics(args.supplement_dir), sort_keys=True))
