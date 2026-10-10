"""B6 Protocol Contract Tests - Task 4B-2A"""
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.research_protocol_freezer import _validate_frozen_criteria
from contracts.strategy import (
    FrozenCriteriaReference,
    ProtocolFreezePreflightResult,
    ResearchProtocolSnapshot,
    compute_b6_protocol_id,
    compute_b6_protocol_id_from_fields,
)


def _computed_id(data: dict) -> str:
    return compute_b6_protocol_id_from_fields(
        **{
            key: value
            for key, value in data.items()
            if key not in {"protocol_snapshot_id", "frozen_at", "frozen_by", "frozen"}
        }
    )


class TestProtocolFreezePreflightResult(unittest.TestCase):
    def test_preflight_result_frozen(self):
        """Preflight result is frozen."""
        result = ProtocolFreezePreflightResult(
            status="validation_unavailable",
            reason_code="template_not_approved",
        )
        with self.assertRaises(Exception):
            result.status = "available"
    
    def test_preflight_result_has_no_protocol_id(self):
        """Preflight result has no protocol_snapshot_id field."""
        result = ProtocolFreezePreflightResult(
            status="validation_unavailable",
            reason_code="ledger_budget_exhausted",
            detail="No draws remaining",
        )
        self.assertFalse(hasattr(result, "protocol_snapshot_id"))
    
    def test_all_reason_codes_valid(self):
        """All approved reason codes construct successfully."""
        codes = [
            "availability_qualification_unavailable",
            "availability_successor_binding_invalid",
            "snapshot_manifest_unavailable",
            "template_not_approved",
            "template_binding_mismatch",
            "artifact_binding_mismatch",
            "criteria_reference_unavailable",
            "criteria_content_hash_mismatch",
            "criteria_envelope_hash_mismatch",
            "ledger_owner_unavailable",
            "ledger_active_reservation",
            "ledger_budget_exhausted",
            "split_or_time_consistency_invalid",
        ]
        for code in codes:
            result = ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code=code,
            )
            self.assertEqual(result.reason_code, code)


class TestB6ProtocolContract(unittest.TestCase):
    def _make_b6_protocol(self, **overrides):
        """Factory for valid B6 protocol. ponytail: computes real ID."""
        from contracts.strategy import compute_b6_protocol_id
        defaults = {
            "protocol_snapshot_id": "",  # computed
            "theme_id": "t001",
            "hypothesis_source_snapshot_id": "h001",
            "strategy_revision_id": "r001",
            "sample_split_rule_id": "split001",
            "oos_window_rule_id": "fixed_ratio_70_30",
            "oos_window_rule_params_json": "{}",
            "oos_window_start": date(2024, 7, 1),
            "oos_window_end": date(2024, 12, 31),
            "shared_oos_window_id": "win001",
            "backtest_universe_spec_id": "u001",
            "data_snapshot_id": "snap001",
            "kill_criteria_snapshot_id": "kill001",
            "prototype_gate_thresholds_json": '{"threshold": 0.5}',
            "strategy_config_hash": "cfghash",
            "data_snapshot_hash": "datahash",
            "gate_criteria_hash": "gatehash",
            "frozen_at": datetime(2026, 1, 1),
            "frozen_by": "test",
            "protocol_profile": "b6_coverage_bound",
            "availability_successor_id": "succ001",
            "availability_successor_manifest_hash": "succhash",
            "availability_successor_algorithm_hash": "succalg",
            "predecessor_qualification_id": "pred001",
            "predecessor_qualification_manifest_hash": "predhash",
            "predecessor_qualification_status": "availability_bounded_qualified",
            "predecessor_qualification_algorithm_hash": "predalg",
            "coverage_package_id": "cov001",
            "coverage_manifest_hash": "covhash",
            "coverage_algorithm_hash": "covalg",
            "source_scope_hash": "scopehash",
            "data_requirements_hash": "reqhash",
            "expected_stock_days": 1000,
            "complete_stock_days": 900,
            "unavailable_stock_days": 100,
            "gate_snapshot_id": "gatesnap",
            "gate_content_hash": "gatecontenthash",
            "kill_content_hash": "killcontenthash",
        }
        defaults.update(overrides)
        defaults["protocol_snapshot_id"] = _computed_id(defaults)
        return ResearchProtocolSnapshot(**defaults)
    
    def test_legacy_b3_remains_valid(self):
        """Legacy B3 protocol with no B6 fields remains valid."""
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p001",
            theme_id="t001",
            hypothesis_source_snapshot_id="h001",
            strategy_revision_id="r001",
            sample_split_rule_id="split001",
            oos_window_rule_id="fixed_ratio_70_30",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="win001",
            backtest_universe_spec_id="u001",
            data_snapshot_id="snap001",
            kill_criteria_snapshot_id="",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="cfghash",
            data_snapshot_hash="datahash",
            gate_criteria_hash="gatehash",
            frozen_at=datetime(2026, 1, 1),
            frozen_by="test",
            protocol_profile="legacy_b3",
        )
        self.assertEqual(protocol.protocol_profile, "legacy_b3")
    
    def test_b6_coverage_bound_requires_all_fields(self):
        """B6 coverage_bound rejects missing required field."""
        with self.assertRaisesRegex(ValueError, "b6_coverage_bound requires"):
            ResearchProtocolSnapshot(
                protocol_snapshot_id="p001",
                theme_id="t001",
                hypothesis_source_snapshot_id="h001",
                strategy_revision_id="r001",
                sample_split_rule_id="split001",
                oos_window_rule_id="fixed_ratio_70_30",
                oos_window_rule_params_json="{}",
                oos_window_start=date(2024, 7, 1),
                oos_window_end=date(2024, 12, 31),
                shared_oos_window_id="win001",
                backtest_universe_spec_id="u001",
                data_snapshot_id="snap001",
                kill_criteria_snapshot_id="kill001",
                prototype_gate_thresholds_json='{"threshold": 0.5}',
                strategy_config_hash="cfghash",
                data_snapshot_hash="datahash",
                gate_criteria_hash="gatehash",
                frozen_at=datetime(2026, 1, 1),
                frozen_by="test",
                protocol_profile="b6_coverage_bound",
                # missing all B6 fields
            )
    
    def test_b6_coverage_arithmetic_invalid(self):
        """B6 rejects incorrect coverage arithmetic."""
        with self.assertRaisesRegex(ValueError, "coverage arithmetic"):
            ResearchProtocolSnapshot(
                protocol_snapshot_id="p001",
                theme_id="t001",
                hypothesis_source_snapshot_id="h001",
                strategy_revision_id="r001",
                sample_split_rule_id="split001",
                oos_window_rule_id="fixed_ratio_70_30",
                oos_window_rule_params_json="{}",
                oos_window_start=date(2024, 7, 1),
                oos_window_end=date(2024, 12, 31),
                shared_oos_window_id="win001",
                backtest_universe_spec_id="u001",
                data_snapshot_id="snap001",
                kill_criteria_snapshot_id="kill001",
                prototype_gate_thresholds_json='{"threshold": 0.5}',
                strategy_config_hash="cfghash",
                data_snapshot_hash="datahash",
                gate_criteria_hash="gatehash",
                frozen_at=datetime(2026, 1, 1),
                frozen_by="test",
                protocol_profile="b6_coverage_bound",
                availability_successor_id="succ001",
                availability_successor_manifest_hash="succhash",
                availability_successor_algorithm_hash="succalg",
                predecessor_qualification_id="pred001",
                predecessor_qualification_manifest_hash="predhash",
                predecessor_qualification_status="availability_bounded_qualified",
                predecessor_qualification_algorithm_hash="predalg",
                coverage_package_id="cov001",
                coverage_manifest_hash="covhash",
                coverage_algorithm_hash="covalg",
                source_scope_hash="scopehash",
                data_requirements_hash="reqhash",
                expected_stock_days=1000,
                complete_stock_days=800,
                unavailable_stock_days=100,  # 800+100=900 != 1000
                gate_snapshot_id="gatesnap",
                gate_content_hash="gatecontenthash",
                kill_content_hash="killcontenthash",
            )
    
    def test_b6_rejects_empty_criteria(self):
        """B6 rejects empty gate criteria."""
        with self.assertRaisesRegex(ValueError, "gate criteria cannot be empty"):
            ResearchProtocolSnapshot(
                protocol_snapshot_id="p001",
                theme_id="t001",
                hypothesis_source_snapshot_id="h001",
                strategy_revision_id="r001",
                sample_split_rule_id="split001",
                oos_window_rule_id="fixed_ratio_70_30",
                oos_window_rule_params_json="{}",
                oos_window_start=date(2024, 7, 1),
                oos_window_end=date(2024, 12, 31),
                shared_oos_window_id="win001",
                backtest_universe_spec_id="u001",
                data_snapshot_id="snap001",
                kill_criteria_snapshot_id="kill001",
                prototype_gate_thresholds_json="{}",  # empty
                strategy_config_hash="cfghash",
                data_snapshot_hash="datahash",
                gate_criteria_hash="gatehash",
                frozen_at=datetime(2026, 1, 1),
                frozen_by="test",
                protocol_profile="b6_coverage_bound",
                availability_successor_id="succ001",
                availability_successor_manifest_hash="succhash",
                availability_successor_algorithm_hash="succalg",
                predecessor_qualification_id="pred001",
                predecessor_qualification_manifest_hash="predhash",
                predecessor_qualification_status="availability_bounded_qualified",
                predecessor_qualification_algorithm_hash="predalg",
                coverage_package_id="cov001",
                coverage_manifest_hash="covhash",
                coverage_algorithm_hash="covalg",
                source_scope_hash="scopehash",
                data_requirements_hash="reqhash",
                expected_stock_days=1000,
                complete_stock_days=900,
                unavailable_stock_days=100,
                gate_snapshot_id="gatesnap",
                gate_content_hash="gatecontenthash",
                kill_content_hash="killcontenthash",
            )
    
    def test_b6_valid_protocol(self):
        """B6 with complete valid bindings constructs successfully. ponytail: use factory."""
        protocol = self._make_b6_protocol()
        self.assertEqual(protocol.protocol_profile, "b6_coverage_bound")

    def test_b6_protocol_id_changes_for_v2_criteria_identity(self):
        """The freezer keeps v1 strict and accepts an explicitly selected v2 envelope."""
        gate_json = '{"a":1}'
        kill_json = '{"b":2}'
        gate_hash = __import__("hashlib").sha256(gate_json.encode("utf-8")).hexdigest()
        kill_hash = __import__("hashlib").sha256(kill_json.encode("utf-8")).hexdigest()
        gate = FrozenCriteriaReference(
            snapshot_id="prototype_gate_v2_gate_v2_test",
            criteria_json=gate_json,
            declared_content_hash=gate_hash,
        )
        kill = FrozenCriteriaReference(
            snapshot_id="prototype_gate_v2_kill_v2_test",
            criteria_json=kill_json,
            declared_content_hash=kill_hash,
        )
        v2_envelope = {
            "schema_version": "prototype_gate_v2_criteria_envelope.v2",
            "criteria_contract_version": "v2",
            "gate_snapshot_id": gate.snapshot_id,
            "gate_content_hash": gate_hash,
            "kill_snapshot_id": kill.snapshot_id,
            "kill_content_hash": kill_hash,
        }
        v2_hash = __import__("hashlib").sha256(
            __import__("json").dumps(
                v2_envelope,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        v1_result = _validate_frozen_criteria(
            gate_reference=gate,
            kill_reference=kill,
            gate_criteria_hash=v2_hash,
        )
        self.assertIsInstance(v1_result, ProtocolFreezePreflightResult)
        self.assertEqual(v1_result.reason_code, "criteria_reference_unavailable")

        v2_result = _validate_frozen_criteria(
            gate_reference=gate,
            kill_reference=kill,
            gate_criteria_hash=v2_hash,
            criteria_envelope_schema="prototype_gate_v2_criteria_envelope.v2",
        )
        self.assertIsInstance(v2_result, dict)
        self.assertEqual(v2_result["envelope"], v2_envelope)
        self.assertEqual(v2_result["envelope_hash"], v2_hash)


class TestB6DeterministicID(unittest.TestCase):
    def _make_b6_protocol(self, **overrides):
        """Factory for valid B6 protocol. ponytail: computes real ID."""
        from contracts.strategy import compute_b6_protocol_id
        defaults = {
            "protocol_snapshot_id": "",
            "theme_id": "t001",
            "hypothesis_source_snapshot_id": "h001",
            "strategy_revision_id": "r001",
            "sample_split_rule_id": "split001",
            "oos_window_rule_id": "fixed_ratio_70_30",
            "oos_window_rule_params_json": "{}",
            "oos_window_start": date(2024, 7, 1),
            "oos_window_end": date(2024, 12, 31),
            "shared_oos_window_id": "win001",
            "backtest_universe_spec_id": "u001",
            "data_snapshot_id": "snap001",
            "kill_criteria_snapshot_id": "kill001",
            "prototype_gate_thresholds_json": '{"threshold": 0.5}',
            "strategy_config_hash": "cfghash",
            "data_snapshot_hash": "datahash",
            "gate_criteria_hash": "gatehash",
            "frozen_at": datetime(2026, 1, 1),
            "frozen_by": "test",
            "protocol_profile": "b6_coverage_bound",
            "availability_successor_id": "succ001",
            "availability_successor_manifest_hash": "succhash",
            "availability_successor_algorithm_hash": "succalg",
            "predecessor_qualification_id": "pred001",
            "predecessor_qualification_manifest_hash": "predhash",
            "predecessor_qualification_status": "availability_bounded_qualified",
            "predecessor_qualification_algorithm_hash": "predalg",
            "coverage_package_id": "cov001",
            "coverage_manifest_hash": "covhash",
            "coverage_algorithm_hash": "covalg",
            "source_scope_hash": "scopehash",
            "data_requirements_hash": "reqhash",
            "expected_stock_days": 1000,
            "complete_stock_days": 900,
            "unavailable_stock_days": 100,
            "gate_snapshot_id": "gatesnap",
            "gate_content_hash": "gatecontenthash",
            "kill_content_hash": "killcontenthash",
        }
        defaults.update(overrides)
        defaults["protocol_snapshot_id"] = _computed_id(defaults)
        return ResearchProtocolSnapshot(**defaults)
    
    def test_b6_id_excludes_frozen_at(self):
        """B6 ID unchanged despite different frozen_at."""
        p1 = self._make_b6_protocol(frozen_at=datetime(2026, 1, 1))
        p2 = self._make_b6_protocol(frozen_at=datetime(2026, 12, 31))
        self.assertEqual(compute_b6_protocol_id(p1), compute_b6_protocol_id(p2))
    
    def test_b6_id_excludes_frozen_by(self):
        """B6 ID unchanged despite different frozen_by."""
        p1 = self._make_b6_protocol(frozen_by="alice")
        p2 = self._make_b6_protocol(frozen_by="bob")
        self.assertEqual(compute_b6_protocol_id(p1), compute_b6_protocol_id(p2))
    
    def test_b6_id_changes_on_binding_change(self):
        """B6 ID changes when any binding changes."""
        base = self._make_b6_protocol()
        base_id = compute_b6_protocol_id(base)
        
        # Change each binding
        for field in ["coverage_manifest_hash", "gate_content_hash", "data_snapshot_hash"]:
            changed = self._make_b6_protocol(**{field: f"changed_{field}"})
            changed_id = compute_b6_protocol_id(changed)
            self.assertNotEqual(base_id, changed_id, f"ID should change when {field} changes")

    def test_b6_rejects_noncanonical_ids_and_raw_helper_matches_wrapper(self):
        protocol = self._make_b6_protocol()
        payload = protocol.model_dump()
        raw_id = _computed_id(payload)
        self.assertEqual(raw_id, compute_b6_protocol_id(protocol))
        for bad_id in ("", "wrong", "arbitrary_temp"):
            with self.subTest(protocol_snapshot_id=bad_id):
                payload["protocol_snapshot_id"] = bad_id
                with self.assertRaisesRegex(ValueError, "must match computed ID"):
                    ResearchProtocolSnapshot(**payload)
    
    def test_legacy_b3_id_different_from_b6(self):
        """Legacy B3 and B6 produce different IDs."""
        legacy = self._make_b6_protocol(protocol_profile="legacy_b3")
        b6 = self._make_b6_protocol(protocol_profile="b6_coverage_bound")
        self.assertNotEqual(compute_b6_protocol_id(legacy), compute_b6_protocol_id(b6))


class TestB6DBRoundTrip(unittest.TestCase):
    def test_b6_protocol_round_trip(self):
        """B6 protocol stores and reads via second connection. ponytail: FK needs draft."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db_path = Path(temp.name) / "test.db"
        
        db1 = StrategyDB(str(db_path))
        self.addCleanup(db1.close)
        
        # ponytail: FK constraint requires draft + universe
        from contracts.strategy import StrategyDraft, StrategyLifecycleState, BacktestUniverseSpec, compute_b6_protocol_id
        universe = BacktestUniverseSpec(
            universe_spec_id="u001",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2020, 1, 1),
            membership_effective_to=date(2025, 1, 1),
            snapshot_date=date(2025, 1, 1),
            membership_snapshot_ids=("snap001",),
            quality_status="ok",
        )
        db1.store_backtest_universe(universe)
        
        draft = StrategyDraft(
            strategy_revision_id="r001",
            theme_id="t001",
            hypothesis_id="h001",
            strategy_template_id="tmpl001",
            strategy_template_version="v1",
            strategy_template_hash="tmplhash",
            hypothesis_source_snapshot_id="h001",
            backtest_universe_spec_id="u001",
            strategy_config_json="{}",
            sample_split_rule_id="split001",
            created_at=datetime(2026, 1, 1),
        )
        state = StrategyLifecycleState(
            lifecycle_state_id="state001",
            strategy_revision_id="r001",
            state_version=1,
            state="draft",
            source_record_id="initial",
            recorded_at=datetime(2026, 1, 1),
            recorded_by="test",
        )
        db1.create_strategy_draft(draft, state)
        
        # ponytail: compute ID first, no _temp bypass
        protocol_data = dict(
            protocol_snapshot_id="placeholder",
            theme_id="t001",
            hypothesis_source_snapshot_id="h001",
            strategy_revision_id="r001",
            sample_split_rule_id="split001",
            oos_window_rule_id="fixed_ratio_70_30",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="win001",
            backtest_universe_spec_id="u001",
            data_snapshot_id="snap001",
            kill_criteria_snapshot_id="kill001",
            prototype_gate_thresholds_json='{"threshold": 0.5}',
            strategy_config_hash="cfghash",
            data_snapshot_hash="datahash",
            gate_criteria_hash="gatehash",
            frozen_at=datetime(2026, 1, 1, 12, 0, 0),
            frozen_by="test",
            protocol_profile="b6_coverage_bound",
            availability_successor_id="succ001",
            availability_successor_manifest_hash="succhash",
            availability_successor_algorithm_hash="succalg",
            predecessor_qualification_id="pred001",
            predecessor_qualification_manifest_hash="predhash",
            predecessor_qualification_status="availability_bounded_qualified",
            predecessor_qualification_algorithm_hash="predalg",
            coverage_package_id="cov001",
            coverage_manifest_hash="covhash",
            coverage_algorithm_hash="covalg",
            source_scope_hash="scopehash",
            data_requirements_hash="reqhash",
            expected_stock_days=1000,
            complete_stock_days=900,
            unavailable_stock_days=100,
            gate_snapshot_id="gatesnap",
            gate_content_hash="gatecontenthash",
            kill_content_hash="killcontenthash",
        )
        expected_id = _computed_id(protocol_data)
        
        protocol_data["protocol_snapshot_id"] = expected_id
        protocol = ResearchProtocolSnapshot(**protocol_data)
        
        # Store via db1
        db1.store_protocol_snapshot(protocol)
        
        # Read via second connection
        db2 = StrategyDB(str(db_path))
        self.addCleanup(db2.close)
        
        retrieved = db2.get_protocol_snapshot(expected_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.protocol_profile, "b6_coverage_bound")
        self.assertEqual(retrieved.coverage_manifest_hash, "covhash")
        self.assertEqual(retrieved.complete_stock_days, 900)
        
        # Verify ID is deterministic
        retrieved_id = compute_b6_protocol_id(retrieved)
        self.assertEqual(expected_id, retrieved_id)


if __name__ == "__main__":
    unittest.main()
