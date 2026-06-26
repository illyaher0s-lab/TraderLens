"""
Test Serenity stub runner.

These tests prove:
- quick_scan limits shortlist size to at most 3
- standard limits shortlist size to at most 5
- deep_research limits shortlist size to at most 10
- manual stocks are preserved in raw candidate pool
- output contains evidence gaps and hypothesis draft
- stub output conforms to the same SerenityOutput contract future agent must use
- harness metadata is present and replayable
- harness provider is 'stub'
- runner output contains no applied state mutation
"""

import unittest
from datetime import datetime
from backend.services.serenity_stub import SerenityStubRunner
from contracts.research import ThemeInput, CandidateStock


class TestSerenityStub(unittest.TestCase):
    """Test Serenity stub runner."""

    def setUp(self):
        """Set up stub runner."""
        self.runner = SerenityStubRunner()

    def test_quick_scan_limits_shortlist_to_3(self):
        """quick_scan limits shortlist size to at most 3."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_001",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="quick_scan",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        self.assertLessEqual(len(output.candidate_shortlist), 3)

    def test_standard_limits_shortlist_to_5(self):
        """standard limits shortlist size to at most 5."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_002",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        self.assertLessEqual(len(output.candidate_shortlist), 5)

    def test_deep_research_limits_shortlist_to_10(self):
        """deep_research limits shortlist size to at most 10."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_003",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="deep_research",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        self.assertLessEqual(len(output.candidate_shortlist), 10)

    def test_manual_stocks_preserved_in_raw_pool(self):
        """Manual stocks are preserved in raw candidate pool."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_004",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        manual_candidates = [
            CandidateStock(
                candidate_id="cand_001",
                theme_id="theme_004",
                symbol="300750.SZ",
                company_name="宁德时代",
                source_type="manual_stock",
                match_reason="用户手动添加",
                status="raw",
                created_at=now,
            )
        ]
        
        output = self.runner.run(theme, manual_candidates=manual_candidates)
        
        # Check manual candidate is in raw pool
        raw_symbols = [c.symbol for c in output.candidate_pool_raw]
        self.assertIn("300750.SZ", raw_symbols)

    def test_output_contains_evidence_gaps_and_hypothesis(self):
        """Output contains evidence gaps and hypothesis draft."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_005",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        
        self.assertIsInstance(output.evidence_gaps, list)
        self.assertIsInstance(output.hypothesis_draft, list)

    def test_stub_conforms_to_serenity_output_contract(self):
        """Stub output conforms to the same SerenityOutput contract future agent must use."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_006",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        
        # Check all required fields exist
        self.assertEqual(output.theme_id, "theme_006")
        self.assertIsInstance(output.demand_driver, str)
        self.assertIsInstance(output.value_chain_layers, list)
        self.assertIsInstance(output.suspected_bottleneck_layers, list)
        self.assertIsInstance(output.candidate_pool_raw, list)
        self.assertIsInstance(output.candidate_shortlist, list)
        self.assertIsInstance(output.hypothesis_draft, list)
        self.assertIsInstance(output.evidence_gaps, list)
        self.assertIsNotNone(output.harness)

    def test_harness_metadata_present_and_replayable(self):
        """Harness metadata is present and replayable."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_007",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        
        self.assertTrue(output.harness.replayable)
        self.assertIsInstance(output.harness.tool_whitelist, list)
        self.assertIsInstance(output.harness.max_steps, int)
        self.assertIsInstance(output.harness.token_budget, int)

    def test_harness_provider_is_stub(self):
        """Harness provider is 'stub'."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_008",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        
        self.assertEqual(output.harness.provider, "stub")

    def test_runner_output_contains_no_applied_state_mutation(self):
        """Runner output contains no applied state mutation."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_009",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        
        output = self.runner.run(theme, manual_candidates=[])
        
        # SerenityOutput is pure data, no state mutation
        # All candidates have status='raw' or 'shortlisted', never 'confirmed'
        for candidate in output.candidate_pool_raw:
            self.assertIn(candidate.status, ["raw", "shortlisted"])
        for candidate in output.candidate_shortlist:
            self.assertIn(candidate.status, ["raw", "shortlisted"])


if __name__ == "__main__":
    unittest.main()
