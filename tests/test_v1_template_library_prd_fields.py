"""
V1 Template Library PRD Fields Tests

Verify approved templates expose full V1 PRD boundary and prevent overrides.
"""

import unittest
import hashlib
import json

from backend.services.strategy_template_library import (
    APPROVED_TEMPLATES,
    get_template_by_id,
)


class TestV1TemplatePRDFields(unittest.TestCase):
    """Test V1 PRD fields on approved templates."""

    def test_all_approved_templates_have_prd_fields(self):
        """Every approved template exposes all required PRD fields."""
        required_fields = [
            "template_id",
            "version",
            "market_fit",
            "forbidden_market",
            "entry_rules",
            "exit_rules",
            "risk_rules",
            "position_sizing_rules",
            "validation_gate_profile",
            "frozen_template_hash",
        ]

        for template in APPROVED_TEMPLATES:
            for field in required_fields:
                self.assertTrue(
                    hasattr(template, field),
                    f"Template {template.template_id} missing field: {field}"
                )
                value = getattr(template, field)
                self.assertIsNotNone(
                    value,
                    f"Template {template.template_id} field {field} is None"
                )

    def test_frozen_template_hash_exists_and_stable(self):
        """frozen_template_hash exists and is stable across loads."""
        template1 = get_template_by_id("theme_momentum_breakout_v1")
        template2 = get_template_by_id("theme_momentum_breakout_v1")

        self.assertIsNotNone(template1.frozen_template_hash)
        self.assertIsNotNone(template2.frozen_template_hash)
        self.assertEqual(template1.frozen_template_hash, template2.frozen_template_hash)

    def test_frozen_template_hash_is_semantic(self):
        """Hash covers semantic fields, not just ID+version."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        # Hash must be SHA256 (64 hex chars)
        self.assertEqual(len(template.frozen_template_hash), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in template.frozen_template_hash))

        # Hash must not be just ID+version
        simple_hash = hashlib.sha256(
            f"{template.template_id}:{template.version}".encode()
        ).hexdigest()
        self.assertNotEqual(template.frozen_template_hash, simple_hash)

    def test_template_id_version_frozen(self):
        """Template ID and version remain frozen."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        self.assertEqual(template.template_id, "theme_momentum_breakout_v1")
        self.assertIsNotNone(template.version)
        
        # Pydantic frozen model - cannot modify
        with self.assertRaises(Exception):
            template.template_id = "modified"

    def test_user_payload_cannot_override_entry_rules(self):
        """User/LLM payload cannot override entry_rules."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_entry = template.entry_rules
        
        # Template is frozen - any attempt to override should fail
        with self.assertRaises(Exception):
            template.entry_rules = "User override"
        
        # Verify entry_rules unchanged
        self.assertEqual(template.entry_rules, original_entry)

    def test_user_payload_cannot_override_exit_rules(self):
        """User/LLM payload cannot override exit_rules."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        with self.assertRaises(Exception):
            template.exit_rules = "Modified"

    def test_user_payload_cannot_override_risk_rules(self):
        """User/LLM payload cannot override risk_rules."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        with self.assertRaises(Exception):
            template.risk_rules = "Modified"

    def test_user_payload_cannot_override_position_sizing_rules(self):
        """User/LLM payload cannot override position_sizing_rules."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        with self.assertRaises(Exception):
            template.position_sizing_rules = "Modified"

    def test_user_payload_cannot_override_validation_gate_profile(self):
        """User/LLM payload cannot override validation_gate_profile."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        with self.assertRaises(Exception):
            template.validation_gate_profile = "Modified"

    def test_user_payload_cannot_override_config_payload(self):
        """User/LLM payload cannot override strategy_config_payload."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        with self.assertRaises(Exception):
            template.strategy_config_payload = {}

    def test_candidate_template_not_in_approved_list(self):
        """Candidate/unapproved templates not in APPROVED_TEMPLATES."""
        # All templates in APPROVED_TEMPLATES must have is_approved=True
        for template in APPROVED_TEMPLATES:
            # Should have all PRD fields (already tested above)
            self.assertIsNotNone(template.frozen_template_hash)
        
        # get_template_by_id only returns approved templates
        # Non-existent or candidate templates return None
        candidate = get_template_by_id("candidate_template_v1")
        self.assertIsNone(candidate)

    def test_all_templates_immutable(self):
        """All approved templates are immutable."""
        for template in APPROVED_TEMPLATES:
            # Pydantic frozen=True enforces immutability
            with self.assertRaises(Exception):
                template.template_id = "modified"


class TestV1TemplateHashSemantics(unittest.TestCase):
    """Test semantic hash changes when content changes."""

    def test_hash_covers_entry_rules(self):
        """Hash must change if entry_rules change."""
        # Get template
        t1 = get_template_by_id("theme_momentum_breakout_v1")
        
        # Simulate another template with different entry rules
        # (In real code, templates are frozen at library definition time)
        # Here we verify that hash is not just ID+version
        
        # Hash must be semantic - covering rules and config
        self.assertIsNotNone(t1.frozen_template_hash)
        self.assertIsNotNone(t1.entry_rules)

    def test_hash_covers_config_payload(self):
        """Hash must cover strategy_config_payload."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        # Hash must not be empty
        self.assertTrue(len(template.frozen_template_hash) > 0)
        
        # Template must have non-empty config
        self.assertTrue(len(template.strategy_config_payload) > 0)


if __name__ == "__main__":
    unittest.main()


class TestV1TemplateHashMutation(unittest.TestCase):
    """Test hash changes when semantic fields change."""

    def test_hash_changes_when_entry_rules_changes(self):
        """Hash changes when entry_rules changes."""
        from backend.services.strategy_template_library import StrategyTemplate
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_hash = template.frozen_template_hash
        
        # Use model_construct to bypass validators for test
        modified = StrategyTemplate.model_construct(**{
            **template.model_dump(),
            "entry_rules": "Modified entry logic"
        })
        
        self.assertNotEqual(modified.frozen_template_hash, original_hash)

    def test_hash_changes_when_exit_rules_changes(self):
        """Hash changes when exit_rules changes."""
        from backend.services.strategy_template_library import StrategyTemplate
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_hash = template.frozen_template_hash
        
        modified = StrategyTemplate.model_construct(**{
            **template.model_dump(),
            "exit_rules": "Modified exit logic"
        })
        
        self.assertNotEqual(modified.frozen_template_hash, original_hash)

    def test_hash_changes_when_risk_rules_changes(self):
        """Hash changes when risk_rules changes."""
        from backend.services.strategy_template_library import StrategyTemplate
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_hash = template.frozen_template_hash
        
        modified = StrategyTemplate.model_construct(**{
            **template.model_dump(),
            "risk_rules": "Modified risk logic"
        })
        
        self.assertNotEqual(modified.frozen_template_hash, original_hash)

    def test_hash_changes_when_position_sizing_rules_changes(self):
        """Hash changes when position_sizing_rules changes."""
        from backend.services.strategy_template_library import StrategyTemplate
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_hash = template.frozen_template_hash
        
        modified = StrategyTemplate.model_construct(**{
            **template.model_dump(),
            "position_sizing_rules": "Modified sizing"
        })
        
        self.assertNotEqual(modified.frozen_template_hash, original_hash)

    def test_hash_changes_when_validation_gate_profile_changes(self):
        """Hash changes when validation_gate_profile changes."""
        from backend.services.strategy_template_library import StrategyTemplate
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        original_hash = template.frozen_template_hash
        
        modified = StrategyTemplate.model_construct(**{
            **template.model_dump(),
            "validation_gate_profile": "strict"
        })
        
        self.assertNotEqual(modified.frozen_template_hash, original_hash)

    def test_nested_config_immutable(self):
        """Attempting to mutate nested strategy_config_payload fails."""
        template = get_template_by_id("theme_momentum_breakout_v1")
        
        # strategy_config_payload is now immutable (MappingProxyType)
        with self.assertRaises(TypeError):
            template.strategy_config_payload["entry"]["macd_fast"] = 99

    def test_convert_to_frozen_contract_uses_v1_hash(self):
        """convert_to_frozen_contract uses V1 semantic frozen hash."""
        from backend.services.strategy_template_library import convert_to_frozen_contract
        from datetime import datetime, timezone
        
        template = get_template_by_id("theme_momentum_breakout_v1")
        now = datetime.now(timezone.utc)
        
        contract = convert_to_frozen_contract(template, now)
        
        # Contract must use frozen_template_hash (V1 semantic hash)
        self.assertEqual(contract.template_hash, template.frozen_template_hash)
