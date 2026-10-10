from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.publish_market_regime_suspension_evidence_successor import publish_successor
from scripts.verify_market_regime_suspension_evidence_successor import verify_successor
from scripts.market_regime_bounded_replay import load_market_regime_evidence


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "docs/verification/market_regime_v11_daily_gap_diagnostics.json"
PREDECESSOR = ROOT / "data/pit/market_regime_suspension_evidence/6a74758b672b90b7"


def test_successor_binds_predecessor_plus_formal_intervals_and_is_write_once(tmp_path: Path) -> None:
    first = publish_successor(diagnostics_path=DIAGNOSTICS, predecessor_dir=PREDECESSOR, output_root=tmp_path)
    assert first["status"] == "published"
    verified = verify_successor(Path(first["path"]), diagnostics_path=DIAGNOSTICS, predecessor_dir=PREDECESSOR)
    assert verified["status"] == "verified"
    assert verified["entry_count"] == 141
    assert verified["provider_bounded_count"] == 135
    assert verified["formal_interval_count"] == 6
    assert publish_successor(diagnostics_path=DIAGNOSTICS, predecessor_dir=PREDECESSOR, output_root=tmp_path)["status"] == "already_published"
    manifest = Path(first["path"]) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"] = payload["entries"][:-1]
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    manifest.with_name(manifest.name + ".sha256").write_text(
        f"{__import__('hashlib').sha256(manifest.read_bytes()).hexdigest()}  manifest.json\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="entry|identity|artifact ID"):
        verify_successor(Path(first["path"]), diagnostics_path=DIAGNOSTICS, predecessor_dir=PREDECESSOR)


def test_replay_loader_consumes_successor_only(tmp_path: Path) -> None:
    published = publish_successor(diagnostics_path=DIAGNOSTICS, predecessor_dir=PREDECESSOR, output_root=tmp_path)
    artifact_id, manifest_sha, entries = load_market_regime_evidence(Path(published["path"]))
    assert artifact_id == published["artifact_id"]
    assert manifest_sha
    assert len(entries) == 141
