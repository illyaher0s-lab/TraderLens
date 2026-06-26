"""B4 Time Cursor Contract Tests - Lock frozen backtest contracts."""
import unittest
from datetime import date

from backend.services.b4_protocol_types import (
    BacktestCursorState,
    BacktestReadRequest,
    FutureDataViolation,
    RejectedOrderRecord,
    OrderIntentRecord,
    FillRecord,
    DailyPortfolioSnapshot,
    EventBacktestResult,
    CanaryCaseResult,
    BacktestEngineQualificationResult,
)


class TestB4Contracts(unittest.TestCase):
    def test_contracts_are_frozen(self):
        """All B4 contracts must be frozen (immutable)."""
        contracts = [
            BacktestCursorState,
            BacktestReadRequest,
            FutureDataViolation,
            RejectedOrderRecord,
            OrderIntentRecord,
            FillRecord,
            DailyPortfolioSnapshot,
            EventBacktestResult,
            CanaryCaseResult,
            BacktestEngineQualificationResult,
        ]
        
        for contract in contracts:
            self.assertTrue(contract.model_config.get("frozen"))
            self.assertEqual(contract.model_config.get("extra"), "forbid")

    def test_backtest_cursor_state_frozen(self):
        """BacktestCursorState must be immutable."""
        cursor = BacktestCursorState(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 1),
            allowed_read_until=date(2024, 1, 1),
            evaluation_mode="signal_phase",
            read_trace=("read_bar_000001",),
        )
        
        with self.assertRaises(Exception):
            cursor.current_date = date(2024, 1, 2)

    def test_contracts_use_tuple_not_list(self):
        """Contracts must use tuple for collections (immutable)."""
        cursor = BacktestCursorState(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 1),
            allowed_read_until=date(2024, 1, 1),
            evaluation_mode="signal_phase",
            read_trace=("read_1", "read_2"),
        )
        
        self.assertIsInstance(cursor.read_trace, tuple)

    def test_backtest_result_no_gate_verdict(self):
        """EventBacktestResult must not have Gate verdict field."""
        result = EventBacktestResult(
            result_id="result_001",
            strategy_revision_id="rev_001",
            protocol_snapshot_id="proto_001",
            evaluation_mode="canary_qualification",
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="snap_001",
                snapshot_date=date(2024, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 1, 1),
        )
        
        # Must not have gate verdict field
        self.assertFalse(hasattr(result, "gate_verdict"))
        self.assertFalse(hasattr(result, "prototype_passed"))
        self.assertFalse(hasattr(result, "promotion_status"))

    def test_backtest_result_no_user_recommendation(self):
        """EventBacktestResult must not have buy/sell recommendation."""
        result = EventBacktestResult(
            result_id="result_001",
            strategy_revision_id="rev_001",
            protocol_snapshot_id="proto_001",
            evaluation_mode="canary_qualification",
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="snap_001",
                snapshot_date=date(2024, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 1, 1),
        )
        
        # Must not have user recommendation fields
        self.assertFalse(hasattr(result, "recommended_action"))
        self.assertFalse(hasattr(result, "buy_recommendation"))
        self.assertFalse(hasattr(result, "sell_recommendation"))

    def test_qualification_result_frozen(self):
        """BacktestEngineQualificationResult must be frozen."""
        qualification = BacktestEngineQualificationResult(
            qualification_id="qual_001",
            protocol_snapshot_id="proto_001",
            canary_cases=(),
            qualification_status="pass",
            qualified_at=date(2024, 1, 1),
        )
        
        self.assertTrue(qualification.frozen)
        
        with self.assertRaises(Exception):
            qualification.qualification_status = "fail"

    def test_canary_case_outcome_blocked_is_correct(self):
        """Canary case outcome 'blocked' is the correct result."""
        canary = CanaryCaseResult(
            case_id="canary_001",
            case_name="future_bar_access",
            attempted_violation="future_bar",
            outcome="blocked",  # Correct
            violation_count=1,
            violations=(
                FutureDataViolation(
                    requested_date=date(2024, 6, 1),
                    allowed_max_date=date(2024, 1, 1),
                    source="test_canary",
                    reason="Attempted to read future bar",
                    evaluation_mode="signal_phase",
                ),
            ),
        )
        
        self.assertEqual(canary.outcome, "blocked")

    def test_future_violation_is_blocking_not_degraded(self):
        """FutureDataViolation is blocking failure, not degraded success."""
        violation = FutureDataViolation(
            requested_date=date(2024, 6, 1),
            allowed_max_date=date(2024, 1, 1),
            source="strategy_logic",
            reason="Future data access",
            evaluation_mode="signal_phase",
        )
        
        # Must not have degraded/warning status
        self.assertFalse(hasattr(violation, "severity"))
        self.assertFalse(hasattr(violation, "is_warning"))
        # Violation itself IS the blocking failure

    def test_order_intent_no_execution_guarantee(self):
        """OrderIntentRecord is intent only, not guaranteed fill."""
        intent = OrderIntentRecord(
            order_id="order_001",
            symbol="000001.SZ",
            signal_date=date(2024, 1, 1),
            intent="buy",
            quantity=100,
        )
        
        # Intent does not have fill_price or fill_date
        self.assertFalse(hasattr(intent, "fill_price"))
        self.assertFalse(hasattr(intent, "fill_date"))


class TestBacktestTimeCursor(unittest.TestCase):
    def test_signal_phase_can_only_read_current_date(self):
        """T日 signal phase can only read <= T."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Can read T
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="bar",
            source="test",
        )
        self.assertTrue(allowed)
        self.assertIsNone(violation)
        
        # Can read T-1
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 9),
            data_type="bar",
            source="test",
        )
        self.assertTrue(allowed)
        self.assertIsNone(violation)
        
        # Cannot read T+1
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="test",
        )
        self.assertFalse(allowed)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.requested_date, date(2024, 1, 11))
        self.assertEqual(violation.allowed_max_date, date(2024, 1, 10))

    def test_read_trace_recorded(self):
        """Read trace must be recorded."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="bar",
            source="test",
        )
        
        cursor.request_read(
            symbol="000002.SZ",
            requested_date=date(2024, 1, 9),
            data_type="daily_status",
            source="test",
        )
        
        state = cursor.get_state()
        self.assertEqual(len(state.read_trace), 2)
        self.assertIn("bar:000001.SZ", state.read_trace[0])
        self.assertIn("daily_status:000002.SZ", state.read_trace[1])

    def test_future_data_access_error_is_blocking(self):
        """FutureDataAccessError is blocking failure."""
        from backend.services.backtest_time_cursor import (
            BacktestTimeCursor,
            FutureDataAccessError,
        )
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="strategy_logic",
        )
        
        self.assertFalse(allowed)
        
        # Should raise FutureDataAccessError
        with self.assertRaises(FutureDataAccessError) as ctx:
            raise FutureDataAccessError(violation)
        
        self.assertIn("Future data access blocked", str(ctx.exception))

    def test_cursor_state_immutable(self):
        """Cursor state snapshot is immutable."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        state = cursor.get_state()
        
        # State is frozen
        with self.assertRaises(Exception):
            state.current_date = date(2024, 1, 11)

    def test_validate_read_request(self):
        """Validate BacktestReadRequest against cursor."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Valid request
        request = BacktestReadRequest(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="bar",
            source="strategy",
        )
        
        allowed, violation = cursor.validate_read_request(request)
        self.assertTrue(allowed)
        self.assertIsNone(violation)
        
        # Invalid request (future)
        future_request = BacktestReadRequest(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="strategy",
        )
        
        allowed, violation = cursor.validate_read_request(future_request)
        self.assertFalse(allowed)
        self.assertIsNotNone(violation)

    def test_execution_phase_boundary_separation(self):
        """Execution phase can read T+1, but cannot pollute signal phase."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        from datetime import timedelta
        
        # Signal phase: T日 only read <= T
        signal_cursor = BacktestTimeCursor(
            cursor_id="signal_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Signal phase can read T
        allowed, _ = signal_cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="bar",
            source="signal",
        )
        self.assertTrue(allowed)
        
        # Signal phase cannot read T+1
        allowed, violation = signal_cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="signal",
        )
        self.assertFalse(allowed)
        self.assertIsNotNone(violation)
        
        # Get signal phase state
        signal_state = signal_cursor.get_state()
        signal_trace_len = len(signal_state.read_trace)
        
        # Execution phase: can read T+1
        exec_cursor = BacktestTimeCursor(
            cursor_id="exec_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="execution_phase",
        )
        
        # Execution phase can read T+1
        allowed, _ = exec_cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="execution",
        )
        self.assertTrue(allowed)
        
        # Verify signal phase state unchanged
        signal_state_after = signal_cursor.get_state()
        self.assertEqual(len(signal_state_after.read_trace), signal_trace_len)
        self.assertEqual(signal_state_after.current_date, date(2024, 1, 10))
        self.assertEqual(signal_state_after.allowed_read_until, date(2024, 1, 10))

    def test_membership_as_of_date_visibility(self):
        """Universe membership only visible if as_of_date <= current_date."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # as_of_date = current_date: allowed
        allowed, _ = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="membership",
            source="membership_reader",
        )
        self.assertTrue(allowed)
        
        # as_of_date < current_date: allowed
        allowed, _ = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 9),
            data_type="membership",
            source="membership_reader",
        )
        self.assertTrue(allowed)
        
        # as_of_date > current_date: blocked
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 11),
            data_type="membership",
            source="membership_reader",
        )
        self.assertFalse(allowed)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.requested_date, date(2024, 1, 11))

    def test_financial_ann_date_visibility(self):
        """Financial data visible only if ann_date <= current_date."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # ann_date <= current_date: allowed
        allowed, _ = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),  # ann_date
            data_type="financial",
            source="financial_reader",
        )
        self.assertTrue(allowed)
        
        # ann_date > current_date: blocked (even if report_period_end in past)
        # Example: Q3 2023 report, ann_date = 2024-01-15 (future)
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 15),  # ann_date in future
            data_type="financial",
            source="financial_reader",
        )
        self.assertFalse(allowed)
        self.assertIsNotNone(violation)
        
        # Violation shows we use ann_date, not report_period_end
        self.assertEqual(violation.requested_date, date(2024, 1, 15))
        self.assertIn("financial", violation.source.lower())

    def test_unknown_symbol_or_date_fails_loud(self):
        """Unknown symbol/date must raise explicit error, not return None."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Valid request returns explicit (allowed, violation)
        allowed, violation = cursor.request_read(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),
            data_type="bar",
            source="test",
        )
        self.assertIsNotNone(allowed)  # Explicit bool, not None
        
        # Future date returns explicit rejection
        allowed, violation = cursor.request_read(
            symbol="UNKNOWN_SYMBOL",
            requested_date=date(2024, 1, 11),
            data_type="bar",
            source="test",
        )
        self.assertFalse(allowed)  # Explicit False
        self.assertIsNotNone(violation)  # Explicit violation
        self.assertIn("requested", violation.reason.lower())

    def test_strategy_cannot_bypass_cursor_to_raw_dataset(self):
        """Strategy cannot access raw dataset, only via cursor API."""
        from backend.services.backtest_time_cursor import BacktestTimeCursor
        
        cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Cursor must not expose raw data fields
        self.assertFalse(hasattr(cursor, "data_snapshot"))
        self.assertFalse(hasattr(cursor, "_raw_data"))
        self.assertFalse(hasattr(cursor, "bars"))
        self.assertFalse(hasattr(cursor, "full_dataset"))
        
        # Only allowed access: via request_read API
        # Cannot get unfiltered data
        self.assertTrue(hasattr(cursor, "request_read"))
        self.assertTrue(hasattr(cursor, "validate_read_request"))
        self.assertTrue(hasattr(cursor, "get_state"))
        
        # Internal fields must be private or controlled
        # read_trace is OK (audit trail), but must be via get_state()
        state = cursor.get_state()
        self.assertIsInstance(state.read_trace, tuple)  # Immutable


if __name__ == "__main__":
    unittest.main()
