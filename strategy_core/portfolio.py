from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from contracts.stable import FrozenLot


@dataclass
class Position:
    """
    Position record for a single symbol with T+1 freeze tracking.
    
    T+1 rule: shares bought on day T can only be sold on day T+1.
    
    Invariant: quantity == sellable_quantity + sum(frozen_lots.quantity)
    """
    symbol: str
    quantity: int  # Total quantity (sellable + frozen)
    sellable_quantity: int  # Quantity available for selling
    frozen_lots: list[FrozenLot] = field(default_factory=list)  # Lots frozen by T+1 rule
    avg_cost: float = 0.0
    last_price: float = 0.0
    oldest_buy_date: date | None = None
    
    def __post_init__(self):
        """Validate position invariants."""
        self._validate_invariants()
    
    def _validate_invariants(self):
        """Ensure position state is consistent."""
        frozen_total = sum(lot.quantity for lot in self.frozen_lots)
        if self.quantity != self.sellable_quantity + frozen_total:
            raise ValueError(
                f"Position invariant violated: quantity={self.quantity}, "
                f"sellable={self.sellable_quantity}, frozen_total={frozen_total}"
            )
        if self.sellable_quantity < 0:
            raise ValueError(f"sellable_quantity cannot be negative: {self.sellable_quantity}")
        if self.sellable_quantity > self.quantity:
            raise ValueError(f"sellable_quantity ({self.sellable_quantity}) cannot exceed quantity ({self.quantity})")
        for lot in self.frozen_lots:
            if lot.quantity <= 0:
                raise ValueError(f"Frozen lot quantity must be positive: {lot.quantity}")
    
    def market_value(self) -> float:
        """Current market value of this position."""
        return self.quantity * self.last_price
    
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss for this position."""
        return (self.last_price - self.avg_cost) * self.quantity


@dataclass
class PortfolioState:
    """
    Portfolio state tracking cash and positions.
    Stateful container updated by backtest engine.
    """
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    
    def available_capital(self) -> float:
        """Available capital for new orders."""
        return self.cash
    
    def market_value(self) -> float:
        """Total market value of all positions."""
        return sum(pos.market_value() for pos in self.positions.values())
    
    def total_value(self) -> float:
        """Total portfolio value = cash + market value."""
        return self.cash + self.market_value()
    
    def validate_invariants(self) -> None:
        """
        Validate portfolio invariants.
        
        Raises:
            ValueError: If any invariant is violated
        """
        # Cash must be non-negative (no margin trading in V1)
        if self.cash < 0:
            raise ValueError(
                f"Portfolio invariant violated: cash < 0 (cash={self.cash:.2f}). "
                "Margin trading is not supported in V1."
            )
        
        # All positions must have valid invariants
        for symbol, position in self.positions.items():
            try:
                position._validate_invariants()
            except ValueError as e:
                raise ValueError(f"Position {symbol} invariant violated: {e}")
    
    def update_position_prices(self, prices: dict[str, float]) -> None:
        """Update last_price for positions based on current market prices."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].last_price = price
    
    def unlock_frozen_lots(self, current_date: date) -> None:
        """
        Unlock frozen lots that have reached their unlock_date.
        
        Called at the start of each trading day before processing signals.
        Must be called with a valid trading date from the trading calendar.
        """
        for symbol in list(self.positions.keys()):
            position = self.positions[symbol]
            
            unlocked_quantity = 0
            remaining_frozen = []
            
            for frozen_lot in position.frozen_lots:
                if frozen_lot.unlock_date <= current_date:
                    # Unlock this lot
                    unlocked_quantity += frozen_lot.quantity
                else:
                    # Still frozen
                    remaining_frozen.append(frozen_lot)
            
            if unlocked_quantity > 0:
                position.sellable_quantity += unlocked_quantity
                position.frozen_lots = remaining_frozen
                position._validate_invariants()
    
    def add_position(self, symbol: str, quantity: int, price: float, buy_date: date, calendar) -> None:
        """
        Add to position with T+1 freeze.
        
        Newly bought shares are frozen until next trading day.
        Requires trading calendar to calculate unlock_date.
        """
        if calendar is None:
            raise ValueError("Trading calendar is required for T+1 freeze tracking")
        
        # Calculate unlock date (next trading day)
        unlock_date = calendar.next_trading_day(buy_date)
        
        if symbol in self.positions:
            position = self.positions[symbol]
            
            # Update average cost
            total_cost = position.avg_cost * position.quantity + price * quantity
            position.quantity += quantity
            position.avg_cost = total_cost / position.quantity
            
            # Add frozen lot (sorted by unlock_date for FIFO)
            position.frozen_lots.append(FrozenLot(quantity=quantity, unlock_date=unlock_date))
            position.frozen_lots.sort(key=lambda lot: lot.unlock_date)
            if position.oldest_buy_date is None or buy_date < position.oldest_buy_date:
                position.oldest_buy_date = buy_date
            position._validate_invariants()
        else:
            # New position, all frozen
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                sellable_quantity=0,  # All frozen initially
                frozen_lots=[FrozenLot(quantity=quantity, unlock_date=unlock_date)],
                avg_cost=price,
                last_price=price,
                oldest_buy_date=buy_date,
            )
    
    def reduce_position(self, symbol: str, quantity: int) -> None:
        """
        Reduce position (sell).
        
        Only reduces sellable_quantity; frozen_lots are unaffected.
        Caller must verify sellable_quantity >= quantity before calling.
        """
        if symbol not in self.positions:
            raise ValueError(f"No position to reduce for {symbol}")
        
        position = self.positions[symbol]
        
        if quantity > position.sellable_quantity:
            raise ValueError(
                f"Cannot sell {quantity} shares of {symbol}; "
                f"only {position.sellable_quantity} sellable "
                f"(total {position.quantity}, frozen {position.quantity - position.sellable_quantity})"
            )
        
        position.quantity -= quantity
        position.sellable_quantity -= quantity
        
        # Remove position if empty
        if position.quantity == 0:
            del self.positions[symbol]
        else:
            position._validate_invariants()
