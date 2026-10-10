from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.publish_market_regime_suspension_evidence import publish_evidence
from scripts.verify_market_regime_suspension_evidence import verify_evidence


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "docs/verification/market_regime_v11_daily_gap_diagnostics.json"
PROBE = ROOT / "docs/verification/market_regime_v11_provider_event_probes/111c4d5fcd8bd5a6/manifest.json"


def test_publish_verify_bounded_open_intervals_and_write_once(tmp_path: Path) -> None:
    first = publish_evidence(diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE, output_root=tmp_path)
    assert first["status"] == "published"
    verified = verify_evidence(Path(first["path"]), diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE)
    assert verified["status"] == "verified"
    assert verified["entry_count"] == 135
    assert verified["bounded_open_until_lifecycle_delist_count"] == 135
    second = publish_evidence(diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE, output_root=tmp_path)
    assert second["status"] == "already_published"
    manifest = Path(first["path"]) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"] = payload["entries"][:-1]
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar|artifact identity|entry"):
        verify_evidence(Path(first["path"]), diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE)
