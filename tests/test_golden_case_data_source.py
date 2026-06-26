from datetime import date
from pathlib import Path
import unittest


class GoldenCaseDataSourceTests(unittest.TestCase):
    def test_loads_all_symbols_and_aligns_daily_bars_with_statuses(self):
        from backend.app.golden_cases import GoldenCaseDataSource

        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        self.assertEqual(source.symbols(), ["000001.SZ", "000002.SZ", "300750.SZ", "600000.SH", "600519.SH"])
        for symbol in source.symbols():
            with self.subTest(symbol=symbol):
                bars = source.get_daily_bars(symbol)
                statuses = source.get_daily_statuses(symbol)
                self.assertEqual([bar.date for bar in bars], [status.date for status in statuses])
                self.assertGreaterEqual(len(bars), 3)

    def test_can_query_single_symbol_date_for_trade_constraints(self):
        from backend.app.golden_cases import GoldenCaseDataSource

        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        suspended = source.get_daily_status("600000.SH", date(2024, 1, 3))
        limit_down = source.get_daily_status("000002.SZ", date(2024, 1, 3))
        limit_up = source.get_daily_status("600519.SH", date(2024, 1, 3))

        self.assertTrue(suspended.is_suspended)
        self.assertTrue(limit_down.is_limit_down)
        self.assertTrue(limit_up.is_limit_up)
        self.assertEqual(source.get_daily_bar("000001.SZ", date(2024, 1, 2)).symbol, "000001.SZ")

    def test_unknown_symbol_or_date_fails_loudly(self):
        from backend.app.golden_cases import GoldenCaseDataSource

        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        with self.assertRaises(KeyError):
            source.get_daily_bars("999999.SZ")
        with self.assertRaises(KeyError):
            source.get_daily_status("000001.SZ", date(2030, 1, 1))

    def test_get_price_returns_closing_price_from_daily_bar(self):
        """
        get_price implements PriceProvider protocol and returns closing price.
        """
        from backend.app.golden_cases import GoldenCaseDataSource

        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        price = source.get_price("000001.SZ", date(2024, 1, 2))
        bar = source.get_daily_bar("000001.SZ", date(2024, 1, 2))
        
        self.assertEqual(price, bar.close)
        self.assertIsInstance(price, float)
        self.assertGreater(price, 0)


if __name__ == "__main__":
    unittest.main()
