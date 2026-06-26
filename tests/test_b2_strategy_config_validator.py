import unittest
import copy

from backend.services.strategy_config_validator import (
    StrategyConfigValidator,
    StrategyValidationError,
    StrategyValidationResult,
)
from backend.services.strategy_template_library import StrategyTemplateLibrary
from tests.b1_fixtures import make_backtest_universe, make_forward_watchlist


class TestStrategyConfigValidator(unittest.TestCase):
    def setUp(self):
        self.validator = StrategyConfigValidator()
        self.library = StrategyTemplateLibrary()
        self.template = self.library.get_template("theme_momentum_breakout_v1")

    def test_valid_template_config_passes(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.errors), 0)

    def test_rejects_unknown_template(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        fake_template = self.template.model_copy(
            update={"template_id": "unknown_template"}
        )
        result = self.validator.validate(config, fake_template)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("unknown" in e.message.lower() for e in result.errors))

    def test_rejects_template_hash_mismatch(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        # Modify config to cause hash mismatch
        config["entry"]["breakout_lookback_days"] = 999
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")

    def test_rejects_modified_template_parameter(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["entry"]["breakout_lookback_days"] = 50  # Changed from 60
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")

    def test_rejects_missing_entry_exit_risk(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        del config["entry"]
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("entry" in e.field_path for e in result.errors))

    def test_rejects_forward_watchlist_universe(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        watchlist = make_forward_watchlist()
        result = self.validator.validate_universe(watchlist)
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("ForwardWatchlist" in e.message for e in result.errors)
        )

    def test_rejects_plain_symbol_list_universe(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        result = self.validator.validate_universe(["300750.SZ", "600000.SH"])
        self.assertEqual(result.status, "fail")

    def test_rejects_evidence_event_terms_in_trade_rules(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["entry"]["announcement_filter"] = True
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("announcement" in e.message.lower() for e in result.errors)
        )

    def test_rejects_parameter_search_and_variants(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["entry"]["breakout_lookback_days_range"] = [40, 60, 80]
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")

    def test_rejects_status_hash_gate_budget_fields(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["status"] = "draft"
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        
        config2 = copy.deepcopy(self.template.strategy_config_payload)
        config2["gate_verdict"] = "pass"
        result2 = self.validator.validate(config2, self.template)
        self.assertEqual(result2.status, "fail")

    def test_rejects_oos_dates(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["oos_start"] = "2025-01-01"
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")

    def test_rejects_user_cost_or_benchmark_override(self):
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["cost_model_override"] = "aggressive"
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        
        config2 = copy.deepcopy(self.template.strategy_config_payload)
        config2["benchmark_override"] = "custom_index"
        result2 = self.validator.validate(config2, self.template)
        self.assertEqual(result2.status, "fail")

    def test_rejects_evidence_term_in_deep_key(self):
        """Validator must check deep nested keys for evidence terms."""
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["entry"]["announcement_based_filter"] = {"enabled": True}
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("announcement" in e.message.lower() for e in result.errors)
        )

    def test_rejects_evidence_term_in_string_value(self):
        """Validator must check string values for evidence terms."""
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["entry"]["filter_type"] = "公告驱动"
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("公告" in e.message for e in result.errors)
        )

    def test_rejects_evidence_term_in_exit_and_risk_values(self):
        """Validator must check exit and risk sections for evidence terms."""
        config = copy.deepcopy(self.template.strategy_config_payload)
        config["exit"]["trigger"] = "disclosure event"
        result = self.validator.validate(config, self.template)
        self.assertEqual(result.status, "fail")
        
        config2 = copy.deepcopy(self.template.strategy_config_payload)
        config2["risk"]["avoid_conditions"] = ["订单取消"]
        result2 = self.validator.validate(config2, self.template)
        self.assertEqual(result2.status, "fail")


if __name__ == "__main__":
    unittest.main()
