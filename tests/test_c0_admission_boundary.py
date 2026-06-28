"""
C0 Task 1: C Admission Boundary Identification Tests

Tests to identify if current Signal Board / C module entry points
have bypass risks for B6/CAdmissionGate.
"""
import unittest


class TestC0AdmissionBoundary(unittest.TestCase):
    def test_signal_generation_script_has_no_strategy_state_check(self):
        """
        Original Signal Board entry point: generate_planned_signals.py script.

        Original observation: Script took strategy YAML file path directly.
        No StrategyDB dependency, no lifecycle_state check.

        C0 Task 2 result: Script now has StrategyDB import and lifecycle_state check.
        This test documents that the admission gate has been added.
        """
        # Read generate_planned_signals.py source
        import backend.scripts.generate_planned_signals as gen_script
        import inspect

        source = inspect.getsource(gen_script)

        # C0 Task 2 added StrategyDB and CAdmissionGate
        self.assertIn("StrategyDB", source)
        self.assertIn("CAdmissionGate", source)

        # C0 Task 2 added lifecycle_state check
        self.assertIn("lifecycle_state", source)
        self.assertIn("prototype_passed", source)

        # Admission gate has been integrated (C0 Task 2 complete)

    def test_signal_board_api_has_no_strategy_admission_filter(self):
        """
        Current Signal Board API: backend/api/signal_board.py

        Observation: API lists signals from SignalBoardDB.
        No filter by strategy lifecycle_state.

        Risk: API can return signals from non-prototype_passed strategies
        if those signals were generated (by script or other means).

        Mitigation: C0 Task 2 will add admission gate at signal generation.
        """
        import backend.api.signal_board as api_module
        import inspect

        source = inspect.getsource(api_module)

        # Verify no StrategyDB import
        self.assertNotIn("StrategyDB", source)
        self.assertNotIn("from backend.db.strategy", source)

        # Verify no CAdmissionGate import
        self.assertNotIn("CAdmissionGate", source)
        self.assertNotIn("from backend.services.c_admission_gate", source)

        # This is EXPECTED - API is read-only display layer
        # Admission gate belongs at signal generation entry point

    def test_signal_board_db_stores_signals_without_lifecycle_state(self):
        """
        SignalBoardDB schema: planned_signals table.

        C1 Update: PlannedSignal now has strategy_revision_id, lifecycle_state_at_generation,
        and admission_source fields (added in C1 Task 2).

        C0 observation was: PlannedSignal had no lifecycle_state field.
        C1 solution: Added admission metadata fields to enable filtering.
        """
        from contracts.signal_board import PlannedSignal

        # Check PlannedSignal fields
        fields = PlannedSignal.model_fields.keys()

        self.assertIn("strategy_id", fields)
        self.assertIn("strategy_version", fields)

        # C1 Task 2 added admission metadata fields
        self.assertIn("strategy_revision_id", fields)
        self.assertIn("lifecycle_state_at_generation", fields)
        self.assertIn("admission_source", fields)

    def test_c_admission_boundary_is_signal_generation_entry_point(self):
        """
        Conclusion: C admission boundary is at signal generation entry point.

        Current entry point: generate_planned_signals.py script.

        C0 Task 2 strategy:
        1. Require strategy_revision_id parameter in generate_planned_signals.py
        2. Add StrategyDB lookup for lifecycle_state
        3. Call CAdmissionGate.require_prototype_passed() before generation
        4. Reject with ValueError if not prototype_passed

        Alternative considered: Add admission check in Signal Board API.
        Rejected because:
        - API is read-only display layer
        - Signals already exist in DB at that point
        - Better to reject at generation time (fail early)
        """
        import backend.scripts.generate_planned_signals as gen_script
        import inspect

        source = inspect.getsource(gen_script)

        self.assertIn("strategy_revision_id is required for C module admission", source)
        self.assertIn("strategy_db_path is required for C module admission", source)
        self.assertNotIn("optional, enables prototype_passed validation", source)


if __name__ == "__main__":
    unittest.main()
