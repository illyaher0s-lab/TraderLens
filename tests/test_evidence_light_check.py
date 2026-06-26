"""
Tests for Evidence Light Check (M4.1 Phase 1)

Tests the 5 risk checks:
1. ST status
2. Suspended
3. Limit up (buy signals)
4. Limit down (sell signals)
5. Low liquidity

Design constraints from M4.1 Plan:
- Only adds risk_flags, does NOT modify planned_action
- Does NOT change signal generation logic
- All tests are API-free (use mock data)
"""

import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

from backend.app.tushare.tushare_data_source import TushareDataSource
from backend.scripts.check_signal_evidence import check_signal_evidence
from contracts.signal_board import PlannedSignal
from contracts.stable import DailyBar, DailyStatus


class TestEvidenceLightCheck(unittest.TestCase):
    """Test evidence light_check logic."""
    
    def _make_signal(
        self,
        symbol: str = "600519.SH",
        direction: str = "buy",
        signal_date: date = date(2023, 12, 29)
    ) -> PlannedSignal:
        """Create a test signal."""
        return PlannedSignal(
            signal_id="test_signal_id",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            snapshot_hash="test_hash",
            signal_date=signal_date,
            intended_execution_date=date(2024, 1, 2),
            symbol=symbol,
            direction=direction,
            planned_action="enter" if direction == "buy" else "exit",
            quantity=100,
            trigger_reason="Test trigger",
            review_status="pending",
            created_at=datetime(2023, 12, 29, 16, 0, 0)
        )
    
    def _make_data_source_mock(
        self,
        bar: DailyBar | None = None,
        status: DailyStatus | None = None
    ) -> Mock:
        """Create a mock data source."""
        mock = Mock(spec=TushareDataSource)
        
        if bar:
            mock.get_daily_bar.return_value = bar
        else:
            mock.get_daily_bar.side_effect = KeyError("No bar data")
        
        if status:
            mock.get_daily_status.return_value = status
        else:
            mock.get_daily_status.side_effect = KeyError("No status data")
        
        return mock
    
    def test_clean_signal_no_risks(self):
        """Clean signal with no risks detected."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=2_000_000,  # Above threshold
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertEqual(risk_flags, [])
        self.assertEqual(evidence_status, "clean")
    
    def test_st_status_detected(self):
        """Detect ST status from DailyStatus."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=True,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False,
            st_type="ST"
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertIn("ST", risk_flags)
        self.assertEqual(evidence_status, "warning")
    
    def test_suspended_blocked(self):
        """Suspended stock is blocked."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=True,
            is_limit_up=False,
            is_limit_down=False,
            suspend_reason="重大资产重组"
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertIn("suspended", risk_flags)
        self.assertEqual(evidence_status, "blocked")
    
    def test_limit_up_blocks_buy_signal(self):
        """Limit up blocks buy signals (cannot execute)."""
        signal = self._make_signal(direction="buy")
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1860.0,  # At limit up
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=True,
            is_limit_down=False
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertIn("limit_up", risk_flags)
        self.assertEqual(evidence_status, "blocked")
    
    def test_limit_up_does_not_block_sell_signal(self):
        """Limit up does NOT block sell signals."""
        signal = self._make_signal(direction="sell")
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1860.0,
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=True,  # Limit up
            is_limit_down=False
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        # Should NOT flag limit_up for sell signals
        self.assertNotIn("limit_up", risk_flags)
        self.assertEqual(evidence_status, "clean")
    
    def test_limit_down_blocks_sell_signal(self):
        """Limit down blocks sell signals (cannot execute)."""
        signal = self._make_signal(direction="sell")
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1850.0,
            low=1840.0,
            close=1840.0,  # At limit down
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=True
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertIn("limit_down", risk_flags)
        self.assertEqual(evidence_status, "blocked")
    
    def test_limit_down_does_not_block_buy_signal(self):
        """Limit down does NOT block buy signals."""
        signal = self._make_signal(direction="buy")
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1850.0,
            low=1840.0,
            close=1840.0,
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=True  # Limit down
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        # Should NOT flag limit_down for buy signals
        self.assertNotIn("limit_down", risk_flags)
        self.assertEqual(evidence_status, "clean")
    
    def test_low_liquidity_warning(self):
        """Low liquidity is a warning (not blocked)."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=500_000,  # Below 1M threshold
            amount=900_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        self.assertIn("low_liquidity", risk_flags)
        self.assertEqual(evidence_status, "warning")
    
    def test_multiple_risks_blocked_takes_precedence(self):
        """Multiple risks: blocked status takes precedence over warning."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=500_000,  # Low liquidity (warning)
            amount=900_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=True,  # ST (warning)
            is_suspended=True,  # Suspended (blocked)
            is_limit_up=False,
            is_limit_down=False,
            st_type="ST"
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        # All 3 risks should be flagged
        self.assertIn("ST", risk_flags)
        self.assertIn("suspended", risk_flags)
        self.assertIn("low_liquidity", risk_flags)
        
        # But status should be blocked (highest severity)
        self.assertEqual(evidence_status, "blocked")
    
    def test_missing_status_data_graceful_degradation(self):
        """Missing status data: graceful degradation (check what we can)."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=2_000_000,
            amount=3_700_000_000.0,
            adj_factor=1.0
        )
        
        # No status data available
        data_source = self._make_data_source_mock(bar=bar, status=None)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        # Should still return clean (not error)
        self.assertEqual(risk_flags, [])
        self.assertEqual(evidence_status, "clean")
    
    def test_missing_bar_data_graceful_degradation(self):
        """Missing bar data: graceful degradation (check what we can)."""
        signal = self._make_signal()
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False
        )
        
        # No bar data available
        data_source = self._make_data_source_mock(bar=None, status=status)
        
        risk_flags, evidence_status = check_signal_evidence(signal, data_source)
        
        # Should still return clean (not error)
        self.assertEqual(risk_flags, [])
        self.assertEqual(evidence_status, "clean")
    
    def test_custom_liquidity_threshold(self):
        """Custom liquidity threshold."""
        signal = self._make_signal()
        
        bar = DailyBar(
            date=signal.signal_date,
            symbol=signal.symbol,
            open=1850.0,
            high=1860.0,
            low=1845.0,
            close=1855.0,
            volume=1_500_000,  # Above 1M, below 2M
            amount=2_775_000_000.0,
            adj_factor=1.0
        )
        
        status = DailyStatus(
            date=signal.signal_date,
            symbol=signal.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False
        )
        
        data_source = self._make_data_source_mock(bar=bar, status=status)
        
        # Default threshold (1M): should be clean
        risk_flags, evidence_status = check_signal_evidence(
            signal, data_source, min_liquidity_threshold=1_000_000
        )
        self.assertEqual(risk_flags, [])
        self.assertEqual(evidence_status, "clean")
        
        # Custom threshold (2M): should flag low_liquidity
        risk_flags, evidence_status = check_signal_evidence(
            signal, data_source, min_liquidity_threshold=2_000_000
        )
        self.assertIn("low_liquidity", risk_flags)
        self.assertEqual(evidence_status, "warning")


if __name__ == "__main__":
    unittest.main()
