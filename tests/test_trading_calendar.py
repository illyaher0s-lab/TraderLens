from datetime import date
from pathlib import Path
from unittest import TestCase

from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.trading_calendar import TradingCalendar


class TestTradingCalendar(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = GoldenCaseDataSource(Path(__file__).parent / "golden_cases")
        cls.calendar = TradingCalendar(cls.data_source)

    def test_all_trading_dates_returns_sorted_unique_dates_from_all_symbols(self):
        """
        Trading calendar must be the sorted union of all dates present in the data source.
        """
        all_dates = self.calendar.all_trading_dates()
        self.assertIsInstance(all_dates, list)
        self.assertTrue(len(all_dates) > 0, "Golden Case must contain at least one trading date")
        self.assertEqual(all_dates, sorted(set(all_dates)), "dates must be sorted and unique")

        # verify these are real dates from the Golden Case
        symbols = self.data_source.symbols()
        expected_dates = set()
        for symbol in symbols:
            bars = self.data_source.get_daily_bars(symbol)
            expected_dates.update(bar.date for bar in bars)

        self.assertEqual(set(all_dates), expected_dates)

    def test_is_trading_day_returns_true_for_known_date(self):
        """
        is_trading_day must return True for dates present in the data source.
        """
        known_date = date(2024, 1, 2)
        self.assertTrue(self.calendar.is_trading_day(known_date))

    def test_is_trading_day_returns_false_for_unknown_date(self):
        """
        is_trading_day must return False for dates not in the data source.
        """
        unknown_date = date(2020, 1, 1)
        self.assertFalse(self.calendar.is_trading_day(unknown_date))

    def test_next_trading_day_returns_following_trading_date(self):
        """
        next_trading_day must return the immediate next trading date from the calendar.
        """
        base_date = date(2024, 1, 2)
        expected_next = date(2024, 1, 3)
        self.assertEqual(self.calendar.next_trading_day(base_date), expected_next)

    def test_next_trading_day_fails_loud_if_no_following_date_exists(self):
        """
        next_trading_day must raise ValueError if called on the last trading date.
        """
        all_dates = self.calendar.all_trading_dates()
        last_date = all_dates[-1]
        with self.assertRaises(ValueError) as ctx:
            self.calendar.next_trading_day(last_date)
        self.assertIn("no trading day after", str(ctx.exception).lower())

    def test_previous_trading_day_returns_prior_trading_date(self):
        """
        previous_trading_day must return the immediate prior trading date from the calendar.
        """
        base_date = date(2024, 1, 3)
        expected_prev = date(2024, 1, 2)
        self.assertEqual(self.calendar.previous_trading_day(base_date), expected_prev)

    def test_previous_trading_day_fails_loud_if_no_prior_date_exists(self):
        """
        previous_trading_day must raise ValueError if called on the first trading date.
        """
        all_dates = self.calendar.all_trading_dates()
        first_date = all_dates[0]
        with self.assertRaises(ValueError) as ctx:
            self.calendar.previous_trading_day(first_date)
        self.assertIn("no trading day before", str(ctx.exception).lower())

    def test_next_trading_day_fails_loud_if_input_is_not_a_trading_day(self):
        """
        next_trading_day must fail loudly if the input date is not in the trading calendar.
        """
        non_trading_day = date(2020, 1, 1)
        with self.assertRaises(ValueError) as ctx:
            self.calendar.next_trading_day(non_trading_day)
        self.assertIn("not a trading day", str(ctx.exception).lower())

    def test_previous_trading_day_fails_loud_if_input_is_not_a_trading_day(self):
        """
        previous_trading_day must fail loudly if the input date is not in the trading calendar.
        """
        non_trading_day = date(2020, 1, 1)
        with self.assertRaises(ValueError) as ctx:
            self.calendar.previous_trading_day(non_trading_day)
        self.assertIn("not a trading day", str(ctx.exception).lower())
