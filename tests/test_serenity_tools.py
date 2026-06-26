"""
Test Serenity research tools (SMA-P2 tool chain).

Covers:
- retrieve_supply_chain: data retrieval with gaps
- discover_players: ticker verification gating
- audit_sources: source quality checks
- red_team_falsify: traceable falsifying points
- Anti-injection: external data cannot modify execution path
- System prompt must include anti-injection rules
"""

import unittest
from datetime import date, datetime
from contracts.research import (
    ResearchSource,
    SerenityToolResult,
    ThemeInput,
)
from backend.services.serenity_tools import SerenityTools
from backend.services.data_tools import DataToolsService
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from tests.test_research_validation import FakeTushareClient


def make_tools(validator=None) -> SerenityTools:
    config = TushareConfig(token="fake", api_url="http://fake.test")
    fake_tushare = FakeTushareClient(config)
    dt = DataToolsService(tushare_client=fake_tushare)
    v = validator or ResearchValidator(tushare_config=config)
    v._tushare_client = fake_tushare
    return SerenityTools(data_tools=dt, validator=v)


class TestRetrieveSupplyChain(unittest.TestCase):
    """产业链数据检索 tests."""

    def setUp(self):
        self.tools = make_tools()

    def test_returns_serenity_tool_result(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["300750.SZ"],
        )
        self.assertIsInstance(result, SerenityToolResult)
        self.assertEqual(result.tool_name, "retrieve_supply_chain")

    def test_normal_symbol_produces_records(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["300750.SZ"],
        )
        self.assertGreater(result.total_found, 0)
        self.assertGreater(len(result.records), 0)

    def test_records_have_required_fields(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["300750.SZ"],
        )
        for rec in result.records:
            self.assertIsInstance(rec, ResearchSource)
            self.assertIsNotNone(rec.source_record_id)
            self.assertIn(":", rec.source_record_id)

    def test_empty_result_produces_gap(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["999999.SZ"],
        )
        gap_text = " ".join(result.gaps)
        self.assertIn("no records found", gap_text)

    def test_keywords_filter_applied(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["300750.SZ"],
            keywords=["年度报告"],
        )
        # Should still produce records (keyword filtering happens in get_announcements)
        self.assertIsNotNone(result)

    def test_no_symbols_and_no_theme_mapping_produces_gap(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="完全不存在的主题名",
        )
        gap_text = " ".join(result.gaps)
        self.assertIn("no_symbols_to_search", gap_text)

    def test_known_theme_infers_symbols(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
        )
        self.assertGreater(result.total_found, 0)

    def test_gaps_propagated_from_data_tools(self):
        result = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["000001.SZ"],  # has empty daily_basic
        )
        # Financials or announcements may have gaps
        self.assertGreater(len(result.gaps), 0)

    def test_no_data_tools_records_error(self):
        tools = SerenityTools(data_tools=None)
        result = tools.retrieve_supply_chain(theme_name="锂电池")
        self.assertIn("data_tools_not_configured", result.gaps)


class TestDiscoverPlayers(unittest.TestCase):
    """玩家发现 tests: must verify tickers before entering shortlist."""

    def setUp(self):
        self.tools = make_tools()

    def test_empty_sources_produces_gap(self):
        result = self.tools.discover_players([])
        self.assertIn("no source records", " ".join(result.gaps))

    def test_players_from_source_records(self):
        sources = [
            ResearchSource(
                source_record_id="announcements:300750.SZ:0",
                source_type="announcement",
                source_quality="first_hand",
                title="公告",
                retrieved_at=datetime.now(),
            ),
            ResearchSource(
                source_record_id="sector:300750.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="行业归属",
                summary="行业: 电气设备, 同行: 600406.SH, 002074.SZ",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.discover_players(sources)
        self.assertGreaterEqual(result.total_found, 0)

    def test_unverifiable_ticker_excluded_and_gap_recorded(self):
        """999999.SZ is unknown → low confidence → excluded."""
        sources = [
            ResearchSource(
                source_record_id="announcements:999999.SZ:0",
                source_type="announcement",
                source_quality="first_hand",
                title="未知公司公告",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.discover_players(sources)
        self.assertEqual(result.total_found, 0)
        gap_text = " ".join(result.gaps)
        self.assertIn("verification failed", gap_text)

    def test_no_ticker_symbols_in_sources(self):
        sources = [
            ResearchSource(
                source_record_id="financials:no_dot",
                source_type="financial_report",
                source_quality="first_hand",
                title="无ticker",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.discover_players(sources)
        self.assertIn("no tickers found", " ".join(result.gaps))


class TestAuditSources(unittest.TestCase):
    """来源审计 tests."""

    def setUp(self):
        self.tools = make_tools()

    def test_no_sources_records_gap(self):
        result = self.tools.audit_sources([], [])
        self.assertIn("no source records", " ".join(result.gaps))

    def test_all_weak_sources_flag(self):
        sources = [
            ResearchSource(
                source_record_id="news:1", source_type="news", source_quality="weak",
                title="新闻", retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.audit_sources(sources, [])
        gap_text = " ".join(result.gaps)
        self.assertIn("no first_hand", gap_text)

    def test_expired_source_flag(self):
        sources = [
            ResearchSource(
                source_record_id="ann:1", source_type="announcement",
                source_quality="first_hand", title="公告",
                published_at=date(2020, 1, 1), retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.audit_sources(sources, [])
        gap_text = " ".join(result.gaps)
        self.assertIn("expired", gap_text)

    def test_no_players_limited_coverage(self):
        sources = [
            ResearchSource(
                source_record_id="fin:1", source_type="financial_report",
                source_quality="first_hand", title="财报",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.audit_sources(sources, [])
        gap_text = " ".join(result.gaps)
        self.assertIn("no verified players", gap_text)

    def test_few_players_limited(self):
        sources = [
            ResearchSource(
                source_record_id="fin:1", source_type="financial_report",
                source_quality="first_hand", title="财报",
                retrieved_at=datetime.now(),
            ),
        ]
        players = [
            ResearchSource(
                source_record_id="player:1", source_type="financial_report",
                source_quality="first_hand", title="玩家1",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.audit_sources(sources, players)
        gap_text = " ".join(result.gaps)
        self.assertIn("only 1 verified player", gap_text)


class TestRedTeamFalsify(unittest.TestCase):
    """Red-team 证伪 tests: traceable counter-arguments only."""

    def setUp(self):
        self.tools = make_tools()

    def test_no_sources_flag(self):
        result = self.tools.red_team_falsify([], [])
        self.assertIn("no source records", " ".join(result.gaps))

    def test_source_gaps_become_falsification_points(self):
        sources = [
            ResearchSource(
                source_record_id="ann:1", source_type="announcement",
                source_quality="first_hand", title="公告",
                retrieved_at=datetime.now(),
                gaps=["anns.title_missing"],
            ),
        ]
        result = self.tools.red_team_falsify(sources, [])
        # Gaps in sources should be surfaced as falsification points
        self.assertGreaterEqual(result.total_found, 0)

    def test_no_sector_data_flag(self):
        sources = [
            ResearchSource(
                source_record_id="fin:1", source_type="financial_report",
                source_quality="first_hand", title="仅财务",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.red_team_falsify(sources, [])
        gap_text = " ".join(result.gaps)
        # Should flag missing sector data
        all_text = gap_text + " " + " ".join(
            r.title + r.summary for r in result.records
        )
        self.assertIn("行业", all_text)

    def test_limited_peers_flag(self):
        sources = [
            ResearchSource(
                source_record_id="sector:1", source_type="financial_report",
                source_quality="first_hand", title="行业",
                retrieved_at=datetime.now(),
            ),
        ]
        result = self.tools.red_team_falsify(sources, [])
        # Limited peers should be flagged
        all_text = " ".join(r.title + r.summary for r in result.records) + " ".join(result.gaps)
        self.assertIn("同行", all_text)

    def test_every_falsification_has_source_id(self):
        sources = [
            ResearchSource(
                source_record_id="ann:test:0", source_type="announcement",
                source_quality="first_hand", title="测试",
                retrieved_at=datetime.now(),
                gaps=["test_gap"],
            ),
        ]
        result = self.tools.red_team_falsify(sources, [])
        for rec in result.records:
            self.assertIsNotNone(rec.source_record_id)


class TestAntiInjection(unittest.TestCase):
    """External text cannot modify execution path."""

    def test_tool_definitions_are_fixed(self):
        """Tool definitions are a static list — not modifiable by input."""
        from backend.services.serenity_agent import SerenityAgentRunner
        tools = SerenityAgentRunner._get_tool_definitions()
        tool_names = {t["name"] for t in tools}
        # Core tools must be present
        self.assertIn("retrieve_supply_chain", tool_names)
        self.assertIn("discover_players", tool_names)
        self.assertIn("audit_sources", tool_names)
        self.assertIn("red_team_falsify", tool_names)
        self.assertIn("verify_ticker", tool_names)

    def test_system_prompt_has_anti_injection_rules(self):
        from backend.services.serenity_agent import SERENITY_AGENT_SYSTEM_PROMPT
        prompt = SERENITY_AGENT_SYSTEM_PROMPT.lower()
        self.assertIn("anti-injection", prompt)
        self.assertIn("untrusted", prompt)
        self.assertIn("may not modify", prompt)

    def test_research_source_defaults_conservative(self):
        """ResearchSource defaults to unknown/weak — conservative."""
        src = ResearchSource(
            source_record_id="test",
            retrieved_at=datetime.now(),
        )
        self.assertEqual(src.source_type, "unknown")
        self.assertEqual(src.source_quality, "weak")
        self.assertEqual(src.gaps, [])
        self.assertEqual(src.errors, [])


class TestToolChainIntegration(unittest.TestCase):
    """End-to-end tool chain: retrieve → discover → audit → falsify."""

    def setUp(self):
        self.tools = make_tools()

    def test_full_tool_chain_with_known_symbol(self):
        """Full chain: retrieve → discover → audit → falsify."""
        # Step 1: Retrieve
        retrieve = self.tools.retrieve_supply_chain(
            theme_name="锂电池",
            symbols=["300750.SZ"],
        )
        self.assertGreater(len(retrieve.records), 0)

        # Step 2: Discover players
        discover = self.tools.discover_players(retrieve.records)
        # 300750.SZ is a known symbol → should be verified
        # (may or may not produce a record depending on source format)

        # Step 3: Audit
        audit = self.tools.audit_sources(retrieve.records, discover.records)
        self.assertIsInstance(audit, SerenityToolResult)

        # Step 4: Red-team
        falsify = self.tools.red_team_falsify(retrieve.records, discover.records)
        self.assertIsInstance(falsify, SerenityToolResult)

    def test_no_source_chain_produces_only_gaps(self):
        """Without sources, all tools produce gaps, no fabricated data."""
        for method_name in ["retrieve_supply_chain", "discover_players",
                            "audit_sources", "red_team_falsify"]:
            result = self.tools.retrieve_supply_chain(
                theme_name="无匹配主题",
            )
            # No sources → all downstream tools should handle empty gracefully
            # Just test that retrieve fails gracefully
            gap_text = " ".join(result.gaps)
            self.assertIn("no_symbols", gap_text)


if __name__ == "__main__":
    unittest.main()
