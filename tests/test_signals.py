from datetime import date
import unittest

import yaml

from backend.app.contracts import DailyBar
from strategy_core.dsl_parser import parse_strategy_config_dict


class MemoryBarSource:
    def __init__(self, bars_by_symbol):
        self._bars_by_symbol = bars_by_symbol

    def get_daily_bars(self, symbol):
        return list(self._bars_by_symbol[symbol])


def bar(symbol, day, high, close, volume=1000):
    return DailyBar(
        date=day,
        symbol=symbol,
        open=close,
        high=high,
        low=close,
        close=close,
        volume=volume,
        amount=volume * close,
        adj_factor=1.0,
    )


def load_config_with_entry_rules(rules):
    with open("tests/golden_cases/strategy_config.yaml", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    raw["universe"]["symbols"] = ["000001.SZ"]
    raw["entry_conditions"]["rules"] = rules
    raw["exit_conditions"]["rules"] = []
    return parse_strategy_config_dict(raw, validate_semantics=True)


class SignalGenerationTests(unittest.TestCase):
    def test_breakthrough_generates_entry_signal_when_close_reaches_recent_high(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "breakthrough", "field": "close", "benchmark": "high_2d", "operator": ">="}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0),
                    bar("000001.SZ", date(2024, 1, 4), high=99.0, close=99.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.symbol, "000001.SZ")
        self.assertEqual(signal.signal_date, date(2024, 1, 3))
        self.assertEqual(signal.signal_type, "entry")
        self.assertEqual(signal.generated_by, "strategy_core")
        self.assertEqual(signal.triggered_rules, ["breakthrough:close>=high_2d"])

    def test_breakthrough_does_not_generate_signal_when_close_is_below_recent_high(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "breakthrough", "field": "close", "benchmark": "high_2d", "operator": ">="}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5),
                    bar("000001.SZ", date(2024, 1, 3), high=10.1, close=10.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(signals, [])

    def test_breakthrough_uses_only_trade_date_and_prior_bars(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "breakthrough", "field": "close", "benchmark": "high_2d", "operator": ">="}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0),
                    bar("000001.SZ", date(2024, 1, 4), high=200.0, close=200.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(len(signals), 1)

    def test_volume_surge_generates_entry_signal_when_volume_reaches_moving_average_threshold(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [
                {
                    "type": "volume_surge",
                    "field": "volume",
                    "benchmark": "ma_volume_2d",
                    "multiplier": 1.5,
                    "operator": ">=",
                }
            ]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5, volume=100),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0, volume=300),
                    bar("000001.SZ", date(2024, 1, 4), high=10.0, close=10.0, volume=10000),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].triggered_rules, ["volume_surge:volume>=ma_volume_2d*1.5"])

    def test_volume_surge_does_not_generate_signal_when_volume_is_below_threshold(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [
                {
                    "type": "volume_surge",
                    "field": "volume",
                    "benchmark": "ma_volume_2d",
                    "multiplier": 1.5,
                    "operator": ">=",
                }
            ]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5, volume=200),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0, volume=200),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(signals, [])

    def test_breakthrough_and_volume_surge_both_must_pass_under_and_logic(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [
                {"type": "breakthrough", "field": "close", "benchmark": "high_2d", "operator": ">="},
                {
                    "type": "volume_surge",
                    "field": "volume",
                    "benchmark": "ma_volume_2d",
                    "multiplier": 1.5,
                    "operator": ">=",
                },
            ]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5, volume=100),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0, volume=300),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(len(signals), 1)
        self.assertEqual(
            signals[0].triggered_rules,
            ["breakthrough:close>=high_2d", "volume_surge:volume>=ma_volume_2d*1.5"],
        )

    def test_volume_surge_uses_only_trade_date_and_prior_bars(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [
                {
                    "type": "volume_surge",
                    "field": "volume",
                    "benchmark": "ma_volume_2d",
                    "multiplier": 1.5,
                    "operator": ">=",
                }
            ]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=9.5, volume=100),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0, volume=300),
                    bar("000001.SZ", date(2024, 1, 4), high=10.0, close=10.0, volume=100000),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

        self.assertEqual(len(signals), 1)

    def test_volume_surge_invalid_shape_fails_loudly(self):
        from strategy_core.signals import generate_signals

        source = MemoryBarSource(
            {"000001.SZ": [bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0, volume=300)]}
        )
        invalid_rules = [
            {
                "type": "volume_surge",
                "field": "amount",
                "benchmark": "ma_volume_2d",
                "multiplier": 1.5,
                "operator": ">=",
            },
            {
                "type": "volume_surge",
                "field": "volume",
                "benchmark": "ma_amount_2d",
                "multiplier": 1.5,
                "operator": ">=",
            },
            {
                "type": "volume_surge",
                "field": "volume",
                "benchmark": "ma_volume_2d",
                "multiplier": 1.5,
                "operator": ">",
            },
        ]

        for rule in invalid_rules:
            config = load_config_with_entry_rules([rule])
            with self.subTest(rule=rule):
                with self.assertRaises((ValueError, NotImplementedError)):
                    generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

    def test_ma_condition_generates_entry_signal_when_close_is_above_moving_average(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "ma_condition", "field": "close", "ma_period": 3, "operator": ">"}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=8.0),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0),
                    bar("000001.SZ", date(2024, 1, 4), high=11.0, close=11.0),
                    bar("000001.SZ", date(2024, 1, 5), high=50.0, close=50.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 4), ["000001.SZ"])

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].triggered_rules, ["ma_condition:close>ma_3"])

    def test_ma_condition_does_not_generate_signal_when_close_is_not_above_moving_average(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "ma_condition", "field": "close", "ma_period": 3, "operator": ">"}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=12.0, close=12.0),
                    bar("000001.SZ", date(2024, 1, 3), high=11.0, close=11.0),
                    bar("000001.SZ", date(2024, 1, 4), high=10.0, close=10.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 4), ["000001.SZ"])

        self.assertEqual(signals, [])

    def test_ma_condition_uses_only_trade_date_and_prior_bars(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "ma_condition", "field": "close", "ma_period": 3, "operator": ">"}]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=10.0, close=8.0),
                    bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0),
                    bar("000001.SZ", date(2024, 1, 4), high=11.0, close=11.0),
                    bar("000001.SZ", date(2024, 1, 5), high=200.0, close=200.0),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 4), ["000001.SZ"])

        self.assertEqual(len(signals), 1)

    def test_ma_condition_combines_with_breakthrough_and_volume_surge_under_and_logic(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [
                {"type": "breakthrough", "field": "close", "benchmark": "high_3d", "operator": ">="},
                {
                    "type": "volume_surge",
                    "field": "volume",
                    "benchmark": "ma_volume_3d",
                    "multiplier": 1.2,
                    "operator": ">=",
                },
                {"type": "ma_condition", "field": "close", "ma_period": 3, "operator": ">"},
            ]
        )
        source = MemoryBarSource(
            {
                "000001.SZ": [
                    bar("000001.SZ", date(2024, 1, 2), high=8.0, close=8.0, volume=100),
                    bar("000001.SZ", date(2024, 1, 3), high=9.0, close=9.0, volume=100),
                    bar("000001.SZ", date(2024, 1, 4), high=10.0, close=10.0, volume=500),
                ]
            }
        )

        signals = generate_signals(config, source, date(2024, 1, 4), ["000001.SZ"])

        self.assertEqual(len(signals), 1)
        self.assertEqual(
            signals[0].triggered_rules,
            [
                "breakthrough:close>=high_3d",
                "volume_surge:volume>=ma_volume_3d*1.2",
                "ma_condition:close>ma_3",
            ],
        )

    def test_ma_condition_invalid_shape_fails_loudly(self):
        from strategy_core.signals import generate_signals

        source = MemoryBarSource(
            {"000001.SZ": [bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0)]}
        )
        invalid_rules = [
            {"type": "ma_condition", "field": "volume", "ma_period": 3, "operator": ">"},
            {"type": "ma_condition", "field": "close", "ma_period": 0, "operator": ">"},
            {"type": "ma_condition", "field": "close", "ma_period": 3, "operator": ">="},
        ]

        for rule in invalid_rules:
            config = load_config_with_entry_rules([rule])
            with self.subTest(rule=rule):
                with self.assertRaises((ValueError, NotImplementedError)):
                    generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])

    def test_other_supported_but_unimplemented_rule_fails_loudly(self):
        from strategy_core.signals import generate_signals

        config = load_config_with_entry_rules(
            [{"type": "relative_strength", "field": "sector_relative_strength_rank", "percentile": 10, "operator": "<="}]
        )
        source = MemoryBarSource(
            {"000001.SZ": [bar("000001.SZ", date(2024, 1, 3), high=10.0, close=10.0)]}
        )

        with self.assertRaisesRegex(NotImplementedError, "signal rule is not implemented: relative_strength"):
            generate_signals(config, source, date(2024, 1, 3), ["000001.SZ"])


if __name__ == "__main__":
    unittest.main()
