import hashlib
import json
from pathlib import Path

import pytest

from scripts.publish_v3_liquidity_successor import publish_successor


def _write_artifact(root: Path, artifact_id: str, payload: dict) -> Path:
    d = root / artifact_id
    d.mkdir(parents=True)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    (d / "manifest.json").write_bytes(raw)
    (d / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n")
    return d


def test_publishes_metadata_only_successor_without_mutating_predecessor(tmp_path: Path):
    predecessor = _write_artifact(tmp_path / "pred", "426e468e414f0cf0", {
        "artifact_id": "426e468e414f0cf0",
        "schema_version": "v3_liquidity_qualification.v1",
        "status": "published",
        "algorithm": {"algorithm_id": "avg_amount_20d_shsz_common_v1"},
        "scope": {"stats": {"expected_scope_count": 5522, "complete_count": 5519, "unavailable_ineligible_count": 3, "data_fault_count": 0, "first_data_fault": None}},
        "sources": {"daily": {}, "suspend_d": {}},
    })
    overlay = _write_artifact(tmp_path / "overlay", "4d4159824570b6f0", {
        "artifact_id": "4d4159824570b6f0", "schema_version": "v3_liquidity_suspend_corrective.v1",
        "status": "published", "entries": [{"symbol": "000524.SZ", "trade_date": "20260624"}],
    })
    before = (predecessor / "manifest.json").read_bytes()
    result = publish_successor(predecessor=predecessor, corrective_overlay=overlay,
                               corrective_verification={"status": "verified", "artifact_id": "4d4159824570b6f0"},
                               output_root=tmp_path / "successors")
    assert result["status"] == "published"
    assert result["artifact_id"] != "426e468e414f0cf0"
    assert (predecessor / "manifest.json").read_bytes() == before
    successor = json.loads((Path(result["path"]) / "manifest.json").read_text())
    assert successor["predecessor"]["artifact_id"] == "426e468e414f0cf0"
    assert successor["corrective_overlay"]["artifact_id"] == "4d4159824570b6f0"
    assert successor["correction"]["type"] == "metadata binding correction only"
    assert successor["sources"]["corrective_overlay"]["sha256"] == hashlib.sha256((overlay / "manifest.json").read_bytes()).hexdigest()


def test_rejects_predecessor_that_already_has_overlay(tmp_path: Path):
    predecessor = _write_artifact(tmp_path / "pred", "426e468e414f0cf0", {
        "artifact_id": "426e468e414f0cf0", "scope": {"stats": {"expected_scope_count": 5522, "complete_count": 5519, "unavailable_ineligible_count": 3, "data_fault_count": 0}},
        "sources": {"corrective_overlay": {"sha256": "x"}},
    })
    overlay = _write_artifact(tmp_path / "overlay", "4d4159824570b6f0", {"artifact_id": "4d4159824570b6f0"})
    with pytest.raises(ValueError, match="already has overlay"):
        publish_successor(predecessor=predecessor, corrective_overlay=overlay,
                          corrective_verification={"status": "verified", "artifact_id": "4d4159824570b6f0"}, output_root=tmp_path / "out")
