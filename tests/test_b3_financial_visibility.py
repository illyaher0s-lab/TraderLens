import unittest
from datetime import date

from backend.services.financial_visibility import FinancialVisibilityGuard


class TestFinancialVisibilityGuard(unittest.TestCase):
    def setUp(self):
        self.guard = FinancialVisibilityGuard()

    def test_financial_data_requires_ann_date_not_end_date(self):
        """Financial data must use ann_date (announcement), not end_date (report period)."""
        # Valid: has ann_date
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),
            ann_date=date(2024, 4, 30),
            as_of_date=date(2024, 5, 1),
        )
        self.assertTrue(is_visible)

    def test_unknown_ann_date_blocks_usage(self):
        """Missing or None ann_date must block financial data usage."""
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),
            ann_date=None,
            as_of_date=date(2024, 5, 1),
        )
        self.assertFalse(is_visible)
        self.assertIn("ann_date", error)

    def test_ann_date_after_as_of_date_blocks_usage(self):
        """Data announced after as_of_date (future) cannot be used."""
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),
            ann_date=date(2024, 6, 1),  # Future
            as_of_date=date(2024, 5, 1),
        )
        self.assertFalse(is_visible)
        self.assertIn("future", error.lower())

    def test_no_inference_for_missing_ann_date(self):
        """Guard must not infer or estimate missing ann_date."""
        # This should fail, not silently infer
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),
            ann_date=None,
            as_of_date=date(2024, 5, 1),
        )
        self.assertFalse(is_visible)

    def test_period_end_before_t_but_ann_date_after_t_is_not_visible(self):
        """Report period before T but ann_date after T must not be visible."""
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),  # Q1 report
            ann_date=date(2024, 6, 1),  # Announced June 1
            as_of_date=date(2024, 5, 1),  # Query as of May 1
        )
        self.assertFalse(is_visible)
        self.assertIn("future", error.lower())

    def test_no_fallback_to_period_end_date(self):
        """Guard must not use report period end date when ann_date is missing."""
        # Missing ann_date should block, not fall back to report_period_end
        is_visible, error = self.guard.check_visibility(
            symbol="000001.SZ",
            report_period_end=date(2024, 3, 31),
            ann_date=None,  # Missing
            as_of_date=date(2024, 5, 1),
        )
        self.assertFalse(is_visible)
        self.assertIn("ann_date", error)

    def test_no_llm_call_in_visibility_guard(self):
        """Visibility guard must be deterministic."""
        from backend.services import financial_visibility
        import inspect
        
        source = inspect.getsource(financial_visibility)
        lines = [line for line in source.split('\n') if not line.strip().startswith('"')]
        code_only = '\n'.join(lines).lower()
        
        self.assertNotIn("import llm", code_only)
        self.assertNotIn("openai", code_only)


if __name__ == "__main__":
    unittest.main()
