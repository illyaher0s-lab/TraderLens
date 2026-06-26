"""
Task Execution Tests - M2

Tests task schema, state machine, and validation rules.
"""

import unittest
from datetime import datetime, timedelta

from strategy_core.task_execution import (
    TaskRecord,
    validate_task_record,
    is_valid_state_transition,
)


class TestTaskRecordSchema(unittest.TestCase):
    """Test TaskRecord structure and validation."""
    
    def test_valid_queued_task(self):
        """Valid queued task passes validation."""
        task = TaskRecord(
            task_id="task_001",
            task_type="backtest_run",
            status="queued",
            created_at=datetime.now(),
            started_at=None,
            finished_at=None,
            progress_pct=0.0,
            current_step="Task queued",
            input_payload={"strategy_path": "examples/strategies/strategy_001.yaml"},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        # Should not raise
        validate_task_record(task)
    
    def test_valid_running_task(self):
        """Valid running task passes validation."""
        now = datetime.now()
        task = TaskRecord(
            task_id="task_002",
            task_type="strategy_suite_run",
            status="running",
            created_at=now,
            started_at=now + timedelta(seconds=1),
            finished_at=None,
            progress_pct=45.0,
            current_step="Running backtest: 3/10 strategies",
            input_payload={"strategies_dir": "examples/strategies"},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        validate_task_record(task)
    
    def test_valid_succeeded_task(self):
        """Valid succeeded task passes validation."""
        now = datetime.now()
        task = TaskRecord(
            task_id="task_003",
            task_type="export_backtest_result",
            status="succeeded",
            created_at=now,
            started_at=now + timedelta(seconds=1),
            finished_at=now + timedelta(seconds=10),
            progress_pct=100.0,
            current_step="Export complete",
            input_payload={"result_path": "backtest_result.json"},
            artifact_paths=["metrics.json", "trades.csv", "equity_curve.png"],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        validate_task_record(task)
    
    def test_valid_failed_task(self):
        """Valid failed task passes validation."""
        now = datetime.now()
        task = TaskRecord(
            task_id="task_004",
            task_type="backtest_run",
            status="failed",
            created_at=now,
            started_at=now + timedelta(seconds=1),
            finished_at=now + timedelta(seconds=5),
            progress_pct=25.0,
            current_step="Loading fixture data",
            input_payload={"strategy_path": "bad_strategy.yaml"},
            artifact_paths=[],
            error_type="FileNotFoundError",
            error_message="Strategy file not found: bad_strategy.yaml",
            error_traceback="Traceback (most recent call last)...",
        )
        
        validate_task_record(task)
    
    def test_invalid_task_type_not_enforced_at_runtime(self):
        """Python Literal type hints are not enforced at runtime (documentation only)."""
        # This test documents that invalid task_type won't raise at construction time
        # Validation would need to be added to validate_task_record() if needed
        task = TaskRecord(
            task_id="task_005",
            task_type="invalid_type",  # Type hint violation, but Python allows it
            status="queued",
            created_at=datetime.now(),
            started_at=None,
            finished_at=None,
            progress_pct=0.0,
            current_step="Task queued",
            input_payload={},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        # Task is created (type hints not enforced)
        # M2 decision: task_type validation is caller's responsibility
        self.assertIsNotNone(task)
    
    def test_empty_task_id_fails(self):
        """Empty task_id fails validation."""
        task = TaskRecord(
            task_id="",  # Empty
            task_type="backtest_run",
            status="queued",
            created_at=datetime.now(),
            started_at=None,
            finished_at=None,
            progress_pct=0.0,
            current_step="Task queued",
            input_payload={},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_task_record(task)
        
        self.assertIn("task_id", str(ctx.exception))
    
    def test_progress_pct_out_of_range_fails(self):
        """progress_pct outside 0-100 fails validation."""
        task = TaskRecord(
            task_id="task_006",
            task_type="backtest_run",
            status="queued",
            created_at=datetime.now(),
            started_at=None,
            finished_at=None,
            progress_pct=150.0,  # Invalid
            current_step="Task queued",
            input_payload={},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_task_record(task)
        
        self.assertIn("progress_pct", str(ctx.exception))
    
    def test_running_task_without_started_at_fails(self):
        """Running task without started_at fails validation."""
        task = TaskRecord(
            task_id="task_007",
            task_type="backtest_run",
            status="running",
            created_at=datetime.now(),
            started_at=None,  # Invalid for running
            finished_at=None,
            progress_pct=50.0,
            current_step="Running",
            input_payload={},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_task_record(task)
        
        self.assertIn("started_at", str(ctx.exception))
    
    def test_succeeded_task_without_100_pct_fails(self):
        """Succeeded task without 100% progress fails validation."""
        now = datetime.now()
        task = TaskRecord(
            task_id="task_008",
            task_type="backtest_run",
            status="succeeded",
            created_at=now,
            started_at=now + timedelta(seconds=1),
            finished_at=now + timedelta(seconds=10),
            progress_pct=99.0,  # Invalid for succeeded
            current_step="Almost done",
            input_payload={},
            artifact_paths=[],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_task_record(task)
        
        self.assertIn("progress_pct", str(ctx.exception))
        self.assertIn("100.0", str(ctx.exception))
    
    def test_failed_task_without_error_message_fails(self):
        """Failed task without error_message fails validation."""
        now = datetime.now()
        task = TaskRecord(
            task_id="task_009",
            task_type="backtest_run",
            status="failed",
            created_at=now,
            started_at=now + timedelta(seconds=1),
            finished_at=now + timedelta(seconds=5),
            progress_pct=25.0,
            current_step="Failed",
            input_payload={},
            artifact_paths=[],
            error_type="ValueError",
            error_message=None,  # Invalid for failed
            error_traceback=None,
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_task_record(task)
        
        self.assertIn("error_message", str(ctx.exception))


class TestTaskStateMachine(unittest.TestCase):
    """Test task state machine transitions."""
    
    def test_valid_transitions(self):
        """Valid state transitions are allowed."""
        # queued → running
        self.assertTrue(is_valid_state_transition("queued", "running"))
        
        # running → succeeded
        self.assertTrue(is_valid_state_transition("running", "succeeded"))
        
        # running → failed
        self.assertTrue(is_valid_state_transition("running", "failed"))
        
        # running → cancelled
        self.assertTrue(is_valid_state_transition("running", "cancelled"))
        
        # queued → cancelled
        self.assertTrue(is_valid_state_transition("queued", "cancelled"))
    
    def test_invalid_transitions(self):
        """Invalid state transitions are rejected."""
        # succeeded → running (cannot restart)
        self.assertFalse(is_valid_state_transition("succeeded", "running"))
        
        # failed → succeeded (cannot fix retroactively)
        self.assertFalse(is_valid_state_transition("failed", "succeeded"))
        
        # cancelled → running (cannot resume)
        self.assertFalse(is_valid_state_transition("cancelled", "running"))
        
        # queued → succeeded (must go through running)
        self.assertFalse(is_valid_state_transition("queued", "succeeded"))
        
        # queued → failed (must go through running)
        self.assertFalse(is_valid_state_transition("queued", "failed"))
    
    def test_terminal_states_have_no_transitions(self):
        """Terminal states (succeeded, failed, cancelled) cannot transition."""
        terminal_states = ["succeeded", "failed", "cancelled"]
        
        for state in terminal_states:
            # Cannot transition to any state
            self.assertFalse(is_valid_state_transition(state, "queued"))
            self.assertFalse(is_valid_state_transition(state, "running"))
            self.assertFalse(is_valid_state_transition(state, "succeeded"))
            self.assertFalse(is_valid_state_transition(state, "failed"))
            self.assertFalse(is_valid_state_transition(state, "cancelled"))


class TestTaskArtifacts(unittest.TestCase):
    """Test artifact management."""
    
    def test_artifact_paths_serializable(self):
        """artifact_paths is JSON-serializable."""
        import json
        
        task = TaskRecord(
            task_id="task_010",
            task_type="export_backtest_result",
            status="succeeded",
            created_at=datetime.now(),
            started_at=datetime.now(),
            finished_at=datetime.now(),
            progress_pct=100.0,
            current_step="Complete",
            input_payload={},
            artifact_paths=["metrics.json", "trades.csv", "equity_curve.png"],
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        # Should be JSON-serializable
        artifacts_json = json.dumps(task.artifact_paths)
        restored = json.loads(artifacts_json)
        
        self.assertEqual(restored, task.artifact_paths)
    
    def test_empty_artifact_paths_valid(self):
        """Empty artifact_paths list is valid."""
        task = TaskRecord(
            task_id="task_011",
            task_type="backtest_run",
            status="succeeded",
            created_at=datetime.now(),
            started_at=datetime.now(),
            finished_at=datetime.now(),
            progress_pct=100.0,
            current_step="Complete",
            input_payload={},
            artifact_paths=[],  # Empty is valid
            error_type=None,
            error_message=None,
            error_traceback=None,
        )
        
        validate_task_record(task)


if __name__ == "__main__":
    unittest.main()
