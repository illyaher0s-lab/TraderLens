from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.app.fixed_fixture import FixedFixtureDataSource
from backend.scripts.run_strategy_suite import run_single_strategy
from strategy_core.trading_calendar import TradingCalendar


class TestStrategySuiteDiagnostics(unittest.TestCase):
    def test_single_strategy_summary_includes_exit_diagnostic_fields(self):
        """
        Suite summaries must expose exit diagnostics directly.

        This prevents diagnosing exit behavior by inferring from trades alone.
        """
        data_source = FixedFixtureDataSource(Path("tests/fixed_fixture"))
        calendar = TradingCalendar(data_source)
        strategy_file = Path("tests/diagnostic_strategies/holding_days_exit.yaml")

        with TemporaryDirectory() as tmpdir:
            result = run_single_strategy(
                strategy_file=strategy_file,
                data_source=data_source,
                calendar=calendar,
                output_path=Path(tmpdir),
            )

        expected_fields = [
            "entry_signal_count",
            "exit_signal_count",
            "buy_order_count",
            "sell_order_count",
            "buy_fill_count",
            "sell_fill_count",
            "exit_rejected_count",
            "completed_round_trips",
            "exit_triggered_rules",
        ]
        for field in expected_fields:
            self.assertIn(field, result)

        self.assertGreater(result["entry_signal_count"], 0)
        self.assertGreater(result["exit_signal_count"], 0)
        self.assertGreater(result["sell_fill_count"], 0)
        self.assertIn("holding_days >= 5", result["exit_triggered_rules"])


if __name__ == "__main__":
    unittest.main()
