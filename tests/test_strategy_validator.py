import copy
from pathlib import Path
import unittest

import yaml


def load_golden_config_dict():
    with Path("tests/golden_cases/strategy_config.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class StrategyValidatorTests(unittest.TestCase):
    def test_golden_case_strategy_passes_v1_semantic_validation(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.validator import validate_strategy_config

        config = parse_strategy_config_dict(load_golden_config_dict())

        validated = validate_strategy_config(config)

        self.assertIs(validated, config)

    def test_static_list_universe_must_not_be_empty(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.validator import validate_strategy_config

        raw = load_golden_config_dict()
        raw["universe"]["symbols"] = []
        config = parse_strategy_config_dict(raw)

        with self.assertRaisesRegex(ValueError, "static_list universe must include at least one symbol"):
            validate_strategy_config(config)

    def test_unknown_rule_type_is_rejected_before_signal_generation(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.validator import validate_strategy_config

        raw = load_golden_config_dict()
        raw["entry_conditions"]["rules"] = [{"type": "mystery_indicator"}]
        config = parse_strategy_config_dict(raw)

        with self.assertRaisesRegex(ValueError, "unsupported entry rule type: mystery_indicator"):
            validate_strategy_config(config)

    def test_fundamental_and_event_rules_are_rejected_in_v1(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict
        from strategy_core.validator import validate_strategy_config

        for rule_type in ["pe_ratio", "announcement_keyword"]:
            raw = load_golden_config_dict()
            raw["entry_conditions"]["rules"] = [{"type": rule_type}]
            config = parse_strategy_config_dict(raw)

            with self.subTest(rule_type=rule_type):
                with self.assertRaisesRegex(ValueError, "not supported in V1 strategy signals"):
                    validate_strategy_config(config)

    def test_parser_can_validate_semantics_when_requested(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict

        raw = copy.deepcopy(load_golden_config_dict())
        raw["universe"]["symbols"] = []

        with self.assertRaisesRegex(ValueError, "static_list universe must include at least one symbol"):
            parse_strategy_config_dict(raw, validate_semantics=True)


if __name__ == "__main__":
    unittest.main()
