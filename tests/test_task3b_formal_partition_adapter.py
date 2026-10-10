"""Task 3B Corrective: Formal PIT Partition Adapter RED tests.

从正式分区加载 DailyStatus 并接通 B4 fill simulator。
"""
import unittest
from collections import Counter
from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import inspect
import math
import os
from pathlib import Path
import shutil
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(
    os.environ.get("TRADERLENS_SOURCE_ROOT", Path(__file__).parent.parent)
).resolve()
FORMAL_REL = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal")


def _fixture_adapter(root, *, calendar_artifact_dir=None):
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

    formal_root = root / FORMAL_REL
    return FormalPITPartitionAdapter.for_test_fixture(
        root,
        formal_input_root=formal_root,
        stock_basic_root=formal_root / "stock_basic",
        calendar_artifact_dir=calendar_artifact_dir,
    )


@contextmanager
def _temporary_r_only_down_limit_adapter():
    """Build a minimal synthetic FormalPIT root for the R-only fill boundary."""
    from backend.services.formal_pit_partition_adapter import (
        COMMON_CALENDAR_REL,
        FormalPITPartitionAdapter,
    )

    execution_date = date(2024, 1, 10)
    symbol = "RONLY.SZ"
    temp = tempfile.TemporaryDirectory(prefix="formal_r_only_down_limit_")
    try:
        root = Path(temp.name)
        formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
        source_formal = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
        shutil.copytree(source_formal / "stock_basic", formal / "stock_basic")

        def write_partition(name, rows, schema):
            path = formal / name / f"trade_date={execution_date:%Y%m%d}" / "part.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)

        write_partition(
            "suspend_d",
            [{"ts_code": symbol, "suspend_type": "R", "suspend_timing": None}],
            pa.schema([
                ("ts_code", pa.string()),
                ("suspend_type", pa.string()),
                ("suspend_timing", pa.string()),
            ]),
        )
        write_partition(
            "daily",
            [{
                "ts_code": symbol, "open": 9.0, "high": 9.2, "low": 8.8,
                "close": 9.1, "vol": 100000.0, "amount": 90000000.0,
            }],
            pa.schema([
                ("ts_code", pa.string()), ("open", pa.float64()),
                ("high", pa.float64()), ("low", pa.float64()),
                ("close", pa.float64()), ("vol", pa.float64()),
                ("amount", pa.float64()),
            ]),
        )
        write_partition(
            "adj_factor",
            [{"ts_code": symbol, "adj_factor": 1.0}],
            pa.schema([("ts_code", pa.string()), ("adj_factor", pa.float64())]),
        )
        write_partition(
            "stk_limit",
            [{"ts_code": symbol, "up_limit": 11.0, "down_limit": 9.0}],
            pa.schema([
                ("ts_code", pa.string()),
                ("up_limit", pa.float64()),
                ("down_limit", pa.float64()),
            ]),
        )
        write_partition(
            "stock_st",
            [],
            pa.schema([("ts_code", pa.string()), ("name", pa.string())]),
        )

        calendar_dir = REPO_ROOT / Path(*COMMON_CALENDAR_REL.split("/"))
        adapter = _fixture_adapter(root, calendar_artifact_dir=calendar_dir)
        yield root, adapter, symbol, execution_date
    finally:
        temp.cleanup()


class TestFormalPITPartitionAdapter(unittest.TestCase):
    """RED: 从正式分区加载 DailyStatus。"""
    
    def test_001_adapter_loads_daily_status_from_formal_partition(self):
        """Adapter 从正式分区读取 DailyStatus。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 2024-01-02 是交易日
        status = adapter.get_daily_status("000001.SZ", date(2024, 1, 2))
        
        self.assertEqual(status.symbol, "000001.SZ")
        self.assertEqual(status.date, date(2024, 1, 2))
        self.assertIsInstance(status.is_suspended, bool)
        self.assertIsInstance(status.is_limit_up, bool)
        self.assertIsInstance(status.is_limit_down, bool)
        self.assertIsInstance(status.is_st, bool)
    
    def test_002_missing_partition_fails_loud(self):
        """缺失分区必须 fail loud。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 1999-01-01 分区不存在
        with self.assertRaises((KeyError, FileNotFoundError, ValueError)):
            adapter.get_daily_status("000001.SZ", date(1999, 1, 1))
    
    def test_003_missing_symbol_fails_loud(self):
        """缺失证券必须 fail loud。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # INVALID.SZ 不存在
        with self.assertRaises((KeyError, ValueError)):
            adapter.get_daily_status("INVALID.SZ", date(2024, 1, 2))
    
    def test_004_resume_event_with_daily_is_not_suspended(self):
        """有日线的复牌事件不构成当日全日停牌。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)

        status = adapter.get_daily_status("000676.SZ", date(2016, 1, 4))

        # Diagnostic evidence: the raw row is R and a finite daily row exists;
        # this assertion records the contract correction, not test appeasement.
        self.assertFalse(status.is_suspended)
        self.assertEqual(status.suspend_reason, "R")
        self.assertIsNotNone(adapter.get_daily_bar("000676.SZ", date(2016, 1, 4)))
    
    def test_005_st_stock_returns_true(self):
        """ST 股票 is_st=True。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)

        status = adapter.get_daily_status("000403.SZ", date(2016, 8, 9))

        self.assertTrue(status.is_st)

    def test_r_only_valid_daily_open_at_down_limit_is_not_suspended(self):
        with _temporary_r_only_down_limit_adapter() as (_, adapter, symbol, execution_date):
            status = adapter.get_daily_status(symbol, execution_date)
            self.assertFalse(status.is_suspended)
            self.assertEqual(status.suspend_reason, "R")
            self.assertTrue(status.is_limit_down)


class TestT1ExecutionWithFormalPartitions(unittest.TestCase):
    """RED: T+1 执行与正式分区集成。"""
    
    def test_011_signal_d_executes_on_next_trading_day(self):
        """信号日 d 在下一个交易日执行。"""
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        from strategy_core.trading_calendar import TradingCalendar
        from strategy_core.fill_simulator import simulate_fill
        from strategy_core.portfolio import PortfolioState
        from contracts.stable import Order
        
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 构建 TradingCalendar (需要提供符合 DataSource protocol 的对象)
        # 由于 adapter 不完全实现 symbols()/get_daily_bars()，手工构建 calendar
        trading_dates = adapter.get_trading_dates()
        
        # 手工构建 calendar (直接初始化内部状态)
        from strategy_core.trading_calendar import TradingCalendar
        calendar = object.__new__(TradingCalendar)
        calendar._dates = list(trading_dates)
        calendar._date_set = set(trading_dates)
        calendar._date_to_index = {d: i for i, d in enumerate(trading_dates)}
        
        # 信号日 2024-01-02
        signal_date = date(2024, 1, 2)
        execution_date = calendar.next_trading_day(signal_date)  # 2024-01-03
        
        # 买入订单 (使用真实存在的证券)
        order = Order(
            order_id="test_t1_001",
            signal_id="sig_001",
            symbol="000002.SZ",  # 万科A
            direction="buy",
            quantity=100,
            signal_date=signal_date,
            intended_execution_date=execution_date,
            reason="test_buy",
            strategy_version="v1.0",
            audit_id="audit_001",
        )
        
        portfolio = PortfolioState(cash=100000.0)
        
        # 执行 fill
        filled = simulate_fill(
            order=order,
            execution_date=execution_date,
            data_source=adapter,
            portfolio=portfolio,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.001,
            max_participation_rate=0.10,
            calendar=calendar,
        )
        
        # 必须在 execution_date 执行，不在 signal_date
        self.assertEqual(filled.actual_execution_date, execution_date)
        self.assertNotEqual(filled.actual_execution_date, signal_date)

    def test_r_only_valid_daily_open_at_down_limit_rejects_limit_down(self):
        from contracts.stable import Order
        from strategy_core.fill_simulator import simulate_fill
        from strategy_core.portfolio import PortfolioState
        from strategy_core.trading_calendar import TradingCalendar

        with _temporary_r_only_down_limit_adapter() as (_, adapter, symbol, execution_date):
            dates = list(adapter.get_trading_dates())
            calendar = object.__new__(TradingCalendar)
            calendar._dates = dates
            calendar._date_set = set(dates)
            calendar._date_to_index = {day: index for index, day in enumerate(dates)}

            portfolio = PortfolioState(cash=100000.0)
            buy_date = date(2024, 1, 8)
            portfolio.add_position(symbol, 100, 10.0, buy_date, calendar)
            portfolio.unlock_frozen_lots(execution_date)
            order = Order(
                order_id="r_only_down_limit_sell",
                signal_id="r_only_down_limit_signal",
                symbol=symbol,
                direction="sell",
                quantity=100,
                signal_date=date(2024, 1, 9),
                intended_execution_date=execution_date,
                reason="test_r_only_down_limit",
                strategy_version="test",
                audit_id="r_only_down_limit_audit",
            )

            filled = simulate_fill(
                order, execution_date, adapter, portfolio,
                commission_rate=0.0003, min_commission=5.0,
                stamp_duty_rate=0.001, calendar=calendar,
            )

            self.assertEqual(filled.status, "rejected")
            self.assertEqual(filled.rejection_reason, "limit_down")


class TestFormalPITMembershipProvenance(unittest.TestCase):
    """RED: _005 membership provenance 保留。"""
    
    def test_021_adapter_with_005_membership(self):
        """Adapter 与 _005 membership 集成。"""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        # 获取 2024-01-02 的 PIT members
        members = source.get_members_at_date(date(2024, 1, 2))
        
        # Adapter
        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        
        # 对所有 members 查询 DailyStatus（证明 provenance 保留）
        # 某些成员可能无数据（退市/停牌），记录成功查询数
        success_count = 0
        for member in members[:20]:  # 测试前 20 个（避免超时）
            try:
                status = adapter.get_daily_status(member.symbol, date(2024, 1, 2))
                self.assertEqual(status.symbol, member.symbol)
                success_count += 1
            except (KeyError, FileNotFoundError):
                # 该成员在 2024-01-02 无数据（可能退市）
                pass
        
        # 至少有一些成员有数据
        self.assertGreater(success_count, 0, "At least some _005 members should have data")
        
        # 验证 snapshot ID 可追溯
        self.assertEqual(snapshot.snapshot_id, "pims_traderlens_v2_shsz_sw2021_pit_005")


class TestFormalStockBasicListingEligibility(unittest.TestCase):
    """Historical eligibility uses listing dates, never current list_status."""

    def test_listing_date_boundary_and_current_status_are_ignored(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertFalse(adapter.is_eligible("000001.SZ", date(1991, 4, 2)))
        self.assertTrue(adapter.is_eligible("000001.SZ", date(1991, 4, 3)))
        self.assertTrue(adapter.is_eligible("000001.SZ", date(2024, 1, 2)))

    def test_delist_date_is_exclusive_and_dated_status_remains_eligible_before_it(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertTrue(adapter.is_eligible("000005.SZ", date(2024, 4, 25)))
        self.assertFalse(adapter.is_eligible("000005.SZ", date(2024, 4, 26)))

    def test_missing_delist_date_remains_eligible(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertTrue(adapter.is_eligible("000001.SZ", date(2099, 12, 31)))

    def test_p_status_uses_effective_dates_for_historical_eligibility(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_adapter({
            "L": [],
            "D": [],
            "P": [self._row("PAUSED.SZ", "20200101", None)],
        }) as make_adapter:
            adapter = make_adapter()
            self.assertTrue(adapter.is_eligible("PAUSED.SZ", date(2020, 1, 1)))

    def test_unknown_symbol_fails_loud(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        with self.assertRaises(KeyError):
            adapter.is_eligible("UNKNOWN.SZ", date(2024, 1, 2))

    def test_duplicate_symbol_fails_during_load(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_adapter({
            "L": [self._row("DUP.SZ", "20200101", None)],
            "D": [self._row("DUP.SZ", "20200101", "20210101")],
            "P": [],
        }) as make_adapter:
            with self.assertRaises(ValueError):
                make_adapter()

    def test_invalid_and_reverse_dates_fail_during_load(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        cases = (
            self._row("BAD.SZ", "20201301", None),
            self._row("REVERSE.SZ", "20220101", "20210101"),
        )
        for row in cases:
            with self.subTest(row=row), self._temporary_adapter({"L": [row], "D": [], "P": []}) as make_adapter:
                with self.assertRaises(ValueError):
                    make_adapter()

    @staticmethod
    def _row(symbol, list_date, delist_date):
        return {
            "ts_code": symbol,
            "symbol": symbol.split(".")[0],
            "name": symbol,
            "market": "主板",
            "exchange": "SSE",
            "list_status": "L",
            "list_date": list_date,
            "delist_date": delist_date,
        }

    @staticmethod
    def _temporary_adapter(rows_by_status):
        class Fixture:
            def __enter__(self):
                self.temp = tempfile.TemporaryDirectory(prefix="stock_basic_eligibility_")
                root = Path(self.temp.name)
                formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
                source = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
                for name in ("part.parquet", "part.parquet.sha256"):
                    target = formal / "trade_cal" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / "trade_cal" / name, target)
                for status, rows in rows_by_status.items():
                    target = formal / "stock_basic" / f"list_status={status}" / "part.parquet"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    table = pa.Table.from_pylist(rows, schema=pa.schema([
                        ("ts_code", pa.string()), ("symbol", pa.string()), ("name", pa.string()),
                        ("market", pa.string()), ("exchange", pa.string()), ("list_status", pa.string()),
                        ("list_date", pa.string()), ("delist_date", pa.string()),
                    ]))
                    pq.write_table(table, target)
                    target.with_suffix(target.suffix + ".sha256").write_text(
                        hashlib.sha256(target.read_bytes()).hexdigest() + "\n", encoding="ascii"
                    )
                self.root = root
                return self

            def __exit__(self, *exc):
                self.temp.cleanup()

            def __call__(self):
                from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

                return _fixture_adapter(self.root)

        return Fixture()


class TestFormalStockStDelistingRisk(unittest.TestCase):
    """Daily Stock ST warning evidence, not a complete delisting model."""

    EXECUTION_DATE = date(2016, 8, 9)

    def test_star_st_name_is_delisting_risk(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertTrue(adapter.is_delisting_risk("002199.SZ", self.EXECUTION_DATE))

    def test_plain_st_name_is_not_delisting_risk(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertFalse(adapter.is_delisting_risk("000403.SZ", self.EXECUTION_DATE))

    def test_missing_stock_st_row_is_not_delisting_risk(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        adapter = FormalPITPartitionAdapter(REPO_ROOT)
        self.assertFalse(adapter.is_delisting_risk("000001.SZ", self.EXECUTION_DATE))

    def test_name_matching_is_strict_and_does_not_trim(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_stock_st([{"ts_code": "TRIM.SZ", "name": " *ST trim"}]) as root:
            adapter = _fixture_adapter(root)
            self.assertFalse(adapter.is_delisting_risk("TRIM.SZ", self.EXECUTION_DATE))

    def test_empty_or_non_string_name_fails(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        cases = (("", pa.string()), (123, pa.int64()))
        for name, name_type in cases:
            with self.subTest(name=name), self._temporary_stock_st(
                [{"ts_code": "BAD.SZ", "name": name}], name_type=name_type
            ) as root:
                adapter = _fixture_adapter(root)
                with self.assertRaises(ValueError):
                    adapter.is_delisting_risk("BAD.SZ", self.EXECUTION_DATE)

    def test_docstring_declares_narrow_formal_stock_st_scope(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        doc = inspect.getdoc(FormalPITPartitionAdapter.is_delisting_risk)
        self.assertIsNotNone(doc)
        for phrase in ("2554", "delisting history", "reorganization period", "full-market"):
            self.assertIn(phrase, doc)

    @staticmethod
    def _temporary_stock_st(rows, name_type=pa.string()):
        class Fixture:
            def __enter__(self):
                self.temp = tempfile.TemporaryDirectory(prefix="stock_st_risk_")
                root = Path(self.temp.name)
                formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
                source = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
                for status in ("L", "D", "P"):
                    for name in ("part.parquet", "part.parquet.sha256"):
                        target = formal / "stock_basic" / f"list_status={status}" / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source / "stock_basic" / f"list_status={status}" / name, target)
                for name in ("part.parquet", "part.parquet.sha256"):
                    target = formal / "trade_cal" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / "trade_cal" / name, target)
                target = formal / "stock_st" / "trade_date=20160809" / "part.parquet"
                target.parent.mkdir(parents=True, exist_ok=True)
                table = pa.table({
                    "ts_code": pa.array([row["ts_code"] for row in rows], type=pa.string()),
                    "name": pa.array([row["name"] for row in rows], type=name_type),
                })
                pq.write_table(table, target)
                target.with_suffix(target.suffix + ".sha256").write_text(
                    hashlib.sha256(target.read_bytes()).hexdigest() + "\n", encoding="ascii"
                )
                self.root = root
                return self.root

            def __exit__(self, *exc):
                self.temp.cleanup()

        return Fixture()


class TestFormalLiquidityDerivation(unittest.TestCase):
    """Frozen V3 liquidity derivation focused matrix."""

    EXECUTION_DATE = date(2020, 1, 31)

    def test_common_window_scales_amount_and_excludes_execution_day(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_liquidity_fixture(common_count=20, common_amount=50000.0) as root:
            result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
        self.assertEqual(result, {"status": "qualified", "average_amount_yuan": 50_000_000.0})

    def test_below_threshold_is_distinct_ineligible(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_liquidity_fixture(common_count=20, common_amount=49999.0) as root:
            result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
        self.assertEqual(result["status"], "ineligible")
        self.assertEqual(result["average_amount_yuan"], 49_999_000.0)

    def test_d_status_and_short_listing_history_are_unavailable_ineligible(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_liquidity_fixture(common_count=20) as root:
            adapter = _fixture_adapter(root)
            self.assertEqual(adapter.derive_liquidity("D.SZ", self.EXECUTION_DATE), {
                "status": "unavailable_ineligible", "average_amount_yuan": None,
            })
            self.assertEqual(adapter.derive_liquidity("NEW.SZ", self.EXECUTION_DATE), {
                "status": "unavailable_ineligible", "average_amount_yuan": None,
            })

    def test_suspended_day_contributes_zero(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        suspended = {self.EXECUTION_DATE - timedelta(days=3)}
        with self._temporary_liquidity_fixture(
            common_count=20, common_amount=50000.0, suspended_dates=suspended
        ) as root:
            result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
        self.assertEqual(result, {"status": "ineligible", "average_amount_yuan": 47_500_000.0})

    def test_suspended_day_does_not_require_daily_partition(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        day = self.EXECUTION_DATE - timedelta(days=3)
        with self._temporary_liquidity_fixture(
            common_count=20,
            common_amount=50000.0,
            suspended_dates={day},
            missing_daily_dates={day},
        ) as root:
            result = _fixture_adapter(root).derive_liquidity(
                "AAA.SZ", self.EXECUTION_DATE
            )
        self.assertEqual(
            result,
            {"status": "ineligible", "average_amount_yuan": 47_500_000.0},
        )

    def test_exact_twenty_day_listing_history_is_eligible_but_nineteen_is_not(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        exact_first = self.EXECUTION_DATE - timedelta(days=22)
        with self._temporary_liquidity_fixture(
            common_count=20,
            common_amount=50000.0,
            list_date_overrides={"AAA.SZ": exact_first.strftime("%Y%m%d")},
        ) as root:
            exact = _fixture_adapter(root).derive_liquidity(
                "AAA.SZ", self.EXECUTION_DATE
            )
        with self._temporary_liquidity_fixture(
            common_count=20,
            common_amount=50000.0,
            list_date_overrides={
                "AAA.SZ": (exact_first + timedelta(days=1)).strftime("%Y%m%d")
            },
        ) as root:
            short = _fixture_adapter(root).derive_liquidity(
                "AAA.SZ", self.EXECUTION_DATE
            )
        self.assertEqual(
            exact,
            {"status": "qualified", "average_amount_yuan": 50_000_000.0},
        )
        self.assertEqual(
            short,
            {"status": "unavailable_ineligible", "average_amount_yuan": None},
        )

    def test_same_execution_date_prepares_liquidity_partitions_once(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_liquidity_fixture(common_count=20, common_amount=50000.0) as root:
            adapter = _fixture_adapter(root)
            calls = Counter()
            original = adapter._read_partition

            def counted(partition_name, execution_date):
                calls[partition_name] += 1
                return original(partition_name, execution_date)

            adapter._read_partition = counted
            self.assertEqual(
                adapter.derive_liquidity("AAA.SZ", self.EXECUTION_DATE),
                {"status": "qualified", "average_amount_yuan": 50_000_000.0},
            )
            self.assertEqual(
                adapter.derive_liquidity("P.SZ", self.EXECUTION_DATE),
                {"status": "data_fault", "average_amount_yuan": None},
            )
            self.assertEqual(
                adapter.derive_liquidity("AAA.SZ", self.EXECUTION_DATE),
                {"status": "qualified", "average_amount_yuan": 50_000_000.0},
            )

        self.assertEqual(calls["daily"], 20)
        self.assertEqual(calls["suspend_d"], 20)

    def test_non_suspended_missing_daily_is_data_fault(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        missing = {self.EXECUTION_DATE - timedelta(days=3)}
        with self._temporary_liquidity_fixture(common_count=20, missing_daily_dates=missing) as root:
            result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
        self.assertEqual(result, {"status": "data_fault", "average_amount_yuan": None})

    def test_bad_amounts_are_data_fault(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        cases = (None, float("nan"), float("inf"), -1.0, True)
        for bad_amount in cases:
            with self.subTest(amount=bad_amount), self._temporary_liquidity_fixture(
                common_count=20, amount_overrides={self.EXECUTION_DATE - timedelta(days=3): bad_amount}
            ) as root:
                result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
                self.assertEqual(result, {"status": "data_fault", "average_amount_yuan": None})

    def test_insufficient_window_does_not_partial_or_extend(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        with self._temporary_liquidity_fixture(common_count=19) as root:
            result = _fixture_adapter(root).derive_liquidity("AAA.SZ", self.EXECUTION_DATE)
        self.assertEqual(result, {"status": "unavailable_ineligible", "average_amount_yuan": None})

    def test_docstring_declares_candidate_scope_and_fixed_algorithm(self):
        from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

        doc = inspect.getdoc(FormalPITPartitionAdapter.derive_liquidity)
        self.assertIsNotNone(doc)
        for phrase in ("avg_amount_20d_shsz_common_v1", "candidate", "approved template", "B3 successor"):
            self.assertIn(phrase, doc)

    @classmethod
    def _temporary_liquidity_fixture(
        cls, *, common_count, common_amount=60000.0, suspended_dates=None,
        missing_daily_dates=None, amount_overrides=None, list_date_overrides=None,
    ):
        suspended_dates = set(suspended_dates or ())
        missing_daily_dates = set(missing_daily_dates or ())
        amount_overrides = dict(amount_overrides or {})
        list_date_overrides = dict(list_date_overrides or {})

        class Fixture:
            def __enter__(self):
                self.temp = tempfile.TemporaryDirectory(prefix="liquidity_derivation_")
                root = Path(self.temp.name)
                formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
                dates = [cls.EXECUTION_DATE - timedelta(days=i) for i in range(1, common_count + 3)]
                common_dates = [cls.EXECUTION_DATE - timedelta(days=i) for i in range(3, common_count + 3)]
                calendar_rows = []
                for day in dates + [cls.EXECUTION_DATE]:
                    day_text = day.strftime("%Y%m%d")
                    if day != dates[1]:
                        calendar_rows.append({"exchange": "SSE", "cal_date": day_text, "is_open": 1})
                    if day in common_dates or day == cls.EXECUTION_DATE or day == dates[1]:
                        calendar_rows.append({"exchange": "SZSE", "cal_date": day_text, "is_open": 1})
                calendar_path = formal / "trade_cal/part.parquet"
                calendar_path.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(pa.Table.from_pylist(calendar_rows), calendar_path)
                for status, rows in {
                    "L": [
                        {"ts_code": "AAA.SZ", "list_date": "20190101", "delist_date": None},
                        {"ts_code": "NEW.SZ", "list_date": "20200125", "delist_date": None},
                    ],
                    "D": [{"ts_code": "D.SZ", "list_date": "20190101", "delist_date": "20200130"}],
                    "P": [{"ts_code": "P.SZ", "list_date": "20190101", "delist_date": None}],
                }.items():
                    target = formal / "stock_basic" / f"list_status={status}" / "part.parquet"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    values = {
                        "ts_code": [row["ts_code"] for row in rows],
                        "symbol": [row["ts_code"].split(".")[0] for row in rows],
                        "name": [row["ts_code"] for row in rows],
                        "market": ["主板"] * len(rows), "exchange": ["SZSE"] * len(rows),
                        "list_status": [status] * len(rows),
                        "list_date": [list_date_overrides.get(row["ts_code"], row["list_date"]) for row in rows],
                        "delist_date": [row["delist_date"] for row in rows],
                    }
                    pq.write_table(pa.Table.from_pydict(values), target)
                for day in dates + [cls.EXECUTION_DATE]:
                    day_text = day.strftime("%Y%m%d")
                    suspend_path = formal / "suspend_d" / f"trade_date={day_text}" / "part.parquet"
                    suspend_path.parent.mkdir(parents=True, exist_ok=True)
                    suspend_rows = [{"ts_code": "AAA.SZ", "suspend_type": "S"}] if day in suspended_dates else []
                    pq.write_table(pa.Table.from_pylist(suspend_rows, schema=pa.schema([
                        ("ts_code", pa.string()), ("suspend_type", pa.string())
                    ])), suspend_path)
                    if day not in missing_daily_dates:
                        daily_path = formal / "daily" / f"trade_date={day_text}" / "part.parquet"
                        daily_path.parent.mkdir(parents=True, exist_ok=True)
                        amount = amount_overrides.get(day, 0.0 if day == cls.EXECUTION_DATE else common_amount)
                        pq.write_table(pa.Table.from_pydict({
                            "ts_code": ["AAA.SZ"], "amount": [amount],
                        }), daily_path)
                self.root = root
                return root

            def __exit__(self, *exc):
                self.temp.cleanup()

        return Fixture()


if __name__ == "__main__":
    unittest.main()
