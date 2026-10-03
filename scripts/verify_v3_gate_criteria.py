"""Independent verifier for PrototypeGateV2 criteria snapshots."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from backend.services.prototype_gate_v2 import PrototypeGateV2
from backend.services.prototype_gate_criteria_surface import (
    CRITERIA_CONTRACT_VERSION,
    EVALUATOR_ALGORITHM_ID,
    EVALUATOR_REPO_RELATIVE_PATH,
    EVALUATOR_SURFACE_ID,
)


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = Path("backend/services/prototype_gate_v2.py")
SCHEMA = "prototype_gate_v2_criteria_snapshot.v1"
ENVELOPE_SCHEMA = "prototype_gate_v2_criteria_envelope.v1"
V2_SCHEMA = "prototype_gate_v2_criteria_snapshot.v2"
V2_ENVELOPE_SCHEMA = "prototype_gate_v2_criteria_envelope.v2"
V2_EVALUATOR_PATH = Path(EVALUATOR_REPO_RELATIVE_PATH)
_B4_FIELDS = ["stress_cost_result", "control_comparison", "base_cost_result", "benchmark_comparison"]
_FAILURE_PREDICATE = {
    "string_casefold_values": ["fail", "failed", "rejected", "insufficient"],
    "dict_status_casefold_values": ["fail", "failed", "rejected", "insufficient"],
    "dict_boolean_blocks": [
        {"field": "can_candidate", "when": False},
        {"field": "passed", "when": False},
    ],
    "other_values": "not_failed",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _source_facts(source_path: Path) -> dict:
    raw = Path(source_path).read_bytes()
    tree = ast.parse(raw.decode("utf-8"), filename=str(source_path))
    evaluator = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PrototypeGateV2"), None)
    if evaluator is None:
        raise ValueError("PrototypeGateV2 class missing from evaluator source")
    methods = {node.name for node in evaluator.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not {"evaluate", "_is_failed_result"}.issubset(methods):
        raise ValueError("PrototypeGateV2 evaluator methods missing")
    return {
        "repo_relative_path": EVALUATOR_PATH.as_posix(),
        "class_name": "PrototypeGateV2",
        "evaluate_method": "PrototypeGateV2.evaluate",
        "failure_predicate_method": "PrototypeGateV2._is_failed_result",
        "source_sha256": _sha_bytes(raw),
    }


def _source_inventory(source_facts: dict) -> dict:
    policies = {str(key): value for key, value in PrototypeGateV2.OOS_DRAW_POLICIES.items()}
    return {
        "evaluator_source": source_facts,
        "oos_draw_policies": {
            "repo_relative_path": source_facts["repo_relative_path"],
            "source_sha256": source_facts["source_sha256"],
            "identity": "PrototypeGateV2.OOS_DRAW_POLICIES",
            "status": "declared_but_not_enforced_by_evaluate",
            "effective_in_evaluate": False,
            "payload": policies,
        },
    }


def _expected_criteria(kind: str) -> dict:
    blocking_conditions = [
        {"id": "future_data_violation", "input": "report_payload.future_data_violation_count", "default": 0, "when": "value > 0", "outcome": "rejected"},
        {"id": "invalid_report_integrity", "input": "report.integrity_status", "when": "value != 'valid'", "outcome": "rejected"},
        {"id": "missing_or_failed_b4_result", "inputs": [f"report_payload.{field}" for field in _B4_FIELDS], "missing_when": [None, "not_available_from_b4_result"], "failed_when": "_is_failed_result(value)", "outcome": "rejected"},
        {"id": "invalid_data_quality", "input": "report_payload.data_quality_status", "when": "value in {'insufficient', 'invalid'}", "outcome": "rejected"},
        {"id": "beta_dominated", "input": "report_payload.beta_dominated", "when": "value is True", "outcome": "rejected"},
        {"id": "concentration_risk", "inputs": ["report_payload.single_symbol_concentration", "report_payload.single_month_concentration"], "when": "_is_failed_result(value)", "outcome": "rejected"},
    ]
    payload = {
        "criteria_kind": kind,
        "consumed_report_fields": [
            "gate_criteria_hash",
            "report_payload_json",
            "integrity_status",
            "report_id",
            "strategy_revision_id",
            "protocol_snapshot_id",
            "strategy_config_hash",
            "data_snapshot_hash",
            "oos_draw_index",
            "shared_oos_window_id",
            "multiple_comparison_flag",
        ],
        "consumed_payload_fields": [
            "future_data_violation_count",
            "stress_cost_result",
            "control_comparison",
            "base_cost_result",
            "benchmark_comparison",
            "data_quality_status",
            "beta_dominated",
            "single_symbol_concentration",
            "single_month_concentration",
        ],
        "input_guards": [
            {"id": "gate_criteria_hash_match", "input": "report.gate_criteria_hash", "when": "value != supplied_gate_criteria_hash", "outcome": "raise ValueError"},
            {"id": "report_payload_json_parse", "input": "report.report_payload_json", "when": "json.loads(value) fails", "outcome": "raise ValueError"},
        ],
        "blocking_conditions": blocking_conditions,
        "failure_predicate": _FAILURE_PREDICATE,
        "verdict_mapping": {"blocking_issues_nonempty": "rejected", "blocking_issues_empty": "candidate_for_prototype_passed", "maximum_verdict": "candidate_for_prototype_passed", "prototype_passed_emitted_by_evaluate": False},
        "side_effects": {"writes_lifecycle_state": False, "performs_promotion": False, "max_verdict": "candidate_for_prototype_passed"},
        "excluded_from_effective_rules": ["PrototypeGateV2.OOS_DRAW_POLICIES", "Sharpe thresholds", "trade-count thresholds", "drawdown thresholds", "sample results", "promotion decisions"],
    }
    if kind == "kill_criteria":
        payload["kill_semantics"] = {"only_current_evaluate_hard_blocks": True, "rejected_when_any_blocking_condition": True}
    return payload


def _invalid(reason: str) -> dict:
    return {"status": "invalid", "reason": reason}


def _verify_manifest(snapshot_dir: Path, *, source_path: Path | None = None) -> tuple[dict, dict]:
    manifest_path = Path(snapshot_dir) / "manifest.json"
    sidecar = Path(snapshot_dir) / "manifest.json.sha256"
    if not manifest_path.exists() or not sidecar.exists():
        raise ValueError("manifest or sidecar missing")
    manifest_hash = _sha(manifest_path)
    if sidecar.read_text(encoding="utf-8").split()[0] != manifest_hash:
        raise ValueError("manifest sidecar mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = dict(manifest)
    declared_manifest_hash = content.pop("manifest_content_hash", None)
    content["manifest_content_hash"] = ""
    if declared_manifest_hash != _sha_bytes(_canonical(content)):
        raise ValueError("manifest content hash mismatch")
    kind = manifest.get("artifact_type")
    if manifest.get("schema_version") != SCHEMA or kind not in {"gate_criteria", "kill_criteria"}:
        raise ValueError("criteria schema or artifact type mismatch")
    source_path = Path(source_path) if source_path is not None else ROOT / EVALUATOR_PATH
    facts = _source_facts(source_path)
    if manifest.get("evaluator") != facts:
        raise ValueError("evaluator source binding mismatch")
    inventory = _source_inventory(facts)
    if manifest.get("source_inventory") != inventory:
        raise ValueError("source inventory mismatch")
    criteria = manifest.get("criteria")
    if criteria != _expected_criteria(kind):
        raise ValueError("effective criteria payload mismatch")
    criteria_hash = _sha_bytes(_canonical(criteria))
    if manifest.get("criteria_content_hash") != criteria_hash:
        raise ValueError("criteria content hash mismatch")
    expected_id = f"prototype_gate_v2_{'gate' if kind == 'gate_criteria' else 'kill'}_{criteria_hash[:16]}"
    if manifest.get("snapshot_id") != expected_id or manifest.get("artifact_id") != expected_id:
        raise ValueError("criteria artifact identity mismatch")
    if manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("criteria publication status mismatch")
    if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False:
        raise ValueError("criteria authorization disclosure mismatch")
    return manifest, {"manifest_sha256": manifest_hash, "criteria_content_hash": criteria_hash}


def _verify_criteria_snapshot_v1(snapshot_dir: Path, *, source_path: Path | None = None) -> dict:
    try:
        manifest, hashes = _verify_manifest(Path(snapshot_dir), source_path=source_path)
        envelope = manifest.get("envelope", {})
        if envelope.get("schema_version") != ENVELOPE_SCHEMA or not envelope.get("envelope_hash"):
            raise ValueError("criteria envelope missing")
        return {
            "status": "valid",
            "artifact_type": manifest["artifact_type"],
            "snapshot_id": manifest["snapshot_id"],
            "manifest_sha256": hashes["manifest_sha256"],
            "criteria_content_hash": hashes["criteria_content_hash"],
            "envelope_hash": envelope["envelope_hash"],
            "criteria_json": json.dumps(manifest["criteria"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        }
    except (OSError, UnicodeDecodeError, SyntaxError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _invalid(str(error))


def _verify_criteria_pair_v1(output_root: Path, *, source_path: Path | None = None) -> dict:
    try:
        root = Path(output_root)
        dirs = [path for path in root.iterdir() if path.is_dir()]
        manifests = {}
        results = {}
        for path in dirs:
            result = _verify_criteria_snapshot_v1(path, source_path=source_path)
            if result.get("status") != "valid":
                raise ValueError(result.get("reason", "criteria snapshot invalid"))
            manifests[result["artifact_type"]] = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            results[result["artifact_type"]] = result
        if set(manifests) != {"gate_criteria", "kill_criteria"}:
            raise ValueError("gate and kill criteria snapshots are both required")
        gate = manifests["gate_criteria"]
        kill = manifests["kill_criteria"]
        envelope_base = {
            "schema_version": ENVELOPE_SCHEMA,
            "gate_snapshot_id": gate["snapshot_id"],
            "gate_content_hash": gate["criteria_content_hash"],
            "kill_snapshot_id": kill["snapshot_id"],
            "kill_content_hash": kill["criteria_content_hash"],
        }
        envelope_hash = _sha_bytes(_canonical(envelope_base))
        for manifest in (gate, kill):
            envelope = manifest.get("envelope", {})
            if envelope != {**envelope_base, "envelope_hash": envelope_hash}:
                raise ValueError("criteria envelope mismatch")
        return {
            "status": "valid",
            "gate": results["gate_criteria"],
            "kill": results["kill_criteria"],
            "envelope_hash": envelope_hash,
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _invalid(str(error))


def _source_facts_v2(source_path: Path) -> dict:
    source_path = Path(source_path)
    if source_path.name != V2_EVALUATOR_PATH.name:
        raise ValueError("v2 evaluator source must be the stable criteria surface")
    raw = source_path.read_bytes()
    tree = ast.parse(raw.decode("utf-8"), filename=str(source_path))
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not {"evaluate_effective_criteria", "is_failed_result"}.issubset(functions):
        raise ValueError("stable criteria evaluator functions missing")
    return {
        "repo_relative_path": EVALUATOR_REPO_RELATIVE_PATH,
        "module": "backend.services.prototype_gate_criteria_surface",
        "evaluate_entrypoint": "evaluate_effective_criteria",
        "failure_predicate": "is_failed_result",
        "source_sha256": _sha_bytes(raw),
    }


def _source_inventory_v2(source_facts: dict) -> dict:
    return {
        "evaluator_source": source_facts,
        "evaluator_algorithm": {
            "surface_id": EVALUATOR_SURFACE_ID,
            "algorithm_id": EVALUATOR_ALGORITHM_ID,
            "contract_version": CRITERIA_CONTRACT_VERSION,
        },
    }


def _verify_manifest_v2(
    snapshot_dir: Path,
    *,
    source_path: Path | None = None,
) -> tuple[dict, dict]:
    manifest_path = Path(snapshot_dir) / "manifest.json"
    sidecar = Path(snapshot_dir) / "manifest.json.sha256"
    if not manifest_path.exists() or not sidecar.exists():
        raise ValueError("manifest or sidecar missing")
    manifest_hash = _sha(manifest_path)
    if sidecar.read_text(encoding="utf-8").split()[0] != manifest_hash:
        raise ValueError("manifest sidecar mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version",
        "criteria_contract_version",
        "status",
        "artifact_type",
        "snapshot_id",
        "artifact_id",
        "identity",
        "criteria",
        "criteria_content_hash",
        "evaluator",
        "evaluator_algorithm",
        "source_inventory",
        "envelope",
        "not_authorized_for_b6_oos_gate_promotion_signal",
        "frozen",
        "manifest_content_hash",
    }
    if set(manifest) != expected_keys:
        raise ValueError("v2 manifest fields mismatch")
    content = dict(manifest)
    declared_manifest_hash = content.pop("manifest_content_hash")
    content["manifest_content_hash"] = ""
    if declared_manifest_hash != _sha_bytes(_canonical(content)):
        raise ValueError("manifest content hash mismatch")
    kind = manifest.get("artifact_type")
    if manifest.get("schema_version") != V2_SCHEMA or kind not in {"gate_criteria", "kill_criteria"}:
        raise ValueError("v2 criteria schema or artifact type mismatch")
    if manifest.get("criteria_contract_version") != CRITERIA_CONTRACT_VERSION:
        raise ValueError("v2 criteria contract mismatch")
    source_path = Path(source_path) if source_path is not None else ROOT / V2_EVALUATOR_PATH
    facts = _source_facts_v2(source_path)
    inventory = _source_inventory_v2(facts)
    if manifest.get("evaluator") != facts:
        raise ValueError("v2 evaluator source binding mismatch")
    if manifest.get("evaluator_algorithm") != inventory["evaluator_algorithm"]:
        raise ValueError("v2 evaluator algorithm binding mismatch")
    if manifest.get("source_inventory") != inventory:
        raise ValueError("v2 source inventory mismatch")
    criteria = manifest.get("criteria")
    if criteria != _expected_criteria(kind):
        raise ValueError("v2 effective criteria payload mismatch")
    criteria_hash = _sha_bytes(_canonical(criteria))
    if manifest.get("criteria_content_hash") != criteria_hash:
        raise ValueError("v2 criteria content hash mismatch")
    identity = manifest.get("identity")
    expected_identity = {
        "schema_version": V2_SCHEMA,
        "criteria_contract_version": CRITERIA_CONTRACT_VERSION,
        "artifact_type": kind,
        "criteria_content_hash": criteria_hash,
        "evaluator_surface_id": EVALUATOR_SURFACE_ID,
        "evaluator_algorithm_id": EVALUATOR_ALGORITHM_ID,
        "evaluator_source_sha256": facts["source_sha256"],
    }
    if identity != expected_identity:
        raise ValueError("v2 criteria identity mismatch")
    expected_id = f"prototype_gate_v2_{'gate' if kind == 'gate_criteria' else 'kill'}_v2_{_sha_bytes(_canonical(identity))[:16]}"
    if manifest.get("snapshot_id") != expected_id or manifest.get("artifact_id") != expected_id:
        raise ValueError("v2 criteria artifact identity mismatch")
    envelope = manifest.get("envelope")
    envelope_base = {
        "schema_version": V2_ENVELOPE_SCHEMA,
        "criteria_contract_version": CRITERIA_CONTRACT_VERSION,
        "gate_snapshot_id": envelope.get("gate_snapshot_id") if isinstance(envelope, dict) else None,
        "gate_content_hash": envelope.get("gate_content_hash") if isinstance(envelope, dict) else None,
        "kill_snapshot_id": envelope.get("kill_snapshot_id") if isinstance(envelope, dict) else None,
        "kill_content_hash": envelope.get("kill_content_hash") if isinstance(envelope, dict) else None,
    }
    if not isinstance(envelope, dict) or envelope != {
        **envelope_base,
        "envelope_hash": _sha_bytes(_canonical(envelope_base)),
    }:
        raise ValueError("v2 criteria envelope mismatch")
    if manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("v2 criteria publication status mismatch")
    if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False:
        raise ValueError("v2 criteria authorization disclosure mismatch")
    return manifest, {"manifest_sha256": manifest_hash, "criteria_content_hash": criteria_hash}


def verify_criteria_snapshot(snapshot_dir: Path, *, source_path: Path | None = None) -> dict:
    try:
        manifest_path = Path(snapshot_dir) / "manifest.json"
        schema = json.loads(manifest_path.read_text(encoding="utf-8")).get("schema_version")
        if schema == V2_SCHEMA:
            manifest, hashes = _verify_manifest_v2(Path(snapshot_dir), source_path=source_path)
        elif schema == SCHEMA:
            manifest, hashes = _verify_manifest(Path(snapshot_dir), source_path=source_path)
        else:
            raise ValueError("unknown criteria schema")
        envelope = manifest.get("envelope", {})
        expected_envelope_schema = V2_ENVELOPE_SCHEMA if schema == V2_SCHEMA else ENVELOPE_SCHEMA
        if envelope.get("schema_version") != expected_envelope_schema or not envelope.get("envelope_hash"):
            raise ValueError("criteria envelope missing")
        return {
            "status": "valid",
            "artifact_type": manifest["artifact_type"],
            "snapshot_id": manifest["snapshot_id"],
            "manifest_sha256": hashes["manifest_sha256"],
            "criteria_content_hash": hashes["criteria_content_hash"],
            "envelope_hash": envelope["envelope_hash"],
            "criteria_json": json.dumps(manifest["criteria"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        }
    except (OSError, UnicodeDecodeError, SyntaxError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _invalid(str(error))


def verify_criteria_pair(output_root: Path, *, source_path: Path | None = None) -> dict:
    try:
        root = Path(output_root)
        candidates = []
        for path in root.iterdir():
            if not path.is_dir():
                continue
            manifest_path = path / "manifest.json"
            if not manifest_path.exists():
                continue
            candidates.append((path, json.loads(manifest_path.read_text(encoding="utf-8")).get("schema_version")))
        unknown = [
            schema
            for _, schema in candidates
            if schema not in {SCHEMA, V2_SCHEMA}
        ]
        if unknown:
            raise ValueError("unknown criteria schema")
        v2_paths = [path for path, schema in candidates if schema == V2_SCHEMA]
        v1_paths = [path for path, schema in candidates if schema == SCHEMA]
        selected = v2_paths if v2_paths else v1_paths
        if len(selected) != 2:
            raise ValueError("exactly one gate and kill criteria pair is required")
        manifests = {}
        results = {}
        selected_schema = V2_SCHEMA if v2_paths else SCHEMA
        for path in selected:
            result = verify_criteria_snapshot(path, source_path=source_path)
            if result.get("status") != "valid":
                raise ValueError(result.get("reason", "criteria snapshot invalid"))
            artifact_type = result["artifact_type"]
            if artifact_type in manifests:
                raise ValueError("duplicate criteria artifact type")
            manifests[artifact_type] = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            results[artifact_type] = result
        if set(manifests) != {"gate_criteria", "kill_criteria"}:
            raise ValueError("gate and kill criteria snapshots are both required")
        gate = manifests["gate_criteria"]
        kill = manifests["kill_criteria"]
        envelope_base = {
            "schema_version": V2_ENVELOPE_SCHEMA if selected_schema == V2_SCHEMA else ENVELOPE_SCHEMA,
            **({"criteria_contract_version": CRITERIA_CONTRACT_VERSION} if selected_schema == V2_SCHEMA else {}),
            "gate_snapshot_id": gate["snapshot_id"],
            "gate_content_hash": gate["criteria_content_hash"],
            "kill_snapshot_id": kill["snapshot_id"],
            "kill_content_hash": kill["criteria_content_hash"],
        }
        envelope_hash = _sha_bytes(_canonical(envelope_base))
        for manifest in (gate, kill):
            if manifest.get("envelope") != {**envelope_base, "envelope_hash": envelope_hash}:
                raise ValueError("criteria envelope mismatch")
        return {
            "status": "valid",
            "gate": results["gate_criteria"],
            "kill": results["kill_criteria"],
            "envelope_hash": envelope_hash,
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _invalid(str(error))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_criteria_pair(args.output_root), sort_keys=True))
