import unittest

from backend.services.strategy_template_library import StrategyTemplateLibrary


class TestStrategyTemplateLibrary(unittest.TestCase):
    def setUp(self):
        self.library = StrategyTemplateLibrary()

    def test_library_contains_exactly_four_templates(self):
        """Library contains original 4 templates plus V2 variants (no test fixture in production)."""
        templates = self.library.list_templates()
        expected_ids = {
            "theme_momentum_breakout_v1",
            "relative_strength_rotation_v1",
            "relative_strength_rotation_vendor_industry_v1",
            "relative_strength_rotation_sw2021_pit_v1",
            "volume_breakout_followthrough_v1",
            "trend_pullback_watch_v1",
            "relative_strength_rotation_shsz_sw2021_v1",
            "relative_strength_rotation_shsz_sw2021_v2",
            "relative_strength_rotation_shsz_sw2021_v3",
        }
        actual_ids = {t.template_id for t in templates}
        self.assertEqual(actual_ids, expected_ids, "Template set must match exactly")

    def test_template_hash_is_stable(self):
        lib1 = StrategyTemplateLibrary()
        lib2 = StrategyTemplateLibrary()

        t1 = lib1.get_template("theme_momentum_breakout_v1")
        t2 = lib2.get_template("theme_momentum_breakout_v1")

        self.assertEqual(t1.template_hash, t2.template_hash)
        self.assertNotEqual(t1.template_hash, "")

    def test_unknown_template_id_rejected(self):
        with self.assertRaises(KeyError):
            self.library.get_template("unknown_template")

    def test_no_runtime_template_creation_method(self):
        self.assertFalse(hasattr(self.library, "add_template"))
        self.assertFalse(hasattr(self.library, "create_template"))
        self.assertFalse(hasattr(self.library, "register_template"))
        self.assertFalse(hasattr(self.library, "update_template"))

    def test_templates_convert_to_b1_template_definition(self):
        from contracts.strategy import StrategyTemplateDefinition

        definition = self.library.to_b1_definition("theme_momentum_breakout_v1")
        self.assertIsInstance(definition, StrategyTemplateDefinition)
        self.assertEqual(definition.template_id, "theme_momentum_breakout_v1")
        self.assertEqual(definition.frozen, True)

    def test_each_template_has_core_entry_rule(self):
        for template in self.library.list_templates():
            self.assertIsNotNone(template.core_entry_rule_id)
            self.assertNotEqual(template.core_entry_rule_id, "")


if __name__ == "__main__":
    unittest.main()
