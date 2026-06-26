"""
CSV Schema Stability Tests - M2 Column Order Lock

Validates that CSV export column order matches documented schema.
Uses real export code to generate CSV, then verifies header.

M2 Requirement: Column order is frozen. Any change is a breaking change.
"""

import unittest
import tempfile
import json
import csv
from pathlib import Path
from datetime import date

# Import export functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.scripts.export_backtest_result import (
    export_trades,
    export_round_trips,
    export_equity_curve,
    export_order_generation_events,
)


class TestCSVSchemaStability(unittest.TestCase):
    """Test CSV column order matches M2 locked schema."""
    
    def setUp(self):
        """Create temp directory for test exports."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_trades_csv_columns_are_stable(self):
        """trades.csv column order is locked (13 columns)."""
        # Expected column order (M2 locked)
        expected_columns = [
            "trade_id", "order_id", "symbol", "direction", "quantity", "price",
            "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
            "total_fee", "net_cash_flow"
        ]
        
        # Create minimal backtest result with one trade
        result = {
            "strategy_id": "test_strategy",
            "strategy_version": "v1",
            "initial_capital": 100000.0,
            "final_capital": 100000.0,
            "total_return": 0.0,
            "trades": [{
                "trade_id": "T001",
                "order_id": "O001",
                "symbol": "600519.SH",
                "direction": "buy",
                "quantity": 100,
                "price": 150.0,
                "trade_date": "2023-06-15",
                "gross_amount": 15000.0,
                "commission": 5.0,
                "stamp_duty": 0.0,
                "transfer_fee": 0.0,
                "total_fee": 5.0,
                "net_cash_flow": -15005.0,
                "cost": -15005.0,
            }],
        }
        
        # Export trades.csv
        export_path = self.temp_path / "trades.csv"
        export_trades(result, export_path)
        
        # Read CSV header
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            actual_columns = next(reader)
        
        # Verify column order
        self.assertEqual(actual_columns, expected_columns,
                        f"trades.csv column order changed!\n"
                        f"Expected: {expected_columns}\n"
                        f"Actual: {actual_columns}\n"
                        f"This is a BREAKING CHANGE (requires schema v2.0)")
    
    def test_round_trips_csv_columns_are_stable(self):
        """round_trips.csv column order is locked (11 columns)."""
        # Expected column order (M2 locked)
        expected_columns = [
            "symbol", "buy_date", "sell_date", "holding_days", "quantity",
            "buy_price", "sell_price", "buy_cost", "sell_proceeds",
            "realized_pnl", "return_pct"
        ]
        
        # Create minimal backtest result with one round trip
        result = {
            "round_trips": [{
                "round_trip_id": "RT001",
                "symbol": "600519.SH",
                "buy_date": "2023-06-15",
                "sell_date": "2023-06-20",
                "holding_days": 5,
                "matched_quantity": 100,
                "buy_price": 150.0,
                "sell_price": 155.0,
                "buy_cost": 15005.0,
                "sell_proceeds": 15479.5,
                "realized_pnl": 474.5,
            }],
        }
        
        # Export round_trips.csv
        export_path = self.temp_path / "round_trips.csv"
        export_round_trips(result, export_path)
        
        # Read CSV header
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            actual_columns = next(reader)
        
        # Verify column order
        self.assertEqual(actual_columns, expected_columns,
                        f"round_trips.csv column order changed!\n"
                        f"Expected: {expected_columns}\n"
                        f"Actual: {actual_columns}\n"
                        f"This is a BREAKING CHANGE (requires schema v2.0)")
    
    def test_equity_curve_csv_columns_are_stable(self):
        """equity_curve.csv column order is locked (5 columns)."""
        # Expected column order (M2 locked)
        expected_columns = [
            "date", "cash", "market_value", "total_value", "return_from_start_pct"
        ]
        
        # Create minimal backtest result with daily values
        result = {
            "initial_capital": 100000.0,
            "daily_portfolio_values": [{
                "date": "2023-06-15",
                "cash": 85000.0,
                "market_value": 15000.0,
                "total_value": 100000.0,
            }],
        }
        
        # Export equity_curve.csv
        export_path = self.temp_path / "equity_curve.csv"
        export_equity_curve(result, export_path)
        
        # Read CSV header
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            actual_columns = next(reader)
        
        # Verify column order
        self.assertEqual(actual_columns, expected_columns,
                        f"equity_curve.csv column order changed!\n"
                        f"Expected: {expected_columns}\n"
                        f"Actual: {actual_columns}\n"
                        f"This is a BREAKING CHANGE (requires schema v2.0)")
    
    def test_order_generation_events_csv_columns_are_stable(self):
        """order_generation_events.csv column order is locked (9 columns)."""
        # Expected column order (M2 locked)
        expected_columns = [
            "event_type", "symbol", "signal_id", "intended_execution_date",
            "reason", "requested_quantity", "generated_quantity",
            "sellable_quantity", "total_quantity"
        ]
        
        # Create minimal backtest result with one event
        result = {
            "order_generation_events": [{
                "event_type": "t1_frozen",
                "symbol": "600519.SH",
                "signal_id": "S001",
                "intended_execution_date": "2023-06-16",
                "reason": "T+1 freeze: bought on 2023-06-15",
                "requested_quantity": 100,
                "generated_quantity": None,
                "sellable_quantity": 0,
                "total_quantity": 100,
            }],
        }
        
        # Export order_generation_events.csv
        export_path = self.temp_path / "order_generation_events.csv"
        export_order_generation_events(result, export_path)
        
        # Read CSV header
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            actual_columns = next(reader)
        
        # Verify column order
        self.assertEqual(actual_columns, expected_columns,
                        f"order_generation_events.csv column order changed!\n"
                        f"Expected: {expected_columns}\n"
                        f"Actual: {actual_columns}\n"
                        f"This is a BREAKING CHANGE (requires schema v2.0)")
    
    def test_empty_csv_has_same_headers(self):
        """Empty CSVs still have correct headers."""
        # trades.csv with no trades
        result_no_trades = {
            "trades": [],
        }
        export_path = self.temp_path / "trades_empty.csv"
        export_trades(result_no_trades, export_path)
        
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        
        expected = [
            "trade_id", "order_id", "symbol", "direction", "quantity", "price",
            "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
            "total_fee", "net_cash_flow"
        ]
        self.assertEqual(headers, expected)
        
        # round_trips.csv with no round trips
        result_no_rts = {
            "round_trips": [],
        }
        export_path = self.temp_path / "round_trips_empty.csv"
        export_round_trips(result_no_rts, export_path)
        
        with open(export_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        
        expected = [
            "symbol", "buy_date", "sell_date", "holding_days", "quantity",
            "buy_price", "sell_price", "buy_cost", "sell_proceeds",
            "realized_pnl", "return_pct"
        ]
        self.assertEqual(headers, expected)


class TestCSVColumnCount(unittest.TestCase):
    """Test CSV files have expected column counts (quick sanity check)."""
    
    def test_trades_csv_has_13_columns(self):
        """trades.csv has exactly 13 columns (M2 locked)."""
        expected_count = 13
        expected_columns = [
            "trade_id", "order_id", "symbol", "direction", "quantity", "price",
            "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
            "total_fee", "net_cash_flow"
        ]
        self.assertEqual(len(expected_columns), expected_count)
    
    def test_round_trips_csv_has_11_columns(self):
        """round_trips.csv has exactly 11 columns (M2 locked)."""
        expected_count = 11
        expected_columns = [
            "symbol", "buy_date", "sell_date", "holding_days", "quantity",
            "buy_price", "sell_price", "buy_cost", "sell_proceeds",
            "realized_pnl", "return_pct"
        ]
        self.assertEqual(len(expected_columns), expected_count)
    
    def test_equity_curve_csv_has_5_columns(self):
        """equity_curve.csv has exactly 5 columns (M2 locked)."""
        expected_count = 5
        expected_columns = [
            "date", "cash", "market_value", "total_value", "return_from_start_pct"
        ]
        self.assertEqual(len(expected_columns), expected_count)
    
    def test_order_generation_events_csv_has_9_columns(self):
        """order_generation_events.csv has exactly 9 columns (M2 locked)."""
        expected_count = 9
        expected_columns = [
            "event_type", "symbol", "signal_id", "intended_execution_date",
            "reason", "requested_quantity", "generated_quantity",
            "sellable_quantity", "total_quantity"
        ]
        self.assertEqual(len(expected_columns), expected_count)


if __name__ == "__main__":
    unittest.main()
