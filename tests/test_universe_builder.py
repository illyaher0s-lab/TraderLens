from pathlib import Path
import unittest

import yaml


def load_golden_config():
    from strategy_core.dsl_parser import parse_strategy_config_dict

    with Path("tests/golden_cases/strategy_config.yaml").open("r", encoding="utf-8") as handle:
        return parse_strategy_config_dict(yaml.safe_load(handle))


class UniverseBuilderTests(unittest.TestCase):
    def test_static_list_universe_returns_symbols_in_strategy_order_when_available(self):
        from backend.app.golden_cases import GoldenCaseDataSource
        from strategy_core.universe_builder import build_universe

        config = load_golden_config()
        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        universe = build_universe(config, source)

        self.assertEqual(
            universe,
            ["000001.SZ", "600000.SH", "000002.SZ", "600519.SH", "300750.SZ"],
        )

    def test_static_list_universe_rejects_symbols_missing_from_data_source(self):
        from backend.app.golden_cases import GoldenCaseDataSource
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.universe_builder import build_universe

        raw = yaml.safe_load(Path("tests/golden_cases/strategy_config.yaml").read_text(encoding="utf-8"))
        raw["universe"]["symbols"] = ["000001.SZ", "999999.SZ"]
        config = parse_strategy_config_dict(raw)
        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        with self.assertRaisesRegex(ValueError, "symbol not available in data source: 999999.SZ"):
            build_universe(config, source)

    def test_sector_plus_filters_fails_loudly_for_this_m1_slice(self):
        from backend.app.golden_cases import GoldenCaseDataSource
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.universe_builder import build_universe

        raw = yaml.safe_load(Path("tests/golden_cases/strategy_config.yaml").read_text(encoding="utf-8"))
        raw["universe"] = {"type": "sector_plus_filters", "sector": "robotics", "filters": {}}
        config = parse_strategy_config_dict(raw)
        source = GoldenCaseDataSource(Path("tests/golden_cases"))

        with self.assertRaisesRegex(NotImplementedError, "sector_plus_filters universe is not implemented"):
            build_universe(config, source)


if __name__ == "__main__":
    unittest.main()
