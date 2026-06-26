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


if __name__ == "__main__":
    unittest.main()
