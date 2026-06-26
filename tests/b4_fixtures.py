"""B4 test fixtures for guaranteed rejection scenarios."""
from datetime import date
from contracts.stable import DailyBar, DailyStatus


def create_suspended_stock_data():
    """
    Create minimal data for a suspended stock scenario.
    
    Returns:
        tuple: (bars, statuses) for symbol "999999.SZ" on 2024-01-10
               Stock is suspended - guaranteed to reject buy/sell orders
    """
    symbol = "999999.SZ"
    trade_date = date(2024, 1, 10)
    
    # Suspended bar (zero volume)
    bar = DailyBar(
        date=trade_date,
        symbol=symbol,
        open=10.0,
        high=10.0,
        low=10.0,
        close=10.0,
        volume=0,  # Suspended - no volume
        amount=0.0,
        adj_factor=1.0,
    )
    
    # Suspended status
    status = DailyStatus(
        date=trade_date,
        symbol=symbol,
        is_st=False,
        is_suspended=True,  # Suspended!
        is_limit_up=False,
        is_limit_down=False,
        suspend_reason="major_announcement",
    )
    
    return symbol, trade_date, bar, status


def create_rejection_test_data_source():
    """
    Create a minimal data source for testing rejection scenario.
    
    Returns a data source with:
    - One stock "999999.SZ"
    - Three days: 2024-01-08, 2024-01-09 (normal), 2024-01-10 (suspended)
    - T-1 close=9.0, T close=11.0 → MA(2)=10.0 → 11.0>10.0 triggers entry
    - Guarantees rejection on T+1 (2024-01-10)
    """
    
    class RejectionTestDataSource:
        def __init__(self):
            self.symbol = "999999.SZ"
            self.pre_signal_date = date(2024, 1, 8)
            self.signal_date = date(2024, 1, 9)
            self.execution_date = date(2024, 1, 10)
            
            # T-1: for MA calculation, close = 9.0
            self.bar_t_minus_1 = DailyBar(
                date=self.pre_signal_date,
                symbol=self.symbol,
                open=9.0, high=9.5, low=8.5, close=9.0,
                volume=1000000, amount=9000000.0, adj_factor=1.0,
            )
            
            self.status_t_minus_1 = DailyStatus(
                date=self.pre_signal_date,
                symbol=self.symbol,
                is_st=False, is_suspended=False,
                is_limit_up=False, is_limit_down=False,
            )
            
            # T (signal date): close = 11.0 → triggers MA(2) rule
            self.bar_t = DailyBar(
                date=self.signal_date,
                symbol=self.symbol,
                open=10.0, high=11.5, low=9.5, close=11.0,
                volume=1000000, amount=10500000.0, adj_factor=1.0,
            )
            
            self.status_t = DailyStatus(
                date=self.signal_date,
                symbol=self.symbol,
                is_st=False, is_suspended=False,
                is_limit_up=False, is_limit_down=False,
            )
            
            # T+1 (execution date): SUSPENDED
            self.bar_t1 = DailyBar(
                date=self.execution_date,
                symbol=self.symbol,
                open=11.0, high=11.0, low=11.0, close=11.0,
                volume=0, amount=0.0, adj_factor=1.0,  # No volume
            )
            
            self.status_t1 = DailyStatus(
                date=self.execution_date,
                symbol=self.symbol,
                is_st=False, is_suspended=True,  # SUSPENDED!
                is_limit_up=False, is_limit_down=False,
                suspend_reason="test_rejection",
            )
        
        def symbols(self):
            return [self.symbol]
        
        def get_daily_bars(self, symbol):
            if symbol != self.symbol:
                return []
            return [self.bar_t_minus_1, self.bar_t, self.bar_t1]
        
        def get_daily_bar(self, symbol, trade_date):
            if symbol != self.symbol:
                raise KeyError(f"No data for {symbol}")
            if trade_date == self.pre_signal_date:
                return self.bar_t_minus_1
            elif trade_date == self.signal_date:
                return self.bar_t
            elif trade_date == self.execution_date:
                return self.bar_t1
            raise KeyError(f"No bar for {symbol} on {trade_date}")
        
        def get_status(self, symbol, as_of_date):
            return self.get_daily_status(symbol, as_of_date)
        
        def get_daily_status(self, symbol, trade_date):
            if symbol != self.symbol:
                raise KeyError(f"No data for {symbol}")
            if trade_date == self.pre_signal_date:
                return self.status_t_minus_1
            elif trade_date == self.signal_date:
                return self.status_t
            elif trade_date == self.execution_date:
                return self.status_t1
            raise KeyError(f"No status for {symbol} on {trade_date}")
        
        def get_price(self, symbol, as_of_date):
            bar = self.get_daily_bar(symbol, as_of_date)
            return bar.close
    
    return RejectionTestDataSource()
