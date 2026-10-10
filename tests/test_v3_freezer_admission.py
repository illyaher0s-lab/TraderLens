from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.research_protocol_freezer import ResearchProtocolFreezer
from backend.services.strategy_template_library import convert_to_frozen_contract, get_template_by_id
from contracts.strategy import FrozenCriteriaReference, ProtocolFreezePreflightResult
from scripts.build_v3_availability_bounded_qualification_successor import build_successor
from scripts.publish_v3_formal_snapshot import (
    B3_MANIFEST,
    COVERAGE_DIR,
    EVIDENCE_DIR,
    LIFECYCLE_MANIFEST,
    MEMBERSHIP_DIR,
    SCOPE_DIR,
    TEMPLATE,
    publish_formal_snapshot,
)
from scripts.run_v3_task4_once import _build_provenance_records, _verify_membership_artifact
from scripts.verify_v3_gate_criteria import verify_criteria_pair


ROOT = Path(__file__).resolve().parents[1]


def _real_v3_freezer_args(db: StrategyDB) -> tuple[dict, dict, dict, dict]:
    criteria = verify_criteria_pair(ROOT / "data/pit/prototype_gate_v2_criteria")
    membership, membership_hash, records_hash = _verify_membership_artifact(ROOT)
    b3 = json.loads(B3_MANIFEST.read_text(encoding="utf-8"))
    template, universe, draft, lifecycle = _build_provenance_records(
        b3_manifest=b3,
        b3_manifest_hash=__import__("hashlib").sha256(B3_MANIFEST.read_bytes()).hexdigest(),
        membership_manifest=membership,
        membership_manifest_hash=membership_hash,
        membership_records_hash=records_hash,
    )
    scope_path = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    return (
        {
            "successor_dir": ROOT / "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4",
            "predecessor_manifest_path": B3_MANIFEST,
            "coverage_manifest_path": COVERAGE_DIR / "manifest.json",
            "coverage_sidecar_path": COVERAGE_DIR / "manifest.json.sha256",
            "coverage_by_code_path": COVERAGE_DIR / "coverage_by_code.parquet",
            "coverage_by_date_path": COVERAGE_DIR / "coverage_by_date.parquet",
            "unavailable_path": COVERAGE_DIR / "unavailable_security_dates.parquet",
            "formal_snapshot_dir": ROOT / "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a",
            "approved_template": template,
            "gate_reference": FrozenCriteriaReference(
                snapshot_id=criteria["gate"]["snapshot_id"],
                criteria_json=criteria["gate"]["criteria_json"],
                declared_content_hash=criteria["gate"]["criteria_content_hash"],
            ),
            "kill_reference": FrozenCriteriaReference(
                snapshot_id=criteria["kill"]["snapshot_id"],
                criteria_json=criteria["kill"]["criteria_json"],
                declared_content_hash=criteria["kill"]["criteria_content_hash"],
            ),
            "ledger": OOSBudgetLedger(db),
            "strategy_draft": draft,
            "universe": universe,
            "oos_window_rule_id": scope["split"]["rule_id"],
            "oos_window_start": datetime.strptime(scope["split"]["oos_start"], "%Y%m%d").date(),
            "oos_window_end": datetime.strptime(scope["split"]["oos_end"], "%Y%m%d").date(),
            "frozen_by": template.authorized_by,
            "backtest_start": datetime.strptime(scope["execution"]["start"], "%Y%m%d").date(),
            "scope_freeze_path": scope_path,
            "gate_criteria_hash": criteria["envelope_hash"],
            "criteria_envelope_schema": "prototype_gate_v2_criteria_envelope.v2",
        },
        {"template": template, "universe": universe, "draft": draft, "lifecycle": lifecycle},
        criteria,
        scope,
    )


class TestV3FreezerAdmission(unittest.TestCase):
    def test_v3_full_gate_continuation_reaches_protocol(self):
        criteria = verify_criteria_pair(ROOT / "data/pit/prototype_gate_v2_criteria")
        gate = criteria["gate"]
        kill = criteria["kill"]
        gate_ref = FrozenCriteriaReference(
            snapshot_id=gate["snapshot_id"],
            criteria_json=gate["criteria_json"],
            declared_content_hash=gate["criteria_content_hash"],
        )
        kill_ref = FrozenCriteriaReference(
            snapshot_id=kill["snapshot_id"],
            criteria_json=kill["criteria_json"],
            declared_content_hash=kill["criteria_content_hash"],
        )
        membership, membership_hash, records_hash = _verify_membership_artifact(ROOT)
        b3 = json.loads(B3_MANIFEST.read_text(encoding="utf-8"))
        frozen_template, universe, draft, _ = _build_provenance_records(
            b3_manifest=b3,
            b3_manifest_hash=__import__("hashlib").sha256(B3_MANIFEST.read_bytes()).hexdigest(),
            membership_manifest=membership,
            membership_manifest_hash=membership_hash,
            membership_records_hash=records_hash,
        )
        scope = json.loads((ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            db = StrategyDB(str(Path(temp) / "ledger.db"))
            try:
                result = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(
                    successor_dir=ROOT / "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4",
                    predecessor_manifest_path=B3_MANIFEST,
                    coverage_manifest_path=COVERAGE_DIR / "manifest.json",
                    coverage_sidecar_path=COVERAGE_DIR / "manifest.json.sha256",
                    coverage_by_code_path=COVERAGE_DIR / "coverage_by_code.parquet",
                    coverage_by_date_path=COVERAGE_DIR / "coverage_by_date.parquet",
                    unavailable_path=COVERAGE_DIR / "unavailable_security_dates.parquet",
                    formal_snapshot_dir=ROOT / "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a",
                    approved_template=frozen_template,
                    gate_reference=gate_ref,
                    kill_reference=kill_ref,
                    ledger=OOSBudgetLedger(db),
                    strategy_draft=draft,
                    universe=universe,
                    oos_window_rule_id=scope["split"]["rule_id"],
                    oos_window_start=date.fromisoformat(scope["split"]["oos_start"]),
                    oos_window_end=date.fromisoformat(scope["split"]["oos_end"]),
                    frozen_by=frozen_template.authorized_by,
                    backtest_start=date.fromisoformat(scope["execution"]["start"]),
                    scope_freeze_path=ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json",
                    gate_criteria_hash=criteria["envelope_hash"],
                    criteria_envelope_schema="prototype_gate_v2_criteria_envelope.v2",
                )
            finally:
                db.close()
        self.assertNotIsInstance(result, ProtocolFreezePreflightResult)

    def test_v3_memory_ledger_is_not_a_durable_owner(self):
        db = StrategyDB(":memory:")
        try:
            args, _, _, _ = _real_v3_freezer_args(db)
            result = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(**args)
        finally:
            db.close()
        self.assertIsInstance(result, ProtocolFreezePreflightResult)
        self.assertEqual(result.reason_code, "ledger_owner_unavailable")

    def test_v3_criteria_hash_tamper_and_scope_mismatch_fail_loud(self):
        with tempfile.TemporaryDirectory() as temp:
            db = StrategyDB(str(Path(temp) / "ledger.db"))
            try:
                args, _, _, _ = _real_v3_freezer_args(db)
                args["gate_reference"] = args["gate_reference"].model_copy(
                    update={"declared_content_hash": "0" * 64}
                )
                tampered = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(**args)
                self.assertIsInstance(tampered, ProtocolFreezePreflightResult)
                self.assertEqual(tampered.reason_code, "criteria_content_hash_mismatch")

                args, _, _, _ = _real_v3_freezer_args(db)
                args["oos_window_start"] = date(2026, 3, 19)
                invalid_scope = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(**args)
                self.assertIsInstance(invalid_scope, ProtocolFreezePreflightResult)
                self.assertEqual(invalid_scope.reason_code, "split_or_time_consistency_invalid")
            finally:
                db.close()

    def test_v3_protocol_persistence_is_exact_and_cross_connection_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "ledger.db"
            db = StrategyDB(str(db_path))
            try:
                args, records, _, _ = _real_v3_freezer_args(db)
                db.materialize_strategy_provenance(
                    records["template"], records["universe"], records["draft"], records["lifecycle"]
                )
                protocol = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(**args)
                self.assertNotIsInstance(protocol, ProtocolFreezePreflightResult)
                self.assertEqual(db.store_protocol_snapshot_exact(protocol), "created")
                self.assertEqual(db.store_protocol_snapshot_exact(protocol), "reused")
                other = StrategyDB(str(db_path))
                try:
                    self.assertEqual(other.get_protocol_snapshot(protocol.protocol_snapshot_id), protocol)
                finally:
                    other.close()
                with self.assertRaisesRegex(ValueError, "protocol snapshot conflict"):
                    db.store_protocol_snapshot_exact(protocol.model_copy(update={"frozen_by": "tampered"}))
            finally:
                db.close()

    def test_v3_v2_criteria_freezer_candidate_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            db = StrategyDB(str(Path(temp) / "ledger.db"))
            try:
                args, _, _, _ = _real_v3_freezer_args(db)
                result = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(**args)
                self.assertNotIsInstance(result, ProtocolFreezePreflightResult)
                self.assertEqual(
                    result.protocol_snapshot_id,
                    "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
                )
                payload_sha = __import__("hashlib").sha256(
                    result.model_dump_json().encode("utf-8")
                ).hexdigest()
                self.assertEqual(
                    payload_sha,
                    "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3",
                )
                self.assertEqual(result.frozen_at, datetime.combine(result.oos_window_end, datetime.min.time()))
                self.assertEqual(
                    db.conn.execute("SELECT COUNT(*) FROM research_protocol_snapshots").fetchone()[0],
                    0,
                )
            finally:
                db.close()

    def test_v3_gate_1_to_4_reaches_criteria_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = publish_formal_snapshot(output_root=root / "snapshots")
            successor = build_successor(
                formal_snapshot_dir=Path(snapshot["path"]),
                output_root=root / "successors",
            )
            membership, membership_hash, records_hash = _verify_membership_artifact(ROOT)
            b3 = json.loads(B3_MANIFEST.read_text(encoding="utf-8"))
            frozen_template, universe, draft, _ = _build_provenance_records(
                b3_manifest=b3,
                b3_manifest_hash=__import__("hashlib").sha256(B3_MANIFEST.read_bytes()).hexdigest(),
                membership_manifest=membership,
                membership_manifest_hash=membership_hash,
                membership_records_hash=records_hash,
            )
            db = StrategyDB(str(root / "ledger.db"))
            try:
                ledger = OOSBudgetLedger(db)
                ledger.get_ledger_state(draft.theme_id, draft.hypothesis_source_snapshot_id)
                result = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(
                    successor_dir=Path(successor["path"]),
                    predecessor_manifest_path=B3_MANIFEST,
                    coverage_manifest_path=COVERAGE_DIR / "manifest.json",
                    coverage_sidecar_path=COVERAGE_DIR / "manifest.json.sha256",
                    coverage_by_code_path=COVERAGE_DIR / "coverage_by_code.parquet",
                    coverage_by_date_path=COVERAGE_DIR / "coverage_by_date.parquet",
                    unavailable_path=COVERAGE_DIR / "unavailable_security_dates.parquet",
                    formal_snapshot_dir=Path(snapshot["path"]),
                    approved_template=frozen_template,
                    gate_reference=FrozenCriteriaReference(snapshot_id="", criteria_json="{}", declared_content_hash=""),
                    kill_reference=FrozenCriteriaReference(snapshot_id="", criteria_json="{}", declared_content_hash=""),
                    ledger=ledger,
                    strategy_draft=draft,
                    universe=universe,
                    oos_window_rule_id="fixed_ratio_70_30",
                    oos_window_start=date(2026, 3, 20),
                    oos_window_end=date(2026, 7, 10),
                    frozen_by="test",
                    backtest_start=date(2025, 6, 27),
                    scope_freeze_path=SCOPE_DIR / "manifest.json",
                    gate_criteria_hash="",
                )
            finally:
                db.close()
            self.assertIsInstance(result, ProtocolFreezePreflightResult)
            self.assertEqual(result.reason_code, "criteria_reference_unavailable")


if __name__ == "__main__":
    unittest.main()
