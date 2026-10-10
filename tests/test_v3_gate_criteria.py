from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/services/prototype_gate_v2.py"
STABLE_SOURCE = ROOT / "backend/services/prototype_gate_criteria_surface.py"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _rewrite_manifest(manifest_path: Path, mutate) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest["manifest_content_hash"] = ""
    manifest["manifest_content_hash"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    raw = _canonical(manifest)
    manifest_path.write_bytes(raw)
    manifest_path.with_name("manifest.json.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n",
        encoding="utf-8",
    )


def test_gate_and_kill_criteria_publish_and_verify_independently(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair
    from scripts.verify_v3_gate_criteria import verify_criteria_pair, verify_criteria_snapshot

    result = publish_criteria_pair(output_root=tmp_path)
    assert result["status"] == "published"
    gate_dir = Path(result["gate"]["path"])
    kill_dir = Path(result["kill"]["path"])
    gate = verify_criteria_snapshot(gate_dir)
    kill = verify_criteria_snapshot(kill_dir)
    pair = verify_criteria_pair(tmp_path)
    assert gate["status"] == "valid"
    assert kill["status"] == "valid"
    assert pair["status"] == "valid"
    assert gate["artifact_type"] == "gate_criteria"
    assert kill["artifact_type"] == "kill_criteria"
    assert gate["envelope_hash"] == pair["envelope_hash"]
    assert kill["envelope_hash"] == pair["envelope_hash"]
    assert (gate_dir / "manifest.json.sha256").is_file()
    assert (kill_dir / "manifest.json.sha256").is_file()


def test_criteria_payload_is_effective_evaluator_only_and_excludes_oos_enforcement(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    result = publish_criteria_pair(output_root=tmp_path)
    gate = json.loads((Path(result["gate"]["path"]) / "manifest.json").read_text(encoding="utf-8"))
    kill = json.loads((Path(result["kill"]["path"]) / "manifest.json").read_text(encoding="utf-8"))
    for manifest in (gate, kill):
        assert manifest["source_inventory"]["oos_draw_policies"]["status"] == "declared_but_not_enforced_by_evaluate"
        assert manifest["source_inventory"]["oos_draw_policies"]["effective_in_evaluate"] is False
        effective = json.dumps(manifest["criteria"], sort_keys=True)
        assert "min_sharpe" not in effective
        assert "max_drawdown" not in effective
        assert manifest["criteria"]["side_effects"]["max_verdict"] == "candidate_for_prototype_passed"


def test_criteria_verifier_rejects_evaluator_source_tamper(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair
    from scripts.verify_v3_gate_criteria import verify_criteria_pair

    source_copy = tmp_path / "prototype_gate_v2.py"
    shutil.copy2(SOURCE, source_copy)
    publish_criteria_pair(output_root=tmp_path / "criteria", source_path=source_copy)
    source_copy.write_bytes(source_copy.read_bytes() + b"\n# tampered\n")
    result = verify_criteria_pair(tmp_path / "criteria", source_path=source_copy)
    assert result["status"] == "invalid"
    assert "source" in result["reason"]


def test_criteria_write_once_and_frozen_reference_hashes(tmp_path: Path):
    from contracts.strategy import FrozenCriteriaReference
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    first = publish_criteria_pair(output_root=tmp_path)
    second = publish_criteria_pair(output_root=tmp_path)
    assert second["status"] == "already_published"
    gate_manifest = json.loads((Path(first["gate"]["path"]) / "manifest.json").read_text(encoding="utf-8"))
    criteria_json = json.dumps(gate_manifest["criteria"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert FrozenCriteriaReference(
        snapshot_id=gate_manifest["snapshot_id"],
        criteria_json=criteria_json,
        declared_content_hash=gate_manifest["criteria_content_hash"],
    ).declared_content_hash == hashlib.sha256(criteria_json.encode("utf-8")).hexdigest()
    gate_manifest["criteria"]["tampered"] = True
    raw = json.dumps(gate_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (Path(first["gate"]["path"]) / "manifest.json").write_bytes(raw)
    with pytest.raises(ValueError, match="write-once"):
        publish_criteria_pair(output_root=tmp_path)


def test_effective_criteria_surface_matches_frozen_six_conditions():
    from backend.services.prototype_gate_criteria_surface import (
        EffectiveCriteriaDecision,
        FrozenEffectiveCriteriaInput,
        evaluate_effective_criteria,
    )

    valid = dict(
        future_data_violation_count=0,
        integrity_status="valid",
        stress_cost_result={"status": "pass"},
        control_comparison={"status": "pass"},
        base_cost_result={"status": "pass"},
        benchmark_comparison={"status": "pass"},
        data_quality_status="sufficient",
        beta_dominated=False,
        single_symbol_concentration={"status": "pass"},
        single_month_concentration={"status": "pass"},
    )
    cases = (
        ("future_data_violation", {"future_data_violation_count": 1}),
        ("invalid_report_integrity", {"integrity_status": "invalid"}),
        ("missing_or_failed_b4_result", {"stress_cost_result": None}),
        ("invalid_data_quality", {"data_quality_status": "invalid"}),
        ("beta_dominated", {"beta_dominated": True}),
        (
            "concentration_risk",
            {"single_month_concentration": {"status": "failed"}},
        ),
    )

    for issue_id, override in cases:
        decision = evaluate_effective_criteria(
            FrozenEffectiveCriteriaInput(**{**valid, **override})
        )
        assert isinstance(decision, EffectiveCriteriaDecision)
        assert decision.blocking_issue_ids == (issue_id,)
        assert decision.verdict == "rejected"

    mixed = evaluate_effective_criteria(
        FrozenEffectiveCriteriaInput(
            **{
                **valid,
                "future_data_violation_count": 1,
                "integrity_status": "invalid",
                "base_cost_result": {"status": "failed"},
                "beta_dominated": True,
                "single_symbol_concentration": {"status": "failed"},
            }
        )
    )
    assert mixed.blocking_issue_ids == (
        "future_data_violation",
        "invalid_report_integrity",
        "missing_or_failed_b4_result",
        "beta_dominated",
        "concentration_risk",
    )
    assert mixed.verdict == "rejected"

    passed = evaluate_effective_criteria(FrozenEffectiveCriteriaInput(**valid))
    assert passed.blocking_issue_ids == ()
    assert passed.verdict == "candidate_for_prototype_passed"

    with pytest.raises((TypeError, ValueError)):
        FrozenEffectiveCriteriaInput(**{**valid, "unexpected": True})


def test_effective_criteria_surface_never_emits_prototype_passed_or_promotion():
    from backend.services.prototype_gate_criteria_surface import (
        EffectiveCriteriaDecision,
        FrozenEffectiveCriteriaInput,
        evaluate_effective_criteria,
    )

    assert set(FrozenEffectiveCriteriaInput.model_fields) == {
        "future_data_violation_count",
        "integrity_status",
        "stress_cost_result",
        "control_comparison",
        "base_cost_result",
        "benchmark_comparison",
        "data_quality_status",
        "beta_dominated",
        "single_symbol_concentration",
        "single_month_concentration",
    }
    assert set(EffectiveCriteriaDecision.model_fields) == {
        "blocking_issue_ids",
        "verdict",
    }
    decision = evaluate_effective_criteria(
        FrozenEffectiveCriteriaInput(
            future_data_violation_count=0,
            integrity_status="valid",
            stress_cost_result={"status": "pass"},
            control_comparison={"status": "pass"},
            base_cost_result={"status": "pass"},
            benchmark_comparison={"status": "pass"},
            data_quality_status="sufficient",
            beta_dominated=False,
            single_symbol_concentration={"status": "pass"},
            single_month_concentration={"status": "pass"},
        )
    )
    assert decision.verdict == "candidate_for_prototype_passed"
    assert decision.verdict != "prototype_passed"
    assert not hasattr(decision, "promotion_id")
    assert not hasattr(decision, "signal_id")


def test_v2_snapshot_id_covers_kind_content_evaluator_and_contract(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import (
        publish_criteria_pair,
        publish_criteria_pair_v2,
    )

    v1 = publish_criteria_pair(output_root=tmp_path / "v1")
    v2 = publish_criteria_pair_v2(output_root=tmp_path / "v2")
    v1_gate = json.loads(
        (Path(v1["gate"]["path"]) / "manifest.json").read_text(encoding="utf-8")
    )
    v2_gate = json.loads(
        (Path(v2["gate"]["path"]) / "manifest.json").read_text(encoding="utf-8")
    )

    assert v2_gate["schema_version"] == "prototype_gate_v2_criteria_snapshot.v2"
    assert v2_gate["criteria_content_hash"] == v1_gate["criteria_content_hash"]
    assert v2_gate["snapshot_id"].startswith("prototype_gate_v2_gate_v2_")
    assert v2_gate["snapshot_id"] != v1_gate["snapshot_id"]
    identity = v2_gate["identity"]
    assert set(identity) == {
        "schema_version",
        "criteria_contract_version",
        "artifact_type",
        "criteria_content_hash",
        "evaluator_surface_id",
        "evaluator_algorithm_id",
        "evaluator_source_sha256",
    }
    assert identity["schema_version"] == "prototype_gate_v2_criteria_snapshot.v2"
    assert identity["criteria_contract_version"] == "v2"
    assert identity["artifact_type"] == "gate_criteria"
    assert identity["evaluator_surface_id"] == "prototype_gate_effective_criteria.v2"
    assert identity["evaluator_algorithm_id"] == "b6_effective_criteria.v2"
    assert identity["evaluator_source_sha256"] == hashlib.sha256(
        STABLE_SOURCE.read_bytes()
    ).hexdigest()
    identity_hash = hashlib.sha256(_canonical(identity)).hexdigest()
    assert v2_gate["snapshot_id"] == f"prototype_gate_v2_gate_v2_{identity_hash[:16]}"
    assert v2_gate["evaluator"]["repo_relative_path"] == (
        "backend/services/prototype_gate_criteria_surface.py"
    )
    assert v2_gate["evaluator_algorithm"] == {
        "surface_id": "prototype_gate_effective_criteria.v2",
        "algorithm_id": "b6_effective_criteria.v2",
        "contract_version": "v2",
    }


def test_v2_pair_envelope_uses_v2_snapshot_ids_and_content_hashes(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import (
        publish_criteria_pair,
        publish_criteria_pair_v2,
    )
    from scripts.verify_v3_gate_criteria import verify_criteria_pair

    result = publish_criteria_pair_v2(output_root=tmp_path)
    pair = verify_criteria_pair(tmp_path)
    assert result["status"] == "published"
    assert pair["status"] == "valid"
    gate = json.loads(
        (Path(result["gate"]["path"]) / "manifest.json").read_text(encoding="utf-8")
    )
    kill = json.loads(
        (Path(result["kill"]["path"]) / "manifest.json").read_text(encoding="utf-8")
    )
    envelope = gate["envelope"]
    envelope_base = {
        "schema_version": "prototype_gate_v2_criteria_envelope.v2",
        "criteria_contract_version": "v2",
        "gate_snapshot_id": gate["snapshot_id"],
        "gate_content_hash": gate["criteria_content_hash"],
        "kill_snapshot_id": kill["snapshot_id"],
        "kill_content_hash": kill["criteria_content_hash"],
    }
    assert envelope == {
        **envelope_base,
        "envelope_hash": hashlib.sha256(_canonical(envelope_base)).hexdigest(),
    }
    assert kill["envelope"] == envelope
    assert pair["envelope_hash"] == envelope["envelope_hash"]

    history_root = tmp_path.parent / "v1-v2-history"
    publish_criteria_pair_v2(output_root=history_root)
    publish_criteria_pair(output_root=history_root)
    history_pair = verify_criteria_pair(history_root)
    assert history_pair["status"] == "valid"
    assert history_pair["gate"]["snapshot_id"].startswith("prototype_gate_v2_gate_v2_")

    tampered_root = tmp_path.parent / "v2-envelope-tampered"
    shutil.copytree(tmp_path, tampered_root)
    tampered_gate = next(tampered_root.glob("*/manifest.json"))
    _rewrite_manifest(
        tampered_gate,
        lambda manifest: manifest["envelope"].update(
            {"gate_content_hash": "f" * 64}
        ),
    )
    tampered_pair = verify_criteria_pair(tampered_root)
    assert tampered_pair["status"] == "invalid"


def test_v2_verifier_rejects_v1_manifest_and_v1_verifier_rejects_v2(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import (
        publish_criteria_pair,
        publish_criteria_pair_v2,
    )
    from scripts.verify_v3_gate_criteria import (
        verify_criteria_pair,
        verify_criteria_snapshot,
    )

    v1_root = tmp_path / "v1"
    v2_root = tmp_path / "v2"
    publish_criteria_pair(output_root=v1_root)
    publish_criteria_pair_v2(output_root=v2_root)
    assert verify_criteria_pair(v1_root)["status"] == "valid"
    assert verify_criteria_pair(v2_root)["status"] == "valid"

    v2_with_v1_source = verify_criteria_pair(v2_root, source_path=SOURCE)
    assert v2_with_v1_source["status"] == "invalid"
    assert "stable" in v2_with_v1_source["reason"].lower()

    tampered_source_dir = tmp_path / "tampered-source"
    tampered_source_dir.mkdir()
    tampered_source = tampered_source_dir / STABLE_SOURCE.name
    shutil.copy2(STABLE_SOURCE, tampered_source)
    tampered_source.write_bytes(tampered_source.read_bytes() + b"\n# tampered\n")
    source_tamper = verify_criteria_pair(v2_root, source_path=tampered_source)
    assert source_tamper["status"] == "invalid"
    assert "source" in source_tamper["reason"].lower()

    v1_with_stable_source = verify_criteria_pair(v1_root, source_path=STABLE_SOURCE)
    assert v1_with_stable_source["status"] == "invalid"
    assert "evaluator" in v1_with_stable_source["reason"].lower()

    clean_v2_root = tmp_path / "clean-v2"
    shutil.copytree(v2_root, clean_v2_root)
    v2_gate = next(v2_root.glob("*/manifest.json"))
    _rewrite_manifest(
        v2_gate,
        lambda manifest: manifest.update(
            {"schema_version": "prototype_gate_v2_criteria_snapshot.unknown"}
        ),
    )
    assert verify_criteria_snapshot(v2_gate.parent)["status"] == "invalid"
    assert verify_criteria_pair(v2_root)["status"] == "invalid"

    algorithm_root = tmp_path / "tampered-algorithm"
    shutil.copytree(clean_v2_root, algorithm_root)
    algorithm_gate = next(algorithm_root.glob("*/manifest.json"))
    _rewrite_manifest(
        algorithm_gate,
        lambda manifest: manifest["identity"].update(
            {"evaluator_algorithm_id": "b6_tampered_algorithm.v2"}
        ),
    )
    assert verify_criteria_snapshot(algorithm_gate.parent)["status"] == "invalid"

    sidecar_root = tmp_path / "tampered-sidecar"
    shutil.copytree(clean_v2_root, sidecar_root)
    sidecar_gate = next(sidecar_root.glob("*/manifest.json"))
    sidecar_gate.with_name("manifest.json.sha256").write_text(
        "0" * 64 + "  manifest.json\n",
        encoding="utf-8",
    )
    assert verify_criteria_snapshot(sidecar_gate.parent)["status"] == "invalid"


def test_v2_write_once_conflict_does_not_overwrite_existing_directory(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair_v2

    first = publish_criteria_pair_v2(output_root=tmp_path)
    gate_manifest = Path(first["gate"]["path"]) / "manifest.json"
    kill_manifest = Path(first["kill"]["path"]) / "manifest.json"
    original_kill = kill_manifest.read_bytes()
    _rewrite_manifest(
        gate_manifest,
        lambda manifest: manifest["identity"].update(
            {"evaluator_algorithm_id": "b6_other_algorithm.v2"}
        ),
    )

    with pytest.raises(ValueError, match="write-once conflict"):
        publish_criteria_pair_v2(output_root=tmp_path)
    assert kill_manifest.read_bytes() == original_kill
    assert json.loads(gate_manifest.read_text(encoding="utf-8"))["identity"][
        "evaluator_algorithm_id"
    ] == "b6_other_algorithm.v2"
