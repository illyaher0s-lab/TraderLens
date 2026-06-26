from __future__ import annotations
from collections import deque

from contracts.stable import Trade, RoundTrip


class Lot:
    """
    Represents an open buy lot.
    
    Tracks remaining quantity and cost basis for FIFO matching.
    """
    def __init__(self, trade: Trade):
        self.trade = trade
        self.remaining_quantity = trade.quantity
        # Buy cost per share: (gross_amount + commission + transfer_fee) / quantity
        # Proportionally allocate costs to each share
        total_cost = trade.gross_amount + trade.commission + trade.transfer_fee
        self.cost_per_share = total_cost / trade.quantity


class LotMatcher:
    """
    FIFO lot matching for round-trip PnL calculation.
    
    Usage:
        matcher = LotMatcher()
        for trade in sorted_trades:
            round_trips = matcher.process_trade(trade)
        
        # Access results
        completed_round_trips = matcher.completed_round_trips
        unmatched_sells_count = matcher.unmatched_sells_count
    """
    def __init__(self):
        # symbol → deque of Lot (FIFO queue)
        self.open_lots: dict[str, deque[Lot]] = {}
        
        # Results
        self.completed_round_trips: list[RoundTrip] = []
        self.unmatched_sells_count: int = 0
    
    def process_trade(self, trade: Trade) -> list[RoundTrip]:
        """
        Process a trade and return completed round-trips.
        
        Returns:
            List of RoundTrip objects generated from this trade.
        """
        if trade.direction == "buy":
            return self._process_buy(trade)
        elif trade.direction == "sell":
            return self._process_sell(trade)
        else:
            return []
    
    def _process_buy(self, trade: Trade) -> list[RoundTrip]:
        """Add a buy lot to open lots queue."""
        if trade.symbol not in self.open_lots:
            self.open_lots[trade.symbol] = deque()
        
        self.open_lots[trade.symbol].append(Lot(trade))
        return []  # Buy doesn't close round-trips
    
    def _process_sell(self, trade: Trade) -> list[RoundTrip]:
        """
        Match sell trade against open buy lots (FIFO).
        
        Returns list of completed round-trips.
        """
        if trade.symbol not in self.open_lots or not self.open_lots[trade.symbol]:
            # Sell without buy: record warning but don't generate round-trip
            self.unmatched_sells_count += 1
            return []
        
        lots = self.open_lots[trade.symbol]
        remaining_sell_qty = trade.quantity
        round_trips = []
        
        # Sell proceeds per share (after commission, stamp duty, and transfer fee)
        sell_total_proceeds = trade.gross_amount - trade.commission - trade.stamp_duty - trade.transfer_fee
        sell_proceeds_per_share = sell_total_proceeds / trade.quantity
        
        round_trip_index = 0
        
        while remaining_sell_qty > 0 and lots:
            lot = lots[0]
            matched_qty = min(remaining_sell_qty, lot.remaining_quantity)
            
            # Calculate PnL for this matched segment
            buy_cost = lot.cost_per_share * matched_qty
            sell_proceeds = sell_proceeds_per_share * matched_qty
            realized_pnl = sell_proceeds - buy_cost
            
            holding_days = (trade.trade_date - lot.trade.trade_date).days
            
            round_trip = RoundTrip(
                round_trip_id=f"rt:{trade.trade_id}:{round_trip_index}",
                symbol=trade.symbol,
                buy_trade_id=lot.trade.trade_id,
                buy_date=lot.trade.trade_date,
                buy_price=lot.trade.price,
                buy_trade_quantity=lot.trade.quantity,
                matched_quantity=matched_qty,
                buy_cost=buy_cost,
                sell_trade_id=trade.trade_id,
                sell_date=trade.trade_date,
                sell_price=trade.price,
                sell_trade_quantity=trade.quantity,
                sell_proceeds=sell_proceeds,
                realized_pnl=realized_pnl,
                holding_days=holding_days,
            )
            
            round_trips.append(round_trip)
            self.completed_round_trips.append(round_trip)
            
            # Update lot
            lot.remaining_quantity -= matched_qty
            remaining_sell_qty -= matched_qty
            round_trip_index += 1
            
            # Remove lot if fully consumed
            if lot.remaining_quantity == 0:
                lots.popleft()
        
        # If sell quantity exceeds available lots, record warning
        if remaining_sell_qty > 0:
            self.unmatched_sells_count += 1
        
        return round_trips
