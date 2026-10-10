import json
import hashlib
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
INVALID_COVERAGE_DIR = ROOT / "data/pit/v3_historical_coverage_packages/4d543215598370b5"


@pytest.fixture(scope="module")
def suspension_evidence_manifest(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from scripts.publish_v3_historical_suspension_evidence import publish_evidence

    result = publish_evidence(
        diagnostics_path=ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json",
        provider_probe_path=ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json",
        scope_dir=SCOPE_DIR,
        output_root=tmp_path_factory.mktemp("suspension-evidence"),
    )
    return Path(result["path"]) / "manifest.json"


def test_small_real_slice_reads_each_source_partition_once(suspension_evidence_manifest: Path):
    from scripts.qualify_v3_historical_coverage import scan_coverage

    scope = json.loads((SCOPE_DIR / "manifest.json").read_text(encoding="utf-8"))
    result = scan_coverage(
        scope_dir=SCOPE_DIR,
        execution_dates=scope["execution"]["dates"][:2],
        suspension_evidence_manifest_path=suspension_evidence_manifest,
    )

    assert result["execution_count"] == 2
    assert result["stats"]["data_fault_count"] == 0
    assert result["partition_read_counts"]
    assert max(result["partition_read_counts"].values()) == 1


def test_current_day_liquidity_successor_cannot_be_used_as_historical_input(tmp_path: Path, suspension_evidence_manifest: Path):
    from scripts.qualify_v3_historical_coverage import scan_coverage

    liquidity_manifest = ROOT / "data/pit/liquidity_qualification_successors/7c05ece4d3f01086/manifest.json"
    tampered = tmp_path / "liquidity.json"
    payload = json.loads(liquidity_manifest.read_text(encoding="utf-8"))
    payload["scope"]["start"] = "20250627"
    payload["scope"]["end"] = "20260710"
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    tampered.write_bytes(raw)
    (tmp_path / "liquidity.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  liquidity.json\n")

    import pytest

    with pytest.raises(ValueError, match="current-D-only liquidity"):
        scan_coverage(
            scope_dir=SCOPE_DIR,
            execution_dates=["20250627"],
            liquidity_successor_manifest_path=tampered,
            suspension_evidence_manifest_path=suspension_evidence_manifest,
        )


def test_insufficient_liquidity_history_is_ineligible_not_data_fault(suspension_evidence_manifest: Path):
    from scripts.qualify_v3_historical_coverage import scan_coverage

    result = scan_coverage(scope_dir=SCOPE_DIR, execution_dates=["20250627"], suspension_evidence_manifest_path=suspension_evidence_manifest)
    row = next(item for item in result["unavailable_rows"] if item["symbol"] == "301590.SZ")

    assert row["status"] == "unavailable_ineligible"
    assert row["reason"] == "insufficient_liquidity_history"
    assert row["missing_fields"] == []
    assert result["stats"]["data_fault_count"] == 0
    assert result["stats"]["first_data_fault"] is None
    stats = result["stats"]
    assert stats["expected_stock_days"] == stats["complete_stock_days"] + stats["unavailable_stock_days"] + stats["data_fault_count"]


def test_history_sufficient_qualified_suspension_evidence_publishes(tmp_path: Path, suspension_evidence_manifest: Path):
    from scripts.qualify_v3_historical_coverage import publish_coverage

    result = publish_coverage(scope_dir=SCOPE_DIR, output_root=tmp_path, suspension_evidence_manifest_path=suspension_evidence_manifest)
    assert result["stats"]["data_fault_count"] == 0
    manifest = json.loads((Path(result["path"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lineage"]["suspension_evidence"]["artifact_id"] == json.loads(suspension_evidence_manifest.read_text(encoding="utf-8"))["artifact_id"]


def test_independent_verifier_rejects_inconsistent_first_data_fault():
    import pytest

    from scripts.verify_v3_historical_coverage import verify_coverage

    with pytest.raises(ValueError, match="source adapter binding"):
        verify_coverage(INVALID_COVERAGE_DIR, scope_dir=SCOPE_DIR)


def test_688766_missing_daily_is_zero_only_through_qualified_evidence(tmp_path: Path):
    from scripts.publish_v3_historical_suspension_evidence import publish_evidence
    from scripts.qualify_v3_historical_coverage import scan_coverage

    evidence = publish_evidence(
        diagnostics_path=ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json",
        provider_probe_path=ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json",
        scope_dir=SCOPE_DIR,
        output_root=tmp_path / "evidence",
    )
    scope = json.loads((SCOPE_DIR / "manifest.json").read_text(encoding="utf-8"))
    result = scan_coverage(
        scope_dir=SCOPE_DIR,
        execution_dates=scope["execution"]["dates"][:105],
        suspension_evidence_manifest_path=Path(evidence["path"]) / "manifest.json",
    )

    assert result["stats"]["data_fault_count"] == 0
    row = next(item for item in result["coverage_rows"] if item["execution_date"] == "20251128")
    assert row["data_fault_codes"] == 0


def test_missing_lifecycle_membership_is_hard_data_fault_before_qualified_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import scripts.qualify_v3_historical_coverage as qualifier

    def write_json(path: Path, payload: dict) -> None:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.with_name(path.name + ".sha256").write_text(hashlib.sha256(raw).hexdigest() + "  " + path.name + "\n")

    scope_dir = tmp_path / "scope"
    write_json(
        scope_dir / "manifest.json",
        {
            "execution": {"dates": ["20250627"], "as_of_dates": ["20250626"]},
            "source": {"dates": ["20250626"]},
        },
    )
    b3_manifest = tmp_path / "b3" / "manifest.json"
    write_json(
        b3_manifest,
        {"artifact_id": qualifier.B3_SUCCESSOR_ID, "authorization_scope": "b3_execution_input_binding_only"},
    )
    liquidity_manifest = tmp_path / "liquidity" / "manifest.json"
    write_json(
        liquidity_manifest,
        {
            "artifact_id": qualifier.LIQUIDITY_SUCCESSOR_ID,
            "schema_version": "v3_liquidity_qualification_successor.v1",
            "scope": {"start": "20260710", "end": "20260710"},
        },
    )

    monkeypatch.setattr(qualifier, "verify_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(qualifier, "_load_suspension_evidence", lambda *args, **kwargs: ({}, {}, {}))
    monkeypatch.setattr(qualifier, "_load_lifecycle", lambda *args, **kwargs: ({}, {}))
    monkeypatch.setattr(
        qualifier,
        "_load_membership",
        lambda *args, **kwargs: ({"000991.SZ": [("20160823", None)]}, {}),
    )

    output_root = tmp_path / "qualified"
    with pytest.raises(ValueError, match=r"data_fault: membership symbol missing lifecycle 000991\.SZ"):
        qualifier.publish_coverage(
            scope_dir=scope_dir,
            output_root=output_root,
            input_root=tmp_path / "inputs",
            formal_root=tmp_path / "formal",
            membership_dir=tmp_path / "membership",
            lifecycle_manifest_path=tmp_path / "lifecycle.json",
            b3_successor_manifest_path=b3_manifest,
            liquidity_successor_manifest_path=liquidity_manifest,
            suspension_evidence_manifest_path=tmp_path / "suspension.json",
        )

    assert not output_root.exists()
