import unittest
from datetime import date

from backend.services.oos_window_rules import OOSWindowRuleRegistry
from backend.services.b3_protocol_types import OOSWindowSpec


class TestOOSWindowRules(unittest.TestCase):
    def setUp(self):
        self.registry = OOSWindowRuleRegistry()
        
        # Sample trading calendar (252 trading days)
        self.trading_calendar = tuple(
            date(2024, 1, 1) + __import__("datetime").timedelta(days=i)
            for i in range(365) if (date(2024, 1, 1) + __import__("datetime").timedelta(days=i)).weekday() < 5
        )[:252]

    def test_rejects_user_supplied_oos_start_end(self):
        """User-supplied OOS dates must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            # Trying to pass explicit dates instead of rule
            self.registry.generate(
                rule_id="user_custom",
                trading_calendar=self.trading_calendar,
                available_start=date(2024, 1, 1),
                available_end=date(2024, 12, 31),
            )
        
        self.assertIn("unregistered", str(ctx.exception).lower())

    def test_rejects_llm_supplied_oos_start_end(self):
        """LLM cannot supply OOS start/end dates."""
        # LLM-generated rule names must fail
        with self.assertRaises(ValueError) as ctx:
            self.registry.generate(
                rule_id="llm_suggested_optimal_window",
                trading_calendar=self.trading_calendar,
                available_start=date(2024, 1, 1),
                available_end=date(2024, 12, 31),
            )
        
        self.assertIn("unregistered", str(ctx.exception).lower())

    def test_rejects_unregistered_oos_rule(self):
        """Only registered rules allowed."""
        with self.assertRaises(ValueError) as ctx:
            self.registry.generate(
                rule_id="random_unregistered_rule",
                trading_calendar=self.trading_calendar,
                available_start=date(2024, 1, 1),
                available_end=date(2024, 12, 31),
            )
        
        self.assertIn("unregistered", str(ctx.exception).lower())

    def test_same_inputs_generate_same_window(self):
        """Same trading calendar + rule must produce same window."""
        window1 = self.registry.generate(
            rule_id="latest_252_trading_days",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        window2 = self.registry.generate(
            rule_id="latest_252_trading_days",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        # P0-3: Complete OOSWindowSpec must be equal
        self.assertEqual(window1.oos_window_start, window2.oos_window_start)
        self.assertEqual(window1.oos_window_end, window2.oos_window_end)
        self.assertEqual(window1.oos_window_rule_id, window2.oos_window_rule_id)
        self.assertEqual(window1.generated_at, window2.generated_at)
        
        # Entire object must be equal
        self.assertEqual(window1, window2)

    def test_latest_252_trading_days_rule(self):
        """latest_252_trading_days rule uses last N trading days."""
        window = self.registry.generate(
            rule_id="latest_252_trading_days",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        # OOS should be the entire calendar (252 days)
        self.assertIsInstance(window, OOSWindowSpec)
        self.assertEqual(window.oos_window_rule_id, "latest_252_trading_days")
        self.assertIsNotNone(window.oos_window_start)
        self.assertIsNotNone(window.oos_window_end)

    def test_fixed_ratio_70_30_rule(self):
        """fixed_ratio_70_30 rule splits calendar 70% IS / 30% OOS."""
        window = self.registry.generate(
            rule_id="fixed_ratio_70_30",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        self.assertIsInstance(window, OOSWindowSpec)
        self.assertEqual(window.oos_window_rule_id, "fixed_ratio_70_30")
        
        # OOS start must be after IS period
        self.assertGreater(window.oos_window_start, self.trading_calendar[0])

    def test_insufficient_trading_days_fails(self):
        """Insufficient trading days must fail loud."""
        short_calendar = self.trading_calendar[:10]  # Only 10 days
        
        with self.assertRaises(ValueError) as ctx:
            self.registry.generate(
                rule_id="latest_252_trading_days",
                trading_calendar=short_calendar,
                available_start=date(2024, 1, 1),
                available_end=date(2024, 1, 15),
            )
        
        self.assertIn("insufficient", str(ctx.exception).lower())

    def test_shared_oos_window_id_is_stable(self):
        """shared_oos_window_id must be deterministic and non-empty."""
        window1 = self.registry.generate(
            rule_id="fixed_ratio_70_30",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        window2 = self.registry.generate(
            rule_id="fixed_ratio_70_30",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        # Compute shared_oos_window_id explicitly
        shared_id1 = self.registry.compute_shared_oos_window_id(
            rule_id="fixed_ratio_70_30",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        shared_id2 = self.registry.compute_shared_oos_window_id(
            rule_id="fixed_ratio_70_30",
            trading_calendar=self.trading_calendar,
            available_start=date(2024, 1, 1),
            available_end=date(2024, 12, 31),
        )
        
        # shared_oos_window_id must be stable
        self.assertEqual(shared_id1, shared_id2)
        self.assertIsNotNone(shared_id1)
        self.assertNotEqual(shared_id1, "")
        self.assertGreater(len(shared_id1), 0)
        
        # Window dates must be identical (deterministic)
        self.assertEqual(window1.oos_window_start, window2.oos_window_start)
        self.assertEqual(window1.oos_window_end, window2.oos_window_end)
        
        # generated_at must be deterministic (not current date)
        self.assertEqual(window1.generated_at, window2.generated_at)

    def test_oos_window_generator_has_no_llm_dependency(self):
        """OOS window generator must be deterministic, no LLM."""
        from backend.services import oos_window_rules
        import inspect
        
        source = inspect.getsource(oos_window_rules)
        lines = [line for line in source.split('\n') if not line.strip().startswith('"') and not line.strip().startswith('#')]
        code_only = '\n'.join(lines).lower()
        
        self.assertNotIn("import llm", code_only)
        self.assertNotIn("from llm", code_only)
        self.assertNotIn("openai", code_only)
        self.assertNotIn("anthropic", code_only)


if __name__ == "__main__":
    unittest.main()
