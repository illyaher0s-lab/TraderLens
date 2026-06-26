import unittest

from tests.b1_fixtures import make_backtest_universe, make_forward_watchlist


class TestBacktestUniverseAdmission(unittest.TestCase):
    def test_formal_backtest_accepts_backtest_universe(self):
        from contracts.strategy import admit_formal_backtest_universe

        admitted = admit_formal_backtest_universe(make_backtest_universe())
        self.assertEqual(admitted.universe_spec_id, "universe_001")

    def test_formal_backtest_rejects_forward_watchlist(self):
        from contracts.strategy import admit_formal_backtest_universe

        with self.assertRaisesRegex(TypeError, "BacktestUniverseSpec"):
            admit_formal_backtest_universe(make_forward_watchlist())

    def test_formal_backtest_rejects_plain_symbol_list(self):
        from contracts.strategy import admit_formal_backtest_universe

        with self.assertRaisesRegex(TypeError, "BacktestUniverseSpec"):
            admit_formal_backtest_universe(["300750.SZ"])


if __name__ == "__main__":
    unittest.main()
