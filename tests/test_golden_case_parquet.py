import unittest
from pathlib import Path


class GoldenCaseParquetTests(unittest.TestCase):
    def test_daily_bar_and_status_snapshots_load_through_contract_validator(self):
        try:
            import pyarrow  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("pyarrow is required to generate and read Parquet snapshots")

        from backend.app.golden_cases import load_golden_case_snapshots

        root = Path(__file__).resolve().parent / "golden_cases"
        snapshots = load_golden_case_snapshots(root)

        self.assertEqual(len(snapshots), 5)
        for symbol, snapshot in snapshots.items():
            with self.subTest(symbol=symbol):
                self.assertGreaterEqual(len(snapshot.daily_bars), 3)
                self.assertEqual(len(snapshot.daily_bars), len(snapshot.daily_statuses))
                self.assertEqual(snapshot.daily_bars[0].symbol, symbol)
                self.assertEqual(snapshot.daily_statuses[0].symbol, symbol)


if __name__ == "__main__":
    unittest.main()
