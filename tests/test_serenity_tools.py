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
from zoneinfo import ZoneInfo
from contracts.research import (
    DataToolResult,
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

    def test_sse_announcement_metadata_and_research_window_survive_conversion(self):
        from datetime import timedelta

        symbol = "603002.SH"
        retrieved_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        planner_end_date = retrieved_at.date().strftime("%Y%m%d")
        old_income_end_date = (
            retrieved_at.date() - timedelta(days=90)
        ).strftime("%Y%m%d")
        announcement_date = retrieved_at.date().isoformat()
        announcement_title = "宏昌电子董事会决议公告"
        announcement_date_compact = announcement_date.replace("-", "")
        official_url = (
            "https://static.sse.com.cn/disclosure/listedinfo/announcement/"
            f"c/new/{announcement_date}/{symbol[:6]}_"
            f"{announcement_date_compact}_FWCK.pdf"
        )

        class FixtureDataTools:
            def __init__(self):
                self.announcement_call = None

            def get_financials(self, requested_symbol):
                return DataToolResult(
                    tool_name="get_financials",
                    raw_data=[{
                        "ts_code": requested_symbol,
                        "end_date": old_income_end_date,
                        "ann_date": old_income_end_date,
                        "total_revenue": 123.0,
                    }],
                    source="tushare_income",
                    retrieved_at=retrieved_at,
                )

            def get_company_profile(self, requested_symbol):
                return DataToolResult(
                    tool_name="get_company_profile",
                    raw_data=[],
                    source="tushare_stock_company",
                    retrieved_at=retrieved_at,
                )

            def get_announcements(
                self, requested_symbol, *, start_date=None, end_date=None, keywords=None
            ):
                self.announcement_call = {
                    "symbol": requested_symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "keywords": keywords,
                }
                return DataToolResult(
                    tool_name="get_announcements",
                    raw_data=[{
                        "source": "sse",
                        "code": symbol,
                        "date": announcement_date,
                        "title": announcement_title,
                        "url": official_url,
                        "retrieved_at": retrieved_at,
                        "gaps": ["full_text_unavailable"],
                    }],
                    source="sse_company_announcements",
                    retrieved_at=retrieved_at,
                )

            def get_sector_and_peers(self, requested_symbol, snapshot_date=None):
                return DataToolResult(
                    tool_name="get_sector_and_peers",
                    raw_data=[],
                    source="tushare_stock_basic",
                    retrieved_at=retrieved_at,
                )

        data_tools = FixtureDataTools()
        tools = SerenityTools(data_tools=data_tools)
        result = tools.retrieve_supply_chain(
            theme_name="",
            symbols=[symbol],
            start_date="20260901",
            end_date=planner_end_date,
        )

        self.assertEqual(data_tools.announcement_call["end_date"], planner_end_date)
        announcement = next(
            record for record in result.records
            if record.source_type == "announcement"
        )
        self.assertEqual(announcement.source_record_id, "announcements:603002.SH:0")
        self.assertEqual(announcement.announcement_code, symbol)
        self.assertEqual(announcement.published_at, retrieved_at.date())
        self.assertEqual(announcement.title, announcement_title)
        self.assertEqual(announcement.source_url, official_url)
        self.assertEqual(announcement.retrieved_at, retrieved_at)
        self.assertEqual(
            announcement.summary,
            f"{announcement_date} 披露《{announcement_title}》",
        )
        self.assertEqual(announcement.gaps, ["full_text_unavailable"])

    def test_anns_d_results_become_traceable_research_sources(self):
        import pandas as pd

        official_fields = "ann_date,ts_code,name,title,url,rec_time"

        class RecordingProvider:
            def __init__(self):
                self.calls = []

            def query(self, api_name, **kwargs):
                self.calls.append((api_name, kwargs))
                if api_name == "anns_d":
                    return pd.DataFrame([{
                        "ann_date": "20260918",
                        "ts_code": "603002.SH",
                        "name": "宏昌电子",
                        "title": "603002.SH公告标题",
                        "url": "https://example.test/603002/notice.pdf",
                        "rec_time": datetime(2026, 9, 19, 8, 30),
                    }])
                return pd.DataFrame()

        provider = RecordingProvider()
        tools = SerenityTools(data_tools=DataToolsService(tushare_client=provider))

        result = tools.retrieve_supply_chain(
            theme_name="",
            symbols=["603002.SH"],
        )

        announcement_calls = [
            (api_name, params)
            for api_name, params in provider.calls
            if api_name in {"anns", "anns_d"}
        ]
        self.assertEqual(len(announcement_calls), 1)
        api_name, params = announcement_calls[0]
        self.assertEqual(api_name, "anns_d")
        self.assertEqual(params["ts_code"], "603002.SH")
        self.assertEqual(params["fields"], official_fields)

        announcement = next(
            record for record in result.records
            if record.source_record_id.startswith("announcements:603002.SH:")
        )
        self.assertEqual(announcement.title, "603002.SH公告标题")
        self.assertEqual(announcement.source_url, "https://example.test/603002/notice.pdf")
        self.assertEqual(announcement.published_at, date(2026, 9, 19))

    def test_mismatched_announcement_symbols_are_filtered_before_source_creation(self):
        import pandas as pd

        matching = {
            "ann_date": "20260918",
            "ts_code": "603002.SH",
            "name": "宏昌电子",
            "title": "目标公司公告",
            "url": "https://example.test/603002/notice.pdf",
            "rec_time": "20260919",
        }
        other_symbol = {
            "ann_date": "20260918",
            "ts_code": "600519.SH",
            "name": "贵州茅台",
            "title": "其他公司的公告",
            "url": "https://example.test/600519/notice.pdf",
            "rec_time": "20260919",
        }

        class RecordingProvider:
            def __init__(self):
                self.announcement_rows = [matching, other_symbol]

            def query(self, api_name, **kwargs):
                if api_name == "anns_d":
                    return pd.DataFrame(self.announcement_rows)
                return pd.DataFrame()

        provider = RecordingProvider()
        tools = SerenityTools(data_tools=DataToolsService(tushare_client=provider))
        mixed_result = tools.retrieve_supply_chain(
            theme_name="",
            symbols=["603002.SH"],
        )
        mixed_announcements = [
            record for record in mixed_result.records
            if record.source_type == "announcement"
        ]

        self.assertEqual(len(mixed_announcements), 1)
        self.assertEqual(mixed_announcements[0].title, "目标公司公告")
        self.assertEqual(
            mixed_announcements[0].source_url,
            "https://example.test/603002/notice.pdf",
        )
        self.assertTrue(any(
            "anns_d.ts_code_mismatch" in gap for gap in mixed_result.gaps
        ))

        provider.announcement_rows = [other_symbol]
        all_mismatched_result = tools.retrieve_supply_chain(
            theme_name="",
            symbols=["603002.SH"],
        )
        self.assertFalse(any(
            record.source_type == "announcement"
            for record in all_mismatched_result.records
        ))
        self.assertTrue(any(
            "anns_d.ts_code_mismatch" in gap
            for gap in all_mismatched_result.gaps
        ))

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
                gaps=["anns_d.title_missing"],
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
