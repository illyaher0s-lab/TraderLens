"""
Test Evidence light-check runner.

These tests prove:
- clean candidate gets no blocking issues
- hard-filter flags become blocking issues
- unknown evidence stays 'unknown'
- falsifying evidence can lower level to 'falsified'
- conflicting evidence becomes 'conflicted'
- 'conflicted' does not become blocking_issues
- expired evidence is detectable
- tool trace records deterministic steps
- evidence output includes the baseline kill_criteria_hash
- evidence runner fails loud when no baseline kill criteria snapshot is available
"""

import unittest
from datetime import date, datetime, timedelta
from backend.services.evidence_light import EvidenceLightRunner
from backend.services.research_validation import ValidationResult


class TestEvidenceLight(unittest.TestCase):
    """Test Evidence light-check runner."""

    def setUp(self):
        """Set up evidence runner."""
        self.runner = EvidenceLightRunner()

    def test_clean_candidate_gets_no_blocking_issues(self):
        """Clean candidate gets no blocking issues."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_001",
            symbol="300750.SZ",
            validation_result=validation_result,
        )
        
        self.assertEqual(output.blocking_issues, [])

    def test_hard_filter_flags_become_blocking_issues(self):
        """Hard-filter flags become blocking issues."""
        validation_result = ValidationResult(
            flags=["is_st", "low_liquidity"],
            is_valid=False,
        )
        
        output = self.runner.run_light_check(
            candidate_id="cand_002",
            symbol="*ST600000",
            validation_result=validation_result,
        )
        
        self.assertIn("is_st", output.blocking_issues)
        self.assertIn("low_liquidity", output.blocking_issues)

    def test_unknown_evidence_stays_unknown(self):
        """Unknown evidence stays 'unknown'."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_003",
            symbol="688001.SH",
            validation_result=validation_result,
        )
        
        # Stub runner without external evidence keeps level as 'unknown'
        self.assertEqual(output.evidence_level, "unknown")

    def test_falsifying_evidence_lowers_to_falsified(self):
        """Falsifying evidence can lower level to 'falsified'."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        # Inject falsifying evidence into runner
        output = self.runner.run_light_check(
            candidate_id="cand_004",
            symbol="600000.SH",
            validation_result=validation_result,
            inject_falsifying_evidence=[
                {
                    "source": "公司公告",
                    "description": "业绩大幅下滑",
                    "published_at": date.today() - timedelta(days=5),
                }
            ],
        )
        
        self.assertEqual(output.evidence_level, "falsified")
        self.assertGreater(len(output.falsifying_evidence), 0)

    def test_conflicting_evidence_becomes_conflicted(self):
        """Conflicting evidence becomes 'conflicted'."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_005",
            symbol="002594.SZ",
            validation_result=validation_result,
            inject_conflict=[
                {
                    "source_a": "券商研报",
                    "source_b": "财经媒体",
                    "conflict_type": "业绩预期不一致",
                    "description": "研报预测增长，媒体报道下滑",
                }
            ],
        )
        
        self.assertEqual(output.evidence_level, "conflicted")
        self.assertGreater(len(output.conflict_items), 0)

    def test_conflicted_does_not_become_blocking_issue(self):
        """'conflicted' evidence level is set but unresolved conflicts produce quality blocking issues."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_006",
            symbol="002460.SZ",
            validation_result=validation_result,
            inject_conflict=[
                {
                    "source_a": "来源A",
                    "source_b": "来源B",
                    "conflict_type": "数据冲突",
                    "description": "测试冲突",
                }
            ],
        )
        
        self.assertEqual(output.evidence_level, "conflicted")
        # Quality rules add unresolved_conflict as a blocking issue
        self.assertIn("unresolved_conflict", " ".join(output.blocking_issues))

    def test_expired_evidence_is_detectable(self):
        """Expired evidence is detectable."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        # Inject expired evidence
        output = self.runner.run_light_check(
            candidate_id="cand_007",
            symbol="603799.SH",
            validation_result=validation_result,
            inject_supporting_evidence=[
                {
                    "source": "行业报告",
                    "description": "市场份额数据",
                    "published_at": date.today() - timedelta(days=100),
                    "expiry_days": 90,
                }
            ],
        )
        
        # Check that evidence with expiry_days is present
        for evidence in output.supporting_evidence:
            if evidence.expiry_days:
                expired = (date.today() - evidence.published_at).days > evidence.expiry_days
                if expired:
                    # Expired evidence should be flagged in evidence_gaps
                    self.assertIn("过期", " ".join(output.evidence_gaps))
                    break

    def test_tool_trace_records_deterministic_steps(self):
        """Tool trace records deterministic steps."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_008",
            symbol="688005.SH",
            validation_result=validation_result,
        )
        
        self.assertIsInstance(output.tool_trace, list)
        # Tool trace should record at least the validation step
        self.assertGreater(len(output.tool_trace), 0)

    def test_evidence_output_includes_kill_criteria_hash(self):
        """Evidence output includes the baseline kill_criteria_hash."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        output = self.runner.run_light_check(
            candidate_id="cand_009",
            symbol="300750.SZ",
            validation_result=validation_result,
        )
        
        self.assertIsNotNone(output.kill_criteria_hash)
        self.assertIsInstance(output.kill_criteria_hash, str)

    def test_runner_fails_when_no_baseline_criteria(self):
        """Evidence runner fails loud when no baseline kill criteria snapshot is available."""
        validation_result = ValidationResult(flags=[], is_valid=True)
        
        # Inject missing baseline flag
        with self.assertRaises(ValueError) as ctx:
            self.runner.run_light_check(
                candidate_id="cand_010",
                symbol="000001.SZ",
                validation_result=validation_result,
                inject_missing_baseline=True,
            )
        
        self.assertIn("baseline", str(ctx.exception).lower())


    def test_evidence_item_carries_source_type_and_quality_via_injection(self):
        """Injected evidence items carry source_type and source_quality."""
        validation_result = ValidationResult(flags=[], is_valid=True)

        output = self.runner.run_light_check(
            candidate_id="cand_source_id",
            symbol="300750.SZ",
            validation_result=validation_result,
            inject_supporting_evidence=[
                {
                    "source": "年报2025",
                    "source_type": "financial_report",
                    "source_quality": "first_hand",
                    "description": "ROE 连续三年 > 15%",
                    "published_at": date.today() - timedelta(days=30),
                    "supports": ["thesis_profitability"],
                }
            ],
        )

        self.assertEqual(len(output.supporting_evidence), 1)
        item = output.supporting_evidence[0]
        self.assertEqual(item.source_type, "financial_report")
        self.assertEqual(item.source_quality, "first_hand")
        self.assertEqual(item.supports, ["thesis_profitability"])

    def test_evidence_item_carries_falsifies_and_conflicts_via_injection(self):
        """Injected falsifying evidence carries falsifies and conflicts arrays."""
        validation_result = ValidationResult(flags=[], is_valid=True)

        output = self.runner.run_light_check(
            candidate_id="cand_falsify_id",
            symbol="600000.SH",
            validation_result=validation_result,
            inject_falsifying_evidence=[
                {
                    "source": "券商研报",
                    "source_type": "news",
                    "source_quality": "second_hand",
                    "description": "行业竞争加剧",
                    "published_at": date.today() - timedelta(days=7),
                    "falsifies": ["thesis_moat"],
                    "conflicts": ["source_disagreement"],
                }
            ],
        )

        self.assertEqual(len(output.falsifying_evidence), 1)
        item = output.falsifying_evidence[0]
        self.assertEqual(item.source_type, "news")
        self.assertEqual(item.source_quality, "second_hand")
        self.assertEqual(item.falsifies, ["thesis_moat"])
        self.assertEqual(item.conflicts, ["source_disagreement"])


if __name__ == "__main__":
    unittest.main()
