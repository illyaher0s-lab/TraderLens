from __future__ import annotations

from datetime import date

from backend.app.golden_cases import GoldenCaseDataSource


class TradingCalendar:
    """
    Deterministic trading calendar extracted from Golden Case data.
    Provides trading date queries without external data sources.
    """

    def __init__(self, data_source: GoldenCaseDataSource):
        self._dates = self._extract_trading_dates(data_source)
        self._date_set = set(self._dates)
        self._date_to_index = {d: i for i, d in enumerate(self._dates)}

    def all_trading_dates(self) -> list[date]:
        """Return all trading dates in sorted order."""
        return list(self._dates)

    def is_trading_day(self, target_date: date) -> bool:
        """Check if the given date is a trading day."""
        return target_date in self._date_set

    def next_trading_day(self, current_date: date) -> date:
        """
        Return the next trading day after current_date.
        Raises ValueError if current_date is not a trading day or is the last trading day.
        """
        if current_date not in self._date_to_index:
            raise ValueError(f"not a trading day: {current_date}")

        current_index = self._date_to_index[current_date]
        if current_index + 1 >= len(self._dates):
            raise ValueError(f"no trading day after {current_date}")

        return self._dates[current_index + 1]

    def previous_trading_day(self, current_date: date) -> date:
        """
        Return the previous trading day before current_date.
        Raises ValueError if current_date is not a trading day or is the first trading day.
        """
        if current_date not in self._date_to_index:
            raise ValueError(f"not a trading day: {current_date}")

        current_index = self._date_to_index[current_date]
        if current_index == 0:
            raise ValueError(f"no trading day before {current_date}")

        return self._dates[current_index - 1]

    @staticmethod
    def _extract_trading_dates(data_source: GoldenCaseDataSource) -> list[date]:
        """Extract sorted unique trading dates from all symbols in the data source."""
        all_dates: set[date] = set()
        for symbol in data_source.symbols():
            bars = data_source.get_daily_bars(symbol)
            all_dates.update(bar.date for bar in bars)

        if not all_dates:
            raise ValueError("data source contains no trading dates")

        return sorted(all_dates)
