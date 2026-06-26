"""
Mock v2.1 coverage tests.

These tests keep fixture generation aligned with the validation strategies:
breakthrough rules need controlled trigger points in mock data. The mock data is
for toolchain validation only, not market-performance interpretation.
"""
from pathlib import Path
import unittest

from backend.app.fixed_fixture import FixedFixtureDataSource


def count_breakthrough_days(data_source, symbols: list[str], window: int) -> int:
    """Count days where current close reaches the inclusive high_Nd benchmark."""
    count = 0
    for symbol in symbols:
        bars = sorted(data_source.get_daily_bars(symbol), key=lambda bar: bar.date)
        for index, bar in enumerate(bars):
            recent = bars[max(0, index - window + 1):index + 1]
            if recent and bar.close >= max(recent_bar.high for recent_bar in recent):
                count += 1
    return count


def count_volume_breakthrough_days(data_source, symbols: list[str], window: int, volume_window: int, multiplier: float) -> int:
    """Count days satisfying breakthrough and volume_surge together."""
    count = 0
    for symbol in symbols:
        bars = sorted(data_source.get_daily_bars(symbol), key=lambda bar: bar.date)
        for index, bar in enumerate(bars):
            high_recent = bars[max(0, index - window + 1):index + 1]
            volume_recent = bars[max(0, index - volume_window + 1):index + 1]
            high_match = high_recent and bar.close >= max(recent_bar.high for recent_bar in high_recent)
            volume_match = (
                volume_recent
                and bar.volume >= (sum(recent_bar.volume for recent_bar in volume_recent) / len(volume_recent)) * multiplier
            )
            if high_match and volume_match:
                count += 1
    return count


class TestMockV21BreakthroughCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource(Path("tests/fixed_fixture"))

    def test_fixture_manifest_declares_mock_v21(self):
        """Fixed fixture should explicitly identify Mock v2.1 generation."""
        manifest = self.data_source.get_manifest()
        self.assertEqual(manifest["source"], "mock")
        self.assertEqual(manifest["mock_version"], "2.1")
        self.assertEqual(manifest["result_usage"], "toolchain_validation_only")

    def test_strategy_001_breakthrough_universe_has_high_5d_triggers(self):
        """
        Strategy 001's high_5d breakthrough universe should not be all-zero.
        """
        symbols = ["000001.SZ", "000002.SZ", "600519.SH", "600036.SH", "300750.SZ"]
        self.assertGreaterEqual(count_breakthrough_days(self.data_source, symbols, 5), 5)

    def test_strategy_002_price_volume_breakout_has_joint_triggers(self):
        """
        Strategy 002 needs at least one controlled price+volume breakout event.
        """
        symbols = ["000001.SZ", "600519.SH", "300750.SZ", "002475.SZ", "601318.SH"]
        self.assertGreaterEqual(
            count_volume_breakthrough_days(self.data_source, symbols, 3, 5, 1.5),
            1,
        )


if __name__ == "__main__":
    unittest.main()
