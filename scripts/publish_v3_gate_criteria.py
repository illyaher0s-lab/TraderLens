"""Publish immutable criteria snapshots derived from PrototypeGateV2.evaluate."""
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
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/prototype_gate_v2_criteria"
SCHEMA = "prototype_gate_v2_criteria_snapshot.v1"
ENVELOPE_SCHEMA = "prototype_gate_v2_criteria_envelope.v1"
V2_SCHEMA = "prototype_gate_v2_criteria_snapshot.v2"
V2_ENVELOPE_SCHEMA = "prototype_gate_v2_criteria_envelope.v2"
V2_EVALUATOR_PATH = Path(EVALUATOR_REPO_RELATIVE_PATH)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _source_facts(source_path: Path) -> dict:
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    tree = ast.parse(raw.decode("utf-8"), filename=str(source_path))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    evaluator = classes.get("PrototypeGateV2")
    if evaluator is None:
        raise ValueError("PrototypeGateV2 class missing from evaluator source")
    methods = {node.name for node in evaluator.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    required = {"evaluate", "_is_failed_result"}
    if not required.issubset(methods):
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
    required = {"evaluate_effective_criteria", "is_failed_result"}
    if not required.issubset(functions):
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


_FAILURE_PREDICATE = {
    "string_casefold_values": ["fail", "failed", "rejected", "insufficient"],
    "dict_status_casefold_values": ["fail", "failed", "rejected", "insufficient"],
    "dict_boolean_blocks": [
        {"field": "can_candidate", "when": False},
        {"field": "passed", "when": False},
    ],
    "other_values": "not_failed",
}

_B4_FIELDS = ["stress_cost_result", "control_comparison", "base_cost_result", "benchmark_comparison"]


def _criteria_payload(kind: str) -> dict:
    blocking_conditions = [
        {
            "id": "future_data_violation",
            "input": "report_payload.future_data_violation_count",
            "default": 0,
            "when": "value > 0",
            "outcome": "rejected",
        },
        {
            "id": "invalid_report_integrity",
            "input": "report.integrity_status",
            "when": "value != 'valid'",
            "outcome": "rejected",
        },
        {
            "id": "missing_or_failed_b4_result",
            "inputs": [f"report_payload.{field}" for field in _B4_FIELDS],
            "missing_when": [None, "not_available_from_b4_result"],
            "failed_when": "_is_failed_result(value)",
            "outcome": "rejected",
        },
        {
            "id": "invalid_data_quality",
            "input": "report_payload.data_quality_status",
            "when": "value in {'insufficient', 'invalid'}",
            "outcome": "rejected",
        },
        {
            "id": "beta_dominated",
            "input": "report_payload.beta_dominated",
            "when": "value is True",
            "outcome": "rejected",
        },
        {
            "id": "concentration_risk",
            "inputs": [
                "report_payload.single_symbol_concentration",
                "report_payload.single_month_concentration",
            ],
            "when": "_is_failed_result(value)",
            "outcome": "rejected",
        },
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
            {
                "id": "gate_criteria_hash_match",
                "input": "report.gate_criteria_hash",
                "when": "value != supplied_gate_criteria_hash",
                "outcome": "raise ValueError",
            },
            {
                "id": "report_payload_json_parse",
                "input": "report.report_payload_json",
                "when": "json.loads(value) fails",
                "outcome": "raise ValueError",
            },
        ],
        "blocking_conditions": blocking_conditions,
        "failure_predicate": _FAILURE_PREDICATE,
        "verdict_mapping": {
            "blocking_issues_nonempty": "rejected",
            "blocking_issues_empty": "candidate_for_prototype_passed",
            "maximum_verdict": "candidate_for_prototype_passed",
            "prototype_passed_emitted_by_evaluate": False,
        },
        "side_effects": {
            "writes_lifecycle_state": False,
            "performs_promotion": False,
            "max_verdict": "candidate_for_prototype_passed",
        },
        "excluded_from_effective_rules": [
            "PrototypeGateV2.OOS_DRAW_POLICIES",
            "Sharpe thresholds",
            "trade-count thresholds",
            "drawdown thresholds",
            "sample results",
            "promotion decisions",
        ],
    }
    if kind == "kill_criteria":
        payload["kill_semantics"] = {
            "only_current_evaluate_hard_blocks": True,
            "rejected_when_any_blocking_condition": True,
        }
    return payload


def _manifest(
    *,
    kind: str,
    criteria: dict,
    source_facts: dict,
    source_inventory: dict,
    snapshot_id: str,
    envelope: dict,
) -> dict:
    criteria_hash = _sha_bytes(_canonical(criteria))
    manifest = {
        "schema_version": SCHEMA,
        "status": "published",
        "artifact_type": kind,
        "snapshot_id": snapshot_id,
        "artifact_id": snapshot_id,
        "criteria": criteria,
        "criteria_content_hash": criteria_hash,
        "evaluator": source_facts,
        "source_inventory": source_inventory,
        "envelope": envelope,
        "not_authorized_for_b6_oos_gate_promotion_signal": False,
        "frozen": True,
    }
    manifest["manifest_content_hash"] = ""
    manifest["manifest_content_hash"] = _sha_bytes(_canonical(manifest))
    return manifest


def _write_once(target: Path, manifest: dict) -> bool:
    target = Path(target)
    raw = _canonical(manifest)
    if target.exists():
        manifest_path = target / "manifest.json"
        sidecar_path = target / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            raise ValueError("criteria write-once conflict: incomplete existing artifact")
        if manifest_path.read_bytes() != raw or sidecar_path.read_text(encoding="utf-8").split()[0] != _sha_bytes(raw):
            raise ValueError("criteria write-once conflict: content differs")
        return True
    target.mkdir(parents=True, exist_ok=False)
    manifest_path = target / "manifest.json"
    manifest_path.write_bytes(raw)
    (target / "manifest.json.sha256").write_text(_sha_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    return False


def publish_criteria_pair(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    source_path: Path = ROOT / EVALUATOR_PATH,
) -> dict:
    source_facts = _source_facts(Path(source_path))
    inventory = _source_inventory(source_facts)
    gate_criteria = _criteria_payload("gate_criteria")
    kill_criteria = _criteria_payload("kill_criteria")
    gate_content_hash = _sha_bytes(_canonical(gate_criteria))
    kill_content_hash = _sha_bytes(_canonical(kill_criteria))
    gate_id = f"prototype_gate_v2_gate_{gate_content_hash[:16]}"
    kill_id = f"prototype_gate_v2_kill_{kill_content_hash[:16]}"
    envelope_base = {
        "schema_version": ENVELOPE_SCHEMA,
        "gate_snapshot_id": gate_id,
        "gate_content_hash": gate_content_hash,
        "kill_snapshot_id": kill_id,
        "kill_content_hash": kill_content_hash,
    }
    envelope = {**envelope_base, "envelope_hash": _sha_bytes(_canonical(envelope_base))}
    gate_manifest = _manifest(
        kind="gate_criteria",
        criteria=gate_criteria,
        source_facts=source_facts,
        source_inventory=inventory,
        snapshot_id=gate_id,
        envelope=envelope,
    )
    kill_manifest = _manifest(
        kind="kill_criteria",
        criteria=kill_criteria,
        source_facts=source_facts,
        source_inventory=inventory,
        snapshot_id=kill_id,
        envelope=envelope,
    )
    output_root = Path(output_root)
    preexisting = all(
        (output_root / snapshot_id / "manifest.json").exists()
        and (output_root / snapshot_id / "manifest.json.sha256").exists()
        for snapshot_id in (gate_id, kill_id)
    )
    _write_once(output_root / gate_id, gate_manifest)
    _write_once(output_root / kill_id, kill_manifest)
    return {
        "status": "already_published" if preexisting else "published",
        "gate": {
            "snapshot_id": gate_id,
            "path": str(output_root / gate_id),
            "manifest_sha256": _sha(output_root / gate_id / "manifest.json"),
            "criteria_content_hash": gate_content_hash,
        },
        "kill": {
            "snapshot_id": kill_id,
            "path": str(output_root / kill_id),
            "manifest_sha256": _sha(output_root / kill_id / "manifest.json"),
            "criteria_content_hash": kill_content_hash,
        },
        "envelope_hash": envelope["envelope_hash"],
    }


def _manifest_v2(
    *,
    kind: str,
    criteria: dict,
    source_facts: dict,
    source_inventory: dict,
    identity: dict,
    snapshot_id: str,
    envelope: dict,
) -> dict:
    manifest = {
        "schema_version": V2_SCHEMA,
        "criteria_contract_version": CRITERIA_CONTRACT_VERSION,
        "status": "published",
        "artifact_type": kind,
        "snapshot_id": snapshot_id,
        "artifact_id": snapshot_id,
        "identity": identity,
        "criteria": criteria,
        "criteria_content_hash": identity["criteria_content_hash"],
        "evaluator": source_facts,
        "evaluator_algorithm": source_inventory["evaluator_algorithm"],
        "source_inventory": source_inventory,
        "envelope": envelope,
        "not_authorized_for_b6_oos_gate_promotion_signal": False,
        "frozen": True,
        "manifest_content_hash": "",
    }
    manifest["manifest_content_hash"] = _sha_bytes(_canonical(manifest))
    return manifest


def publish_criteria_pair_v2(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    source_path: Path = ROOT / V2_EVALUATOR_PATH,
) -> dict:
    """Publish the immutable v2 criteria pair; v1 remains a separate history path."""
    source_facts = _source_facts_v2(Path(source_path))
    inventory = _source_inventory_v2(source_facts)
    gate_criteria = _criteria_payload("gate_criteria")
    kill_criteria = _criteria_payload("kill_criteria")
    gate_content_hash = _sha_bytes(_canonical(gate_criteria))
    kill_content_hash = _sha_bytes(_canonical(kill_criteria))

    def identity(kind: str, criteria_hash: str) -> dict:
        return {
            "schema_version": V2_SCHEMA,
            "criteria_contract_version": CRITERIA_CONTRACT_VERSION,
            "artifact_type": kind,
            "criteria_content_hash": criteria_hash,
            "evaluator_surface_id": EVALUATOR_SURFACE_ID,
            "evaluator_algorithm_id": EVALUATOR_ALGORITHM_ID,
            "evaluator_source_sha256": source_facts["source_sha256"],
        }

    gate_identity = identity("gate_criteria", gate_content_hash)
    kill_identity = identity("kill_criteria", kill_content_hash)
    gate_id = f"prototype_gate_v2_gate_v2_{_sha_bytes(_canonical(gate_identity))[:16]}"
    kill_id = f"prototype_gate_v2_kill_v2_{_sha_bytes(_canonical(kill_identity))[:16]}"
    envelope_base = {
        "schema_version": V2_ENVELOPE_SCHEMA,
        "criteria_contract_version": CRITERIA_CONTRACT_VERSION,
        "gate_snapshot_id": gate_id,
        "gate_content_hash": gate_content_hash,
        "kill_snapshot_id": kill_id,
        "kill_content_hash": kill_content_hash,
    }
    envelope = {**envelope_base, "envelope_hash": _sha_bytes(_canonical(envelope_base))}
    gate_manifest = _manifest_v2(
        kind="gate_criteria",
        criteria=gate_criteria,
        source_facts=source_facts,
        source_inventory=inventory,
        identity=gate_identity,
        snapshot_id=gate_id,
        envelope=envelope,
    )
    kill_manifest = _manifest_v2(
        kind="kill_criteria",
        criteria=kill_criteria,
        source_facts=source_facts,
        source_inventory=inventory,
        identity=kill_identity,
        snapshot_id=kill_id,
        envelope=envelope,
    )
    output_root = Path(output_root)
    preexisting = all(
        (output_root / snapshot_id / "manifest.json").exists()
        and (output_root / snapshot_id / "manifest.json.sha256").exists()
        for snapshot_id in (gate_id, kill_id)
    )
    _write_once(output_root / gate_id, gate_manifest)
    _write_once(output_root / kill_id, kill_manifest)
    return {
        "status": "already_published" if preexisting else "published",
        "gate": {
            "snapshot_id": gate_id,
            "path": str(output_root / gate_id),
            "manifest_sha256": _sha(output_root / gate_id / "manifest.json"),
            "criteria_content_hash": gate_content_hash,
        },
        "kill": {
            "snapshot_id": kill_id,
            "path": str(output_root / kill_id),
            "manifest_sha256": _sha(output_root / kill_id / "manifest.json"),
            "criteria_content_hash": kill_content_hash,
        },
        "envelope_hash": envelope["envelope_hash"],
    }


if __name__ == "__main__":
    print(json.dumps(publish_criteria_pair_v2(), sort_keys=True))
