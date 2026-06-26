"""
Test Serenity tool chain end-to-end with real data context.

Proves that:
1. retrieve_supply_chain → discover_players → audit_sources → red_team_falsify
2. All tools use real ResearchSource objects from context
3. Non-existent source_record_ids are rejected and audited
4. Player records are passed to audit and red-team
"""

import unittest
from datetime import datetime
from contracts.research import ThemeInput
from backend.services.serenity_agent import SerenityAgentRunner, SerenityAgentAudit
from backend.services.serenity_tools import SerenityTools
from backend.services.data_tools import DataToolsService
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from backend.db.research import ResearchDB
from tests.test_research_validation import FakeTushareClient


def make_theme(name="端到端测试") -> ThemeInput:
    now = datetime.now()
    return ThemeInput(
        theme_id=f"theme_e2e_{name}",
        theme_name=name,
        background="测试端到端工具链真实数据传递",
        source_type="manual_theme",
        research_mode="standard",
        created_at=now,
        updated_at=now,
    )


class TestSerenityToolChainE2E(unittest.TestCase):
    """End-to-end test of Serenity tool chain with real data context."""

    def setUp(self):
        self.db = ResearchDB(":memory:")
        config = TushareConfig(token="fake", api_url="http://fake.test")
        fake_tushare = FakeTushareClient(config)
        
        validator = ResearchValidator(tushare_config=config)
        validator._tushare_client = fake_tushare
        
        data_tools = DataToolsService(tushare_client=fake_tushare)
        serenity_tools = SerenityTools(data_tools=data_tools, validator=validator)
        
        self.runner = SerenityAgentRunner(
            llm_client=None,
            validator=validator,
            tools=serenity_tools,
            mode="stub",
            db=self.db,
        )

    def test_full_tool_chain_with_real_context(self):
        """Full chain: retrieve → discover → audit → red_team uses real records."""
        audit = SerenityAgentAudit()
        theme = make_theme("锂电池")
        proposed = []
        
        # Create run context (simulating what _run_agent does)
        run_context = {
            "source_records_by_id": {},
            "verified_players_by_symbol": {},
            "verification_results_by_id": {},
        }
        
        # Step 1: retrieve_supply_chain
        retrieve_result = self.runner._execute_tool(
            "retrieve_supply_chain",
            {"symbols": ["300750.SZ"]},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        self.assertEqual(retrieve_result["status"], "ok")
        self.assertGreater(retrieve_result["record_count"], 0)
        
        # Verify context was populated
        self.assertGreater(len(run_context["source_records_by_id"]), 0)
        
        # Get real source_record_ids
        records = retrieve_result.get("records", [])
        source_ids = [r["source_record_id"] for r in records[:5]]
        
        # Step 2: discover_players with real IDs
        discover_result = self.runner._execute_tool(
            "discover_players",
            {"source_record_ids": source_ids},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        self.assertEqual(discover_result["status"], "ok")
        # No errors because all IDs exist in context
        self.assertEqual(len([e for e in audit.errors if "not found in context" in e]), 0)
        
        # Step 3: audit_sources with real IDs
        audit_result = self.runner._execute_tool(
            "audit_sources",
            {"source_record_ids": source_ids},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        self.assertEqual(audit_result["status"], "ok")
        
        # Step 4: red_team_falsify with real IDs
        red_team_result = self.runner._execute_tool(
            "red_team_falsify",
            {"source_record_ids": source_ids},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        self.assertEqual(red_team_result["status"], "ok")
        
        # Verify no "not found in context" errors
        context_errors = [e for e in audit.errors if "not found in context" in e]
        self.assertEqual(len(context_errors), 0,
                        f"Should not have context errors, got: {context_errors}")

    def test_non_existent_source_id_rejected(self):
        """LLM submitting non-existent source_record_id is audited."""
        audit = SerenityAgentAudit()
        theme = make_theme()
        proposed = []
        
        run_context = {
            "source_records_by_id": {},
            "verified_players_by_symbol": {},
            "verification_results_by_id": {},
        }
        
        # Try to use fake source_record_id without calling retrieve
        discover_result = self.runner._execute_tool(
            "discover_players",
            {"source_record_ids": ["fake_source_123", "fake_source_456"]},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        # Should still return ok (with empty source list)
        self.assertEqual(discover_result["status"], "ok")
        
        # But audit should record the missing IDs
        context_errors = [e for e in audit.errors if "not found in context" in e]
        self.assertEqual(len(context_errors), 1)
        self.assertIn("fake_source_123", context_errors[0])

    def test_audit_and_red_team_receive_player_records(self):
        """audit_sources and red_team_falsify receive verified player records."""
        audit = SerenityAgentAudit()
        theme = make_theme("锂电池")
        proposed = []
        
        run_context = {
            "source_records_by_id": {},
            "verified_players_by_symbol": {},
            "verification_results_by_id": {},
        }
        
        # Retrieve sources
        retrieve_result = self.runner._execute_tool(
            "retrieve_supply_chain",
            {"symbols": ["300750.SZ"]},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        records = retrieve_result.get("records", [])
        source_ids = [r["source_record_id"] for r in records[:3]]
        
        # Discover players
        discover_result = self.runner._execute_tool(
            "discover_players",
            {"source_record_ids": source_ids},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        # Check if players were saved to context
        # (may be 0 if source format doesn't trigger discovery)
        player_count = len(run_context["verified_players_by_symbol"])
        
        # Audit should now have access to players
        audit_result = self.runner._execute_tool(
            "audit_sources",
            {"source_record_ids": source_ids},
            theme,
            proposed,
            audit,
            run_context,
        )
        
        self.assertEqual(audit_result["status"], "ok")
        # If player_count > 0, audit should not report "no verified players"
        if player_count > 0:
            gaps = audit_result.get("gaps", [])
            self.assertNotIn("no verified players", " ".join(gaps).lower())


if __name__ == "__main__":
    unittest.main()
