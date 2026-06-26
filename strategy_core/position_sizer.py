from __future__ import annotations


class PositionSizer:
    """
    Stateless position sizing tool.
    Calculates A-share lot-based quantity from available capital, position ratio, and price.
    """

    def __init__(self, position_ratio: float = 0.2, lot_size: int = 100):
        """
        position_ratio: fraction of available capital to use per position (0, 1]
        lot_size: minimum trading unit for A-shares (default 100 shares)
        """
        if not 0 < position_ratio <= 1:
            raise ValueError("position_ratio must be in (0, 1]")
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")

        self._ratio = position_ratio
        self._lot = lot_size

    def calculate_quantity(
        self,
        price: float,
        available_capital: float,
    ) -> int:
        """
        Calculate buyable quantity (A-share lot multiples).

        Returns:
        - >= lot_size: buyable lots (rounded down to whole lots)
        - 0: insufficient capital for one lot

        Note: This is planned quantity, not guaranteed fill quantity.
        Actual execution date price may differ; backtest engine must re-verify capital sufficiency.
        """
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")
        if available_capital < 0:
            raise ValueError(f"available_capital cannot be negative, got {available_capital}")

        budget = available_capital * self._ratio
        shares = int(budget / price)
        lots = shares // self._lot
        return lots * self._lot
