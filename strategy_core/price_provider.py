from __future__ import annotations

from datetime import date
from typing import Protocol


class PriceProvider(Protocol):
    """
    Price query interface for order generation.
    Decouples order generator from specific data sources.
    """

    def get_price(self, symbol: str, target_date: date) -> float:
        """
        Return the closing price for the given symbol on the target date.
        
        Raises:
            KeyError: if symbol or date is not available
            ValueError: if price data is invalid
        """
        ...
