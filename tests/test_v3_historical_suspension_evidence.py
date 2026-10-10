from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
DIAGNOSTICS = ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json"
PROBE = ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json"
SCOPE = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"


def _publish(tmp_path: Path) -> Path:
    from scripts.publish_v3_historical_suspension_evidence import publish_evidence

    result = publish_evidence(
        diagnostics_path=DIAGNOSTICS,
        provider_probe_path=PROBE,
        scope_dir=SCOPE,
        output_root=tmp_path / "evidence",
    )
    return Path(result["path"]) / "manifest.json"


def test_publishes_and_verifies_exact_58_scope_bound_entries(tmp_path: Path):
    manifest_path = _publish(tmp_path)

    from scripts.verify_v3_historical_suspension_evidence import verify_evidence

    result = verify_evidence(manifest_path.parent, diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE, scope_dir=SCOPE)

    assert result["status"] == "verified"
    assert result["entry_count"] == 58
    assert result["exact_same_day_s_count"] == 58


def test_rejects_provider_probe_hash_tamper(tmp_path: Path):
    manifest_path = _publish(tmp_path)
    payload = json.loads(PROBE.read_text(encoding="utf-8"))
    payload["d_evidence"][0]["classification"] = "tampered"
    tampered_probe = tmp_path / "probe.json"
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tampered_probe.write_bytes(raw)

    from scripts.verify_v3_historical_suspension_evidence import verify_evidence

    with pytest.raises(ValueError, match="provider probe hash"):
        verify_evidence(manifest_path.parent, diagnostics_path=DIAGNOSTICS, provider_probe_path=tampered_probe, scope_dir=SCOPE)


def test_rejects_unauthorized_execution_binding(tmp_path: Path):
    manifest_path = _publish(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["entries"][0]["execution_dates"] = ["20990101"]
    payload.pop("artifact_id", None)
    raw = json.dumps({**payload, "artifact_id": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]}, sort_keys=True, separators=(",", ":")).encode()
    manifest_path.write_bytes(raw)
    (manifest_path.parent / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n", encoding="utf-8")

    from scripts.verify_v3_historical_suspension_evidence import verify_evidence

    with pytest.raises(ValueError, match="execution"):
        verify_evidence(manifest_path.parent, diagnostics_path=DIAGNOSTICS, provider_probe_path=PROBE, scope_dir=SCOPE)
