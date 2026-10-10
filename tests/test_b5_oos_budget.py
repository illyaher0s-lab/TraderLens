"""B5 OOS Budget Ledger Tests."""
import unittest
from datetime import datetime

from pydantic import ValidationError

from backend.services.b5_oos_types import (
    OOSReservation,
    GateCheckItem,
    ReportPayloadSchema,
    ExplanationSnapshot,
    B5ValidationBoundary,
)
from backend.services.oos_budget_ledger import OOSBudgetLedger
from tests.b5_fixtures import (
    make_oos_reservation,
    make_gate_check_item,
    make_report_payload_schema,
    make_explanation_snapshot,
)


class TestB5ContractsAreFrozen(unittest.TestCase):
    """Test B5 contracts are frozen and forbid extra fields."""
    
    def test_b5_contracts_are_frozen(self):
        """All B5 contracts must be frozen (Pydantic frozen=True)."""
        reservation = make_oos_reservation()
        
        # Frozen models raise ValidationError on mutation
        with self.assertRaises(ValidationError):
            reservation.status = "completed"
        
        gate_check = make_gate_check_item()
        with self.assertRaises(ValidationError):
            gate_check.status = "fail"
        
        report_payload = make_report_payload_schema()
        with self.assertRaises(ValidationError):
            report_payload.oos_draw_index = 2
        
        explanation = make_explanation_snapshot()
        with self.assertRaises(ValidationError):
            explanation.plain_summary = "Changed"
    
    def test_oos_reservation_requires_protocol_and_hashes(self):
        """OOSReservation must include strategy_config_hash, data_snapshot_hash, gate_criteria_hash."""
        reservation = make_oos_reservation()
        
        self.assertIsNotNone(reservation.strategy_config_hash)
        self.assertIsNotNone(reservation.data_snapshot_hash)
        self.assertIsNotNone(reservation.gate_criteria_hash)
        self.assertGreater(len(reservation.strategy_config_hash), 0)
        self.assertGreater(len(reservation.data_snapshot_hash), 0)
        self.assertGreater(len(reservation.gate_criteria_hash), 0)
    
    def test_gate_check_item_has_deterministic_source(self):
        """GateCheckItem must reference deterministic source (report/protocol ID), not LLM verdict."""
        check = make_gate_check_item(
            deterministic_source="report:rpt_001"
        )
        
        self.assertIn("report:", check.deterministic_source)
        self.assertGreater(len(check.deterministic_source), 0)
        
        # Test protocol reference
        check_protocol = make_gate_check_item(
            deterministic_source="protocol:proto_001"
        )
        self.assertIn("protocol:", check_protocol.deterministic_source)
    
    def test_report_payload_has_no_buy_sell_recommendation(self):
        """ReportPayloadSchema must not contain buy/sell recommendation fields."""
        payload = make_report_payload_schema()
        
        # Check no forbidden fields exist
        payload_dict = payload.model_dump()
        forbidden_fields = ["buy_signal", "sell_signal", "action_plan", "recommendation", "entry_price", "target_price"]
        
        for field in forbidden_fields:
            self.assertNotIn(field, payload_dict)
        
        # Verify disclaimer is present
        self.assertIn("not", payload.disclaimer.lower())
        self.assertIn("profit", payload.disclaimer.lower())
        self.assertIn("live trading", payload.disclaimer.lower())
    
    def test_explanation_snapshot_references_report_and_gate(self):
        """ExplanationSnapshot must reference report_id and gate_result_id."""
        explanation = make_explanation_snapshot()
        
        self.assertIsNotNone(explanation.report_id)
        self.assertIsNotNone(explanation.gate_result_id)
        self.assertGreater(len(explanation.report_id), 0)
        self.assertGreater(len(explanation.gate_result_id), 0)
        
        # Deterministic evidence must reference check IDs
        self.assertGreater(len(explanation.deterministic_evidence), 0)
        for evidence_id in explanation.deterministic_evidence:
            self.assertIsInstance(evidence_id, str)
            self.assertGreater(len(evidence_id), 0)
    
    def test_b5_types_do_not_write_prototype_passed(self):
        """B5 types must not have prototype_passed write capability."""
        # Check OOSReservation has no promotion field
        reservation = make_oos_reservation()
        reservation_dict = reservation.model_dump()
        self.assertNotIn("prototype_passed", reservation_dict)
        self.assertNotIn("promotion_id", reservation_dict)
        
        # Check GateCheckItem has no promotion field
        check = make_gate_check_item()
        check_dict = check.model_dump()
        self.assertNotIn("prototype_passed", check_dict)
        self.assertNotIn("promotion_id", check_dict)
        
        # Check ReportPayloadSchema has no promotion field
        payload = make_report_payload_schema()
        payload_dict = payload.model_dump()
        self.assertNotIn("prototype_passed", payload_dict)
        self.assertNotIn("promotion_id", payload_dict)
        
        # Check ExplanationSnapshot has no promotion field
        explanation = make_explanation_snapshot()
        explanation_dict = explanation.model_dump()
        self.assertNotIn("prototype_passed", explanation_dict)
        self.assertNotIn("promotion_id", explanation_dict)
    
    def test_b5_validation_boundary_proof(self):
        """B5ValidationBoundary proves contract design correctness."""
        boundary = B5ValidationBoundary(
            boundary_name="b5_oos_types_frozen",
            proof_timestamp=datetime(2026, 6, 27, 14, 0, 0),
        )
        
        self.assertEqual(boundary.boundary_name, "b5_oos_types_frozen")
        self.assertTrue(boundary.frozen)


class TestOOSBudgetLedger(unittest.TestCase):
    """Test OOS budget ledger and atomic reservation."""
    
    def setUp(self):
        import tempfile
        from pathlib import Path
        from backend.db.strategy import StrategyDB
        
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
        self.tmpfile.close()
        self.db_path = Path(self.tmpfile.name)
        self.db = StrategyDB(str(self.db_path))
        self.ledger = OOSBudgetLedger(self.db)
        self.theme_id = "theme_test_001"
        self.hypothesis_id = "hyp_snap_001"
        self.config_hash_1 = "config_hash_001"
        self.data_hash_1 = "data_hash_001"
        self.gate_hash_1 = "gate_hash_001"
        self.oos_window_1 = "shared_oos_001"
    
    def tearDown(self):
        self.db.close()
        if self.db_path.exists():
            self.db_path.unlink()
    
    def test_same_hash_tuple_returns_cached_without_budget_draw(self):
        """Same (config, data, gate) hash tuple returns cached result without consuming budget."""
        # First reservation
        rsv1 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb1"
        )
        self.assertEqual(rsv1.oos_draw_index, 1)
        
        # Complete first
        self.ledger.start_execution(rsv1.reservation_id)
        self.ledger.complete_reservation(rsv1.reservation_id, "rejected")
        
        # Check cache
        cached_id = self.ledger.check_cache(self.config_hash_1, self.data_hash_1, self.gate_hash_1)
        self.assertEqual(cached_id, rsv1.reservation_id)
        
        # Second attempt with same hashes should fail (cached)
        with self.assertRaises(ValueError) as ctx:
            self.ledger.reserve_oos_draw(
                self.theme_id, self.hypothesis_id,
                self.config_hash_1, self.data_hash_1, self.gate_hash_1,
                self.oos_window_1,
            idempotency_key="kb2"
            )
        # ponytail: DB version says "Hash tuple already used", both correct
        self.assertTrue("cached" in str(ctx.exception).lower() or "already used" in str(ctx.exception).lower())
    
    def test_strategy_hash_change_consumes_new_draw(self):
        """Strategy config hash change consumes new OOS draw."""
        # First reservation
        rsv1 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb3"
        )
        self.ledger.start_execution(rsv1.reservation_id)
        self.ledger.complete_reservation(rsv1.reservation_id, "rejected")
        
        # Second reservation with different config hash
        config_hash_2 = "config_hash_002"
        rsv2 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            config_hash_2, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb4"
        )
        
        self.assertEqual(rsv2.oos_draw_index, 2)  # Consumed new draw
        self.assertNotEqual(rsv2.reservation_id, rsv1.reservation_id)
    
    def test_data_hash_change_consumes_new_draw(self):
        """Data snapshot hash change consumes new OOS draw."""
        rsv1 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb5"
        )
        self.ledger.start_execution(rsv1.reservation_id)
        self.ledger.complete_reservation(rsv1.reservation_id, "rejected")
        
        # Different data hash
        data_hash_2 = "data_hash_002"
        rsv2 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, data_hash_2, self.gate_hash_1,
            "shared_oos_002",  # Different window to avoid cross-theme check
            idempotency_key="kb4"
        )
        
        self.assertEqual(rsv2.oos_draw_index, 2)
    
    def test_gate_hash_change_consumes_new_draw(self):
        """Gate criteria hash change consumes new OOS draw."""
        rsv1 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb7"
        )
        self.ledger.start_execution(rsv1.reservation_id)
        self.ledger.complete_reservation(rsv1.reservation_id, "rejected")
        
        # Different gate hash
        gate_hash_2 = "gate_hash_002"
        rsv2 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, gate_hash_2,
            self.oos_window_1,
            idempotency_key="kb8"
        )
        
        self.assertEqual(rsv2.oos_draw_index, 2)
    
    def test_fourth_oos_draw_rejected(self):
        """Fourth OOS draw is rejected (budget exhausted)."""
        # Consume 3 draws
        for i in range(3):
            rsv = self.ledger.reserve_oos_draw(
                self.theme_id, self.hypothesis_id,
                f"config_{i}", f"data_{i}", f"gate_{i}",
                f"oos_window_{i}",
                idempotency_key=f"kbloop{i}"
            )
            self.ledger.start_execution(rsv.reservation_id)
            self.ledger.complete_reservation(rsv.reservation_id, "rejected")
        
        # Fourth draw should fail
        with self.assertRaises(ValueError) as ctx:
            self.ledger.reserve_oos_draw(
                self.theme_id, self.hypothesis_id,
                "config_4", "data_4", "gate_4",
                "oos_window_4",
            idempotency_key="kb10"
            )
        self.assertIn("budget exhausted", str(ctx.exception))
        self.assertIn("max 3", str(ctx.exception))
    
    def test_active_reservation_blocks_concurrent_draw(self):
        """Active reservation blocks concurrent OOS draw for same theme."""
        rsv1 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb11"
        )
        
        # Attempt concurrent draw
        with self.assertRaises(ValueError) as ctx:
            self.ledger.reserve_oos_draw(
                self.theme_id, self.hypothesis_id,
                "config_2", "data_2", "gate_2",
                "oos_window_2",
            idempotency_key="kb12"
            )
        self.assertIn("Active reservation blocks", str(ctx.exception))
    
    def test_failed_infrastructure_run_releases_reservation(self):
        """Infrastructure failure releases reservation without consuming budget."""
        rsv = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb13"
        )
        
        # Release due to infrastructure failure
        self.ledger.release_reservation(rsv.reservation_id, "B4 backtest crashed")
        
        # Budget not consumed - can reserve again
        rsv2 = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb14"
        )
        
        self.assertEqual(rsv2.oos_draw_index, 1)  # Still draw 1
    
    def test_completed_rejected_report_consumes_budget(self):
        """Completed report consumes budget even if rejected."""
        rsv = self.ledger.reserve_oos_draw(
            self.theme_id, self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb15"
        )
        
        # Complete with rejected verdict
        self.ledger.start_execution(rsv.reservation_id)
        self.ledger.complete_reservation(rsv.reservation_id, "rejected")
        
        # Budget consumed
        state = self.ledger.get_ledger_state(self.theme_id, self.hypothesis_id)
        self.assertEqual(state["completed_draw_count"], 1)
        self.assertEqual(state["next_oos_draw_index"], 2)
    
    def test_cross_theme_same_window_and_data_hash_rejected(self):
        """Cross-theme reuse of same OOS window + data hash is rejected."""
        # Theme 1 uses OOS window
        rsv1 = self.ledger.reserve_oos_draw(
            "theme_001", self.hypothesis_id,
            self.config_hash_1, self.data_hash_1, self.gate_hash_1,
            self.oos_window_1,
            idempotency_key="kb16"
        )
        
        # Theme 2 attempts to use same OOS window + data hash
        with self.assertRaises(ValueError) as ctx:
            self.ledger.reserve_oos_draw(
                "theme_002", "hyp_002",
                "config_2", self.data_hash_1, "gate_2",
                self.oos_window_1,  # Same OOS window + same data hash
                idempotency_key="kb9"
            )
        self.assertIn("Cross-theme OOS reuse rejected", str(ctx.exception))
    
    def test_oos_ledger_has_no_llm_dependency(self):
        """OOS budget ledger must not import or call LLM."""
        import backend.services.oos_budget_ledger as ledger_module
        import inspect
        
        source = inspect.getsource(ledger_module)
        
        # Check no LLM imports
        forbidden_imports = ["import openai", "from openai", "import anthropic", "from anthropic"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
