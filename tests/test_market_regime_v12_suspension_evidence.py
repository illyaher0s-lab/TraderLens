from pathlib import Path

import pytest

import json

import scripts.publish_market_regime_v12_suspension_evidence as evidence_module
from scripts.market_regime_bounded_replay import load_market_regime_evidence
from scripts.publish_market_regime_v12_suspension_evidence import publish_v12_evidence, verify_v12_evidence


def test_v12_evidence_successor_reuses_exact_provider_and_formal_entries(tmp_path: Path) -> None:
    result = publish_v12_evidence(output_root=tmp_path / "evidence")
    assert result["status"] == "published"
    assert result["stats"] == {
        "entry_count": 112,
        "provider_bounded_count": 110,
        "formal_interval_count": 2,
        "data_fault_count": 0,
    }
    verified = verify_v12_evidence(Path(result["path"]))
    assert verified["status"] == "verified"
    assert verified["entry_count"] == 112
    identity = load_market_regime_evidence(Path(result["path"]))
    assert identity[0] == result["artifact_id"]
    assert len(identity[2]) == 112


def test_v12_evidence_successor_write_once_conflict_is_rejected(tmp_path: Path) -> None:
    first = publish_v12_evidence(output_root=tmp_path / "evidence")
    manifest = Path(first["path"]) / "manifest.json"
    raw = manifest.read_bytes()
    manifest.write_bytes(raw + b"tamper")
    with pytest.raises(ValueError, match="sidecar|identity|write-once"):
        verify_v12_evidence(Path(first["path"]))


def test_formal_entries_do_not_scan_unreferenced_suspend_partitions(monkeypatch: pytest.MonkeyPatch) -> None:
    diagnostics = json.loads(evidence_module.DEFAULT_DIAGNOSTICS.read_text(encoding="utf-8"))
    predecessor = json.loads((evidence_module.DEFAULT_PREDECESSOR / "manifest.json").read_text(encoding="utf-8"))
    formal_gaps = [
        gap for gap in diagnostics["gaps"]
        if (gap["symbol"], gap["date"]) in {("000995.SZ", "20200102"), ("600610.SH", "20200102")}
    ]

    def fail_full_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("full suspend_d history scan is forbidden")

    monkeypatch.setattr(evidence_module, "_formal_events", fail_full_scan, raising=False)
    entries = evidence_module._formal_entries(
        {"gaps": formal_gaps}, predecessor, evidence_module.DEFAULT_FORMAL_ROOT
    )
    assert len(entries) == 2


def test_formal_predecessor_partition_tamper_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    diagnostics = json.loads(evidence_module.DEFAULT_DIAGNOSTICS.read_text(encoding="utf-8"))
    predecessor = json.loads((evidence_module.DEFAULT_PREDECESSOR / "manifest.json").read_text(encoding="utf-8"))
    formal_gaps = [
        gap for gap in diagnostics["gaps"]
        if (gap["symbol"], gap["date"]) == ("000995.SZ", "20200102")
    ]
    formal_entry = next(
        entry for entry in predecessor["entries"]
        if entry["symbol"] == "000995.SZ" and entry["evidence_kind"] == "formal_active_S_to_later_R_interval"
    )
    tampered_path = evidence_module.ROOT / formal_entry["formal_event_sources"]["previous_s"]["partition"]["repo_relative_path"]
    original_sha_file = evidence_module._sha_file

    def tampered_sha(path: Path) -> str:
        if Path(path).resolve() == tampered_path.resolve():
            return "0" * 64
        return original_sha_file(path)

    monkeypatch.setattr(evidence_module, "_sha_file", tampered_sha)
    with pytest.raises(ValueError, match="partition hash mismatch"):
        evidence_module._formal_entries({"gaps": formal_gaps}, predecessor, evidence_module.DEFAULT_FORMAL_ROOT)
