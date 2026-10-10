"""Task 3B Corrective-2: Formal PIT Partition Adapter 完整性与开盘成交边界 RED tests.

无 skip/xfail，所有测试用真实正式分区数据。
"""
import unittest
from datetime import date
from pathlib import Path
import shutil
import tempfile

REPO_ROOT = Path(__file__).parent.parent


class TestFormalPartitionCompleteness(unittest.TestCase):
    """RED: 分区完整性检查。"""
    
    def test_001_missing_daily_partition_fails_loud(self):
        """缺失 daily 分区必须 fail loud。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 1990-01-01 分区不存在
        with self.assertRaises(FileNotFoundError) as cm:
            adapter.get_daily_bar("000001.SZ", date(1990, 1, 1))
        
        self.assertIn("daily", str(cm.exception).lower())
    
    def test_002_adj_factor_from_formal_partition(self):
        """adj_factor 从正式分区读取，不能是 stub 1.0。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 2016-01-04 有真实 adj_factor
        bar = adapter.get_daily_bar("000001.SZ", date(2016, 1, 4))
        
        # 不能是 stub 1.0
        self.assertNotEqual(bar.adj_factor, 1.0)
        self.assertIsInstance(bar.adj_factor, float)
        self.assertGreater(bar.adj_factor, 0)
    
    def test_003_missing_adj_factor_for_symbol_fails_loud(self):
        """证券无 adj_factor 记录必须 fail loud。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 假设 INVALID.SZ 不存在（用真实日期但虚假代码）
        with self.assertRaises((KeyError, FileNotFoundError)):
            adapter.get_daily_bar("INVALID.SZ", date(2016, 1, 4))

    def test_004_missing_required_status_partition_fails_loud(self):
        """A missing suspend_d, stock_st, or stk_limit file is not an empty status."""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        execution_date = date(2016, 1, 4)
        partition_names = ("suspend_d", "stock_st", "stk_limit")

        for missing_partition in partition_names:
            with self.subTest(missing_partition=missing_partition), tempfile.TemporaryDirectory() as temp_dir:
                adapter = FormalPITPartitionAdapter(REPO_ROOT)
                source_root = adapter.formal_root
                temp_root = Path(temp_dir)
                for partition_name in partition_names + ("daily",):
                    if partition_name == missing_partition:
                        continue
                    source = source_root / partition_name / "trade_date=20160104" / "part.parquet"
                    target = temp_root / partition_name / "trade_date=20160104" / "part.parquet"
                    target.parent.mkdir(parents=True)
                    shutil.copy2(source, target)

                adapter.formal_root = temp_root
                with self.assertRaises(FileNotFoundError) as error:
                    adapter.get_daily_status("000001.SZ", execution_date)
                self.assertIn(missing_partition, str(error.exception))


class TestOpenPriceExecutionBoundary(unittest.TestCase):
    """RED: 开盘价成交边界。"""
    
    def test_011_limit_up_at_open_rejects_buy(self):
        """开盘涨停（open == up_limit）拒绝买入。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        from strategy_core.fill_simulator import simulate_fill
        from strategy_core.portfolio import PortfolioState
        from contracts.stable import Order
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 2016-01-04 开盘涨停且未停牌的真实证券
        symbol = "300494.SZ"
        execution_date = date(2016, 1, 4)
        
        # 验证确实开盘涨停且未停牌
        bar = adapter.get_daily_bar(symbol, execution_date)
        status = adapter.get_daily_status(symbol, execution_date)
        self.assertTrue(status.is_limit_up, "300494.SZ should be limit_up at open on 2016-01-04")
        self.assertFalse(status.is_suspended, "300494.SZ should not be suspended")
        
        # 买入订单
        order = Order(
            order_id="limit_up_buy",
            signal_id="sig_001",
            symbol=symbol,
            direction="buy",
            quantity=100,
            signal_date=date(2016, 1, 1),
            intended_execution_date=execution_date,
            reason="test",
            strategy_version="v1.0",
            audit_id="audit_001",
        )
        
        portfolio = PortfolioState(cash=100000.0)
        
        # 构建 calendar stub
        from strategy_core.trading_calendar import TradingCalendar
        calendar = object.__new__(TradingCalendar)
        trading_dates = adapter.get_trading_dates()
        calendar._dates = list(trading_dates)
        calendar._date_set = set(trading_dates)
        calendar._date_to_index = {d: i for i, d in enumerate(trading_dates)}
        
        # Fill
        filled = simulate_fill(
            order, execution_date, adapter, portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, max_participation_rate=0.10,
            calendar=calendar,
        )
        
        # 必须被拒绝
        self.assertEqual(filled.status, "rejected")
        self.assertIn("limit", filled.rejection_reason.lower())
    
    def test_012_limit_down_at_open_rejects_sell(self):
        """开盘跌停（open == down_limit）拒绝卖出。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        from strategy_core.fill_simulator import simulate_fill
        from strategy_core.portfolio import PortfolioState, Position
        from contracts.stable import Order
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 2016-01-04 开盘跌停且未停牌的真实证券
        symbol = "000155.SZ"
        execution_date = date(2016, 1, 4)
        
        # 验证确实开盘跌停且未停牌
        status = adapter.get_daily_status(symbol, execution_date)
        self.assertTrue(status.is_limit_down, "000155.SZ should be limit_down at open on 2016-01-04")
        self.assertFalse(status.is_suspended, "000155.SZ should not be suspended")
        
        # 卖出订单
        order = Order(
            order_id="limit_down_sell",
            signal_id="sig_002",
            symbol=symbol,
            direction="sell",
            quantity=100,
            signal_date=date(2016, 1, 1),
            intended_execution_date=execution_date,
            reason="test",
            strategy_version="v1.0",
            audit_id="audit_002",
        )
        
        # Portfolio with position
        portfolio = PortfolioState(cash=100000.0)
        portfolio.positions[symbol] = Position(
            symbol=symbol,
            quantity=200,
            sellable_quantity=200,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        # Calendar stub
        from strategy_core.trading_calendar import TradingCalendar
        calendar = object.__new__(TradingCalendar)
        trading_dates = adapter.get_trading_dates()
        calendar._dates = list(trading_dates)
        calendar._date_set = set(trading_dates)
        calendar._date_to_index = {d: i for i, d in enumerate(trading_dates)}
        
        # Fill
        filled = simulate_fill(
            order, execution_date, adapter, portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, max_participation_rate=0.10,
            calendar=calendar,
        )
        
        # 必须被拒绝
        self.assertEqual(filled.status, "rejected")
        self.assertIn("limit", filled.rejection_reason.lower())

if __name__ == "__main__":
    unittest.main()
