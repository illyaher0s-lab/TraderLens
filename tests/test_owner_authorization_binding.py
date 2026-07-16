"""
Owner Authorization Binding Tests (Task 1-E)

Test exact binding enforcement from governance_map.
Per docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md Task 1.
"""
import unittest
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import backend.services.strategy_template_library as template_library
from backend.services.strategy_template_library import (
    get_template_by_id,
    convert_to_frozen_contract,
    list_approved_templates,
)


class TestOwnerAuthorizationBinding(unittest.TestCase):
    """Exact binding: authorization in governance_map controls approved status."""

    review_path = Path("docs/verification/TASK1_V2_AI_TECHNICAL_REVIEW.md")

    def _copy_review(self, root: Path, *, tamper: bool = False) -> None:
        target = root / self.review_path
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(self.review_path, target)
        if tamper:
            target.write_bytes(target.read_bytes() + b"\nreview tampered for test\n")

    def _assert_b6_blocks_before_reserve(self) -> None:
        from backend.services.b6_validation_flow import B6ValidationFlow
        from contracts.strategy import StrategyDraft

        class FakeLedger:
            reserve_calls = 0

            def reserve_oos_draw(self, **kwargs):
                self.reserve_calls += 1
                raise AssertionError("review evidence guard must block before reserve")

        ledger = FakeLedger()
        controller = MagicMock()
        report_builder = MagicMock()
        gate = MagicMock()
        explanation_builder = MagicMock()
        flow = B6ValidationFlow(
            oos_controller=controller,
            report_builder=report_builder,
            gate=gate,
            explanation_builder=explanation_builder,
            oos_budget_ledger=ledger,
        )
        draft = StrategyDraft(
            strategy_revision_id="review_guard_v2",
            theme_id="theme_001",
            hypothesis_id="hypothesis_001",
            strategy_template_id="relative_strength_rotation_shsz_sw2021_v2",
            strategy_template_version="v2_shsz_sw2021_pit_12m",
            strategy_template_hash="867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6",
            hypothesis_source_snapshot_id="hypothesis_snapshot_001",
            backtest_universe_spec_id="universe_001",
            strategy_config_json="{}",
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime(2026, 7, 15, 17, 0, 0),
        )
        result = flow.run_minimal_validation(
            strategy_draft=draft,
            protocol=MagicMock(protocol_snapshot_id="protocol_001"),
            manifest=MagicMock(),
            universe=MagicMock(),
            b4_qualification={},
            b4_event_result=MagicMock(),
            human_decision=None,
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("candidate", result.blocking_reason.lower())
        self.assertEqual(ledger.reserve_calls, 0)
        controller.validate_b3_b4_prerequisites.assert_not_called()
        for protected_component in (report_builder, gate, explanation_builder):
            self.assertEqual(
                [call for call in protected_component.mock_calls if call[0] != "__bool__"],
                [],
            )

    def test_v2_approved_via_governance_map(self):
        """V2 with authorization in governance_map → approved."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        frozen = convert_to_frozen_contract(template, created_at=datetime.now())
        
        self.assertEqual(frozen.governance_status, "approved")
        self.assertEqual(frozen.template_id, "relative_strength_rotation_shsz_sw2021_v2")
        self.assertEqual(frozen.version, "v2_shsz_sw2021_pit_12m")
        self.assertEqual(
            frozen.template_hash,
            "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6",
        )
        self.assertEqual(frozen.reviewer_id, "ai_reviewer_openai_codex_gpt5")
        self.assertIsNotNone(frozen.reviewed_at)
        self.assertIsNotNone(frozen.review_due_date)
        self.assertEqual(frozen.review_evidence_path, self.review_path.as_posix())
        self.assertEqual(len(frozen.review_evidence_sha256), 64)
        self.assertEqual(len(frozen.owner_authorization_hash), 64)
        self.assertEqual(frozen.authorized_by, "illya")
        self.assertIsNotNone(frozen.authorized_at)

    def test_v1_no_authorization_stays_candidate(self):
        """V1 without authorization in governance_map → candidate."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        frozen = convert_to_frozen_contract(template, created_at=datetime.now())
        
        self.assertEqual(frozen.governance_status, "candidate")
        self.assertIsNone(frozen.reviewer_id)
        self.assertIsNone(frozen.reviewed_at)

    def test_invalid_review_evidence_blocks_conversion_list_and_b6(self):
        """Missing, tampered, or wrongly expected review evidence blocks the real boundary."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        for case, copy_review, tamper, wrong_expected_hash in (
            ("missing", False, False, False),
            ("tampered", True, True, False),
            ("wrong_expected_hash", True, False, True),
        ):
            with self.subTest(case=case):
                with TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    if copy_review:
                        self._copy_review(root, tamper=tamper)
                    governance_context = nullcontext()
                    if wrong_expected_hash:
                        self.assertTrue(hasattr(template_library, "_governance_map"))
                        governance_map = template_library._governance_map()
                        governance_map[template.template_id]["owner_authorization"]["review_evidence_sha256"] = "0" * 64
                        governance_context = patch.object(
                            template_library,
                            "_governance_map",
                            return_value=governance_map,
                        )
                    with patch.object(template_library, "_repository_root", return_value=root, create=True):
                        with governance_context:
                            frozen = convert_to_frozen_contract(template, created_at=datetime.now())
                            self.assertEqual(frozen.governance_status, "candidate")
                            self.assertNotIn(template.template_id, [item.template_id for item in list_approved_templates()])
                            self._assert_b6_blocks_before_reserve()

    def test_list_approved_returns_only_v2(self):
        """list_approved_templates() returns only V2 (approved via governance_map)."""
        approved = list_approved_templates()
        approved_ids = [t.template_id for t in approved]
        
        self.assertEqual(len(approved), 1)
        self.assertIn("relative_strength_rotation_shsz_sw2021_v2", approved_ids)

    def test_b6_real_path_gets_approved_status(self):
        """B6 real path (direct convert_to_frozen_contract call) sees approved."""
        # Simulate B6 orchestrator calling convert_to_frozen_contract directly
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        frozen = convert_to_frozen_contract(template, created_at=datetime.now())
        
        # Must be approved (not candidate) so B6 does not reject before reserve
        self.assertEqual(frozen.governance_status, "approved")

    def test_governance_map_is_single_source_of_truth(self):
        """Authorization from governance_map applies to all call paths."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        
        # Call path 1: direct convert
        frozen1 = convert_to_frozen_contract(template, created_at=datetime.now())
        
        # Call path 2: via list_approved
        approved = list_approved_templates()
        frozen2 = convert_to_frozen_contract(approved[0], created_at=datetime.now())
        
        self.assertEqual(frozen1.governance_status, "approved")
        self.assertEqual(frozen2.governance_status, "approved")
        self.assertEqual(frozen1.template_hash, frozen2.template_hash)


if __name__ == "__main__":
    unittest.main()
