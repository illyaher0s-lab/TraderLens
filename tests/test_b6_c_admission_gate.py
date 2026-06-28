"""
B6 Task 7: C Admission Gate Tests

Tests that C module only accepts true prototype_passed strategies.
"""
import unittest

from backend.services.c_admission_gate import CAdmissionGate


class TestB6CAdmissionGate(unittest.TestCase):
    def test_c_admission_rejects_non_prototype_passed_states(self):
        """C admission rejects all non-prototype_passed states."""
        gate = CAdmissionGate()

        for state in ["draft", "rejected", "needs_review", "candidate_for_prototype_passed"]:
            with self.subTest(state=state):
                with self.assertRaises(ValueError) as ctx:
                    gate.require_prototype_passed(
                        strategy_revision_id="strat_001",
                        lifecycle_state=state,
                    )

                self.assertIn("not prototype_passed", str(ctx.exception))
                self.assertIn(state, str(ctx.exception))

    def test_c_admission_accepts_only_prototype_passed(self):
        """C admission accepts only prototype_passed."""
        gate = CAdmissionGate()

        result = gate.require_prototype_passed(
            strategy_revision_id="strat_001",
            lifecycle_state="prototype_passed",
        )

        self.assertEqual(result["strategy_revision_id"], "strat_001")
        self.assertEqual(result["admission_status"], "accepted")

    def test_c_admission_rejects_candidate_for_prototype_passed(self):
        """C admission explicitly rejects candidate_for_prototype_passed."""
        gate = CAdmissionGate()

        with self.assertRaises(ValueError) as ctx:
            gate.require_prototype_passed(
                strategy_revision_id="strat_001",
                lifecycle_state="candidate_for_prototype_passed",
            )

        self.assertIn("not prototype_passed", str(ctx.exception))
        self.assertIn("candidate_for_prototype_passed", str(ctx.exception))

    def test_c_admission_has_no_broker_or_live_trading_dependency(self):
        """C admission gate has no broker or live trading dependency."""
        import inspect
        import backend.services.c_admission_gate as gate_module

        source = inspect.getsource(gate_module).lower()

        forbidden_keywords = [
            "broker",
            "live_trading",
            "order_submission",
            "execution_venue",
        ]

        for keyword in forbidden_keywords:
            self.assertNotIn(keyword, source)


if __name__ == "__main__":
    unittest.main()
