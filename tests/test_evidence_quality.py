"""
Test Evidence source-quality rules.

These tests prove:
- Source mapping is deterministic
- No source → blocked
- Weak source → cannot produce strong
- All weak → blocked
- Expired evidence → gap/warning
- Unresolved conflict → blocks auto-confirmation
- Must have both support chain and counter-evidence
- Quality validator integrates with EvidenceLightRunner
"""

import unittest
from datetime import date, datetime, timedelta
from contracts.research import EvidenceItem, EvidenceOutput
from backend.services.evidence_quality import (
    EvidenceQualityValidator,
    EvidenceQualityResult,
    classify_source,
    SOURCE_MAPPING,
    DEFAULT_MAPPING,
)
from backend.services.research_validation import ValidationResult
from backend.services.evidence_light import EvidenceLightRunner


class TestSourceMapping(unittest.TestCase):
    """Test deterministic source mapping."""

    def test_tushare_income_maps_to_financial_report_first_hand(self):
        source_type, source_quality = classify_source("tushare_income")
        self.assertEqual(source_type, "financial_report")
        self.assertEqual(source_quality, "first_hand")

    def test_tushare_anns_maps_to_announcement_first_hand(self):
        source_type, source_quality = classify_source("tushare_anns")
        self.assertEqual(source_type, "announcement")
        self.assertEqual(source_quality, "first_hand")

    def test_tushare_stock_basic_maps_to_financial_report_first_hand(self):
        source_type, source_quality = classify_source("tushare_stock_basic")
        self.assertEqual(source_type, "financial_report")
        self.assertEqual(source_quality, "first_hand")

    def test_news_maps_to_news_second_hand(self):
        source_type, source_quality = classify_source("news")
        self.assertEqual(source_type, "news")
        self.assertEqual(source_quality, "second_hand")

    def test_interaction_platform_maps_to_weak(self):
        source_type, source_quality = classify_source("interaction_platform")
        self.assertEqual(source_type, "interaction_platform")
        self.assertEqual(source_quality, "weak")

    def test_social_media_maps_to_weak(self):
        source_type, source_quality = classify_source("social_media")
        self.assertEqual(source_type, "social_media")
        self.assertEqual(source_quality, "weak")

    def test_unknown_source_maps_to_default(self):
        source_type, source_quality = classify_source("some_random_source")
        self.assertEqual(source_type, "unknown")
        self.assertEqual(source_quality, "weak")

    def test_all_mapped_sources_in_valid_literals(self):
        """All mapped source_types are valid SourceType literals."""
        valid_types = {
            "announcement", "financial_report", "prospectus",
            "interaction_platform", "news", "social_media", "unknown",
        }
        for _, (st, sq) in SOURCE_MAPPING.items():
            self.assertIn(st, valid_types, f"Invalid source_type: {st}")


class TestQualityValidator(unittest.TestCase):
    """Test EvidenceQualityValidator rules."""

    def setUp(self):
        self.validator = EvidenceQualityValidator()
        self.now = datetime.now()
        self.today = date.today()

    def _make_evidence(self, source, source_type, source_quality, **kwargs):
        return EvidenceItem(
            source=source,
            source_type=source_type,
            source_quality=source_quality,
            description=kwargs.get("description", "test evidence"),
            retrieved_at=self.now,
            published_at=kwargs.get("published_at"),
            expiry_days=kwargs.get("expiry_days"),
            valid_until=kwargs.get("valid_until"),
            supports=kwargs.get("supports", []),
            falsifies=kwargs.get("falsifies", []),
            conflicts=kwargs.get("conflicts", []),
        )

    def test_no_evidence_produces_no_blocking(self):
        """Empty evidence produces no quality blocking (state is 'needs_evidence')."""
        result = self.validator.validate([], [], 0)
        self.assertFalse(result.can_auto_confirm)
        # But blocking_reasons is empty — no_evidence is handled by evidence_level='unknown'
        self.assertEqual(result.blocking_reasons, [])

    def test_no_source_blocks_confirmation(self):
        """Evidence with source_type='unknown' blocks confirmation."""
        evidence = self._make_evidence("some_source", "unknown", "weak")
        result = self.validator.validate([evidence], [], 0)
        self.assertTrue(result.any_no_source)
        self.assertIn("no_source", " ".join(result.blocking_reasons))
        self.assertFalse(result.can_auto_confirm)

    def test_all_weak_blocks_confirmation(self):
        """All evidence from weak sources blocks confirmation."""
        evidence = self._make_evidence("微博", "social_media", "weak")
        result = self.validator.validate([evidence], [], 0)
        self.assertTrue(result.all_weak)
        self.assertIn("all_weak", " ".join(result.blocking_reasons))
        self.assertFalse(result.can_auto_confirm)

    def test_weak_source_cannot_be_strong(self):
        """Weak sources are flagged; evaluate_evidence_level downgrades 'strong'."""
        evidence = self._make_evidence("微博", "social_media", "weak")
        result = self.validator.validate([evidence], [], 0)
        level = self.validator.evaluate_evidence_level(result, "strong", 1, 0, 0)
        self.assertEqual(level, "weak")  # downgraded: all weak

    def test_first_hand_with_support_passes_quality(self):
        """First-hand source with supporting evidence passes quality checks."""
        evidence = self._make_evidence(
            "年报", "financial_report", "first_hand",
            supports=["thesis_1"],
        )
        result = self.validator.validate([evidence], [], 0)
        # has support but no counter-evidence — warning, not block
        self.assertTrue(result.has_support)
        self.assertFalse(result.all_weak)
        self.assertFalse(result.any_no_source)
        # no counter-evidence is a warning, not a block
        self.assertIn("no_counter_evidence", " ".join(result.warnings))

    def test_expired_by_days_produces_gap(self):
        """Evidence expired by expiry_days produces gap."""
        evidence = self._make_evidence(
            "年报", "financial_report", "first_hand",
            published_at=self.today - timedelta(days=100),
            expiry_days=90,
        )
        result = self.validator.validate([evidence], [], 0)
        self.assertTrue(result.any_expired)
        self.assertIn("expired_evidence", " ".join(result.gaps))

    def test_expired_by_valid_until_produces_gap(self):
        """Evidence expired by valid_until produces gap."""
        evidence = self._make_evidence(
            "年报", "financial_report", "first_hand",
            valid_until=self.today - timedelta(days=1),
        )
        result = self.validator.validate([evidence], [], 0)
        self.assertTrue(result.any_expired)
        self.assertIn("expired_evidence", " ".join(result.gaps))

    def test_unresolved_conflict_blocks_auto_confirm(self):
        """Unresolved conflicts block auto-confirmation."""
        evidence = self._make_evidence(
            "年报", "financial_report", "first_hand",
            supports=["thesis_1"],
        )
        result = self.validator.validate([evidence], [], 1)
        self.assertTrue(result.any_unresolved_conflict)
        self.assertIn("unresolved_conflict", " ".join(result.blocking_reasons))
        self.assertFalse(result.can_auto_confirm)

    def test_mixed_weak_and_first_hand_is_not_all_weak(self):
        """One first_hand among weak sources prevents all_weak block."""
        weak = self._make_evidence("微博", "social_media", "weak")
        strong = self._make_evidence("年报", "financial_report", "first_hand")
        result = self.validator.validate([weak, strong], [], 0)
        self.assertFalse(result.all_weak)

    def test_has_counter_evidence_detected(self):
        """Falsifying evidence provides counter-evidence chain."""
        evidence = self._make_evidence(
            "公告", "announcement", "first_hand",
            supports=["thesis_1"],
        )
        falsifying = self._make_evidence(
            "媒体", "news", "second_hand",
            falsifies=["thesis_1"],
        )
        result = self.validator.validate([evidence], [falsifying], 0)
        self.assertTrue(result.has_counter_evidence)

    def test_enforce_must_have_support(self):
        """Falsifying-only evidence with no support blocks confirmation."""
        falsifying = self._make_evidence("公告", "announcement", "first_hand")
        result = self.validator.validate([], [falsifying], 0)
        self.assertIn("no_supporting_evidence", " ".join(result.blocking_reasons))

    def test_evaluate_level_returns_conflicted_for_conflicts(self):
        """Conflicts force 'conflicted' regardless of quality."""
        result = self.validator.validate([], [], 1)
        level = self.validator.evaluate_evidence_level(result, "strong", 0, 0, 1)
        self.assertEqual(level, "conflicted")

    def test_evaluate_level_returns_falsified_for_falsifying(self):
        """Falsifying evidence forces 'falsified'."""
        result = self.validator.validate([], [], 0)
        level = self.validator.evaluate_evidence_level(result, "medium", 0, 1, 0)
        self.assertEqual(level, "falsified")

    def test_evaluate_level_unknown_for_no_evidence(self):
        """No supporting evidence → unknown."""
        result = self.validator.validate([], [], 0)
        level = self.validator.evaluate_evidence_level(result, "medium", 0, 0, 0)
        self.assertEqual(level, "unknown")


class TestQualityIntegrationWithRunner(unittest.TestCase):
    """Test that quality validator integrates correctly with EvidenceLightRunner."""

    def setUp(self):
        self.runner = EvidenceLightRunner()

    def test_first_hand_support_with_counter_evidence_passes(self):
        """First-hand support + falsifying = quality pass (warnings only)."""
        validation = ValidationResult(flags=[], is_valid=True)
        output = self.runner.run_light_check(
            candidate_id="cand_q1",
            symbol="300750.SZ",
            validation_result=validation,
            inject_supporting_evidence=[{
                "source": "年报2025",
                "source_type": "financial_report",
                "source_quality": "first_hand",
                "description": "ROE > 15%",
                "supports": ["thesis_profitability"],
            }],
            inject_falsifying_evidence=[{
                "source": "券商研报",
                "source_type": "news",
                "source_quality": "second_hand",
                "description": "行业增速放缓",
                "falsifies": ["thesis_growth"],
            }],
        )
        # No quality blocking for first-hand + counter-evidence
        self.assertEqual(output.evidence_level, "falsified")
        blocking_text = " ".join(output.blocking_issues)
        self.assertNotIn("no_source", blocking_text)
        self.assertNotIn("all_weak", blocking_text)

    def test_weak_only_blocks_with_quality_rules(self):
        """All weak sources produces quality blocking."""
        validation = ValidationResult(flags=[], is_valid=True)
        output = self.runner.run_light_check(
            candidate_id="cand_q2",
            symbol="002460.SZ",
            validation_result=validation,
            inject_supporting_evidence=[{
                "source": "互动平台",
                "source_type": "interaction_platform",
                "source_quality": "weak",
                "description": "董秘在线问答",
                "supports": ["thesis_rumor"],
            }],
        )
        self.assertIn("all_weak_sources", " ".join(output.blocking_issues))
        # Level should be capped to 'weak'
        self.assertEqual(output.evidence_level, "weak")

    def test_no_source_evidence_items_block(self):
        """EvidenceItem with source_type='unknown' produces quality block."""
        validation = ValidationResult(flags=[], is_valid=True)
        output = self.runner.run_light_check(
            candidate_id="cand_q3",
            symbol="688005.SH",
            validation_result=validation,
            inject_supporting_evidence=[{
                "source": "未知来源",
                "source_type": "unknown",
                "source_quality": "weak",
                "description": "无来源证据",
                "supports": ["thesis_unknown"],
            }],
        )
        blocking_text = " ".join(output.blocking_issues)
        self.assertIn("no_source", blocking_text)

    def test_expired_evidence_appears_in_gaps(self):
        """Expired evidence appears in evidence_gaps."""
        validation = ValidationResult(flags=[], is_valid=True)
        output = self.runner.run_light_check(
            candidate_id="cand_q4",
            symbol="600519.SH",
            validation_result=validation,
            inject_supporting_evidence=[{
                "source": "年报2024",
                "source_type": "financial_report",
                "source_quality": "first_hand",
                "description": "过期年报数据",
                "published_at": date.today() - timedelta(days=200),
                "expiry_days": 90,
                "supports": ["thesis_stale"],
            }],
        )
        gap_text = " ".join(output.evidence_gaps)
        self.assertIn("expired_evidence", gap_text)


if __name__ == "__main__":
    unittest.main()
