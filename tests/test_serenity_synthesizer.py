"""
Tests for Serenity Research Synthesizer (LLM 2/2).

验证:
- 单次 LLM 调用
- 输出符合 schema
- 验证所有 source IDs 存在
- 拒绝不存在的 source IDs
- 无效 JSON 明确失败
- LLM 不能覆盖 company_name
"""

import unittest
import json
from datetime import datetime, date
from backend.services.serenity_synthesizer import ResearchSynthesizer, ResearchSynthesis
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit, VerifiedResearchCandidate
from backend.services.data_tools import DataToolsService
from backend.services.serenity_tools import SerenityTools
from contracts.research import ThemeInput, ResearchSource


class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.call_count = 0
    
    def create_message(self, messages, system, max_tokens):
        self.call_count += 1
        return {
            "content": [{"type": "text", "text": self.response_text}]
        }


class TestResearchSynthesizer(unittest.TestCase):

    def test_sse_metadata_and_full_text_gap_are_preserved_for_synthesis(self):
        source_time = datetime(2026, 9, 26, 12, 0)
        announcement_date = date(2026, 9, 12)
        announcement_title = "宏昌电子第七届董事会第四次会议决议公告"
        official_url = (
            "https://static.sse.com.cn/disclosure/listedinfo/announcement/"
            "c/new/2026-09-12/603002_20260912_FWCK.pdf"
        )
        sources = [
            ResearchSource(
                source_record_id="announcements:603002.SH:0",
                source_type="announcement",
                source_quality="first_hand",
                title=announcement_title,
                published_at=announcement_date,
                retrieved_at=source_time,
                summary=f"{announcement_date.isoformat()} 披露《{announcement_title}》",
                source_url=official_url,
                announcement_code="603002.SH",
                gaps=["full_text_unavailable"],
            ),
            ResearchSource(
                source_record_id="financials:603002.SH:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="宏昌电子财务数据",
                published_at=date(2026, 8, 15),
                retrieved_at=source_time,
                summary="报告期: 20260630; 营业总收入: 123.0",
            ),
            ResearchSource(
                source_record_id="stock_company:603002.SH:0",
                source_type="unknown",
                source_quality="weak",
                title="公司主营业务: 宏昌电子",
                retrieved_at=source_time,
                summary="主营业务: 电子元器件的研发、生产和销售。",
            ),
        ]

        class CapturingLLM:
            def create_message(self, messages, system, max_tokens):
                self.messages = messages
                self.system = system
                return {
                    "content": [{
                        "type": "text",
                        "text": json.dumps({
                            "demand_driver": "",
                            "value_chain_layers": [],
                            "suspected_bottleneck_layers": [],
                            "hypothesis_draft": [],
                            "candidate_rationales": {},
                            "evidence_gaps": [],
                        }),
                    }],
                }

        llm = CapturingLLM()
        context = SerenityRunContext(
            sources_by_id={source.source_record_id: source for source in sources},
        )
        theme = ThemeInput(
            theme_id="sse-metadata-synthesis-test",
            theme_name="公告元数据边界测试",
            background="只测试可信来源元数据及其缺口传递",
            source_type="manual_theme",
            created_at=source_time,
            updated_at=source_time,
        )

        synthesis = ResearchSynthesizer(llm).synthesize(
            theme, context, SerenityAgentAudit(),
        )

        prompt = llm.messages[0]["content"]
        source_summary_json = prompt.split("来源摘要 (3 个):\n", 1)[1].split(
            "\n\n请整合", 1,
        )[0]
        source_summaries = json.loads(source_summary_json)
        announcement = next(
            item for item in source_summaries
            if item["id"] == "announcements:603002.SH:0"
        )
        self.assertEqual(announcement.get("as_of"), "2026-09-12")
        self.assertEqual(announcement.get("source_url"), official_url)
        self.assertEqual(
            announcement.get("summary"),
            f"2026-09-12 披露《{announcement_title}》",
        )
        self.assertIn("full_text_unavailable", announcement.get("gaps", []))
        self.assertIn("公告标题和日期不能用于推断公告正文", llm.system)
        self.assertTrue(any(
            "full_text_unavailable" in gap
            for gap in synthesis.evidence_gaps
        ))

    def _serenity_tools_for_income_rows(self, rows):
        import pandas as pd

        class IncomeProvider:
            def query(self, api_name, **kwargs):
                if api_name == "income":
                    return pd.DataFrame(rows)
                return pd.DataFrame()

        data_tools = DataToolsService(tushare_client=IncomeProvider())
        return data_tools, SerenityTools(data_tools=data_tools)

    def _serenity_tools_for_company_rows(self, rows):
        import pandas as pd

        class CompanyProvider:
            def __init__(self):
                self.calls = []
                self.company_rows = rows

            def query(self, api_name, **kwargs):
                self.calls.append((api_name, kwargs))
                if api_name == "stock_company":
                    return pd.DataFrame(self.company_rows)
                return pd.DataFrame()

        provider = CompanyProvider()
        data_tools = DataToolsService(tushare_client=provider)
        return provider, SerenityTools(data_tools=data_tools)

    def test_company_main_business_reaches_synthesizer_with_retrieval_as_of(self):
        target_symbol = "603002.SH"
        rows = [
            {
                "ts_code": target_symbol,
                "com_name": "宏昌电子股份有限公司",
                "main_business": "电子元器件的研发、生产和销售。",
                "business_scope": "范围说明不应冒充主营事实。",
            },
            {
                "ts_code": "600519.SH",
                "com_name": "贵州茅台酒股份有限公司",
                "main_business": "白酒生产与销售。",
                "business_scope": "其他公司的经营范围。",
            },
        ]
        provider, serenity_tools = self._serenity_tools_for_company_rows(rows)

        retrieved = serenity_tools.retrieve_supply_chain(
            theme_name="",
            symbols=[target_symbol],
        )
        company_sources = [
            source for source in retrieved.records
            if source.source_record_id.startswith(f"stock_company:{target_symbol}:")
        ]
        self.assertEqual(len(company_sources), 1)
        api_calls = [call for call in provider.calls if call[0] == "stock_company"]
        self.assertEqual(len(api_calls), 1)
        self.assertEqual(api_calls[0][1]["ts_code"], target_symbol)
        self.assertEqual(
            api_calls[0][1]["fields"],
            "ts_code,com_name,main_business,business_scope",
        )
        self.assertTrue(any(
            "stock_company.ts_code_mismatch" in gap for gap in retrieved.gaps
        ))

        source = company_sources[0]
        self.assertEqual(source.source_record_id, f"stock_company:{target_symbol}:0")
        self.assertEqual(source.source_type, "unknown")
        self.assertEqual(source.source_quality, "weak")
        self.assertIsNone(source.published_at)
        self.assertIn("主营业务: 电子元器件的研发、生产和销售。", source.summary)
        self.assertNotIn("经营范围", source.summary)
        self.assertLessEqual(len(source.summary), 500)

        context = SerenityRunContext(
            sources_by_id={source.source_record_id: source},
        )
        theme = ThemeInput(
            theme_id="company-profile-summary-test",
            theme_name="公司主营事实传递",
            background="只检查公司主营事实与来源时间",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        prompt, _ = ResearchSynthesizer(llm_client=None)._build_research_pack(
            theme,
            context,
        )
        source_summary_json = prompt.split("来源摘要 (1 个):\n", 1)[1].split(
            "\n\n请整合",
            1,
        )[0]
        source_summary = json.loads(source_summary_json)[0]
        self.assertEqual(source_summary["id"], source.source_record_id)
        self.assertEqual(source_summary["summary"], source.summary)
        self.assertEqual(source_summary["as_of"], source.retrieved_at.isoformat())
        self.assertEqual(source_summary["as_of_basis"], "retrieved_at")
        self.assertLessEqual(len(source_summary["summary"]), 500)

    def test_mismatched_or_empty_company_business_is_gap_not_source(self):
        target_symbol = "603002.SH"
        rows = [
            {
                "ts_code": "600519.SH",
                "com_name": "贵州茅台酒股份有限公司",
                "main_business": "白酒生产与销售。",
            },
            {
                "ts_code": target_symbol,
                "com_name": "宏昌电子股份有限公司",
                "main_business": "   ",
            },
        ]
        provider, serenity_tools = self._serenity_tools_for_company_rows(rows)

        retrieved = serenity_tools.retrieve_supply_chain(
            theme_name="",
            symbols=[target_symbol],
        )
        company_sources = [
            source for source in retrieved.records
            if source.source_record_id.startswith("stock_company:")
        ]
        self.assertEqual(company_sources, [])
        gap_text = " ".join(retrieved.gaps)
        self.assertIn("stock_company.ts_code_mismatch", gap_text)
        self.assertIn("stock_company.main_business_missing", gap_text)

        provider.company_rows = []
        empty_result = serenity_tools.retrieve_supply_chain(
            theme_name="",
            symbols=[target_symbol],
        )
        self.assertFalse(any(
            source.source_record_id.startswith("stock_company:")
            for source in empty_result.records
        ))
        self.assertIn("stock_company_data_empty", " ".join(empty_result.gaps))

    def test_financial_facts_flow_to_synthesizer_source_summary(self):
        target_symbol = "603002.SH"
        rows = [
            {
                "ts_code": target_symbol,
                "end_date": "20260630",
                "ann_date": "20260815",
                "total_revenue": 1200000.5,
                "revenue": 1150000.25,
                "n_income_attr_p": 0,
                "basic_eps": 0.0,
                "ebitda": 987654321,
            },
            {
                "ts_code": "600519.SH",
                "end_date": "20260630",
                "ann_date": "20260816",
                "total_revenue": 999999999,
                "n_income_attr_p": 888888888,
                "basic_eps": 99.0,
            },
        ]
        data_tools, serenity_tools = self._serenity_tools_for_income_rows(rows)

        financial_result = data_tools.get_financials(target_symbol)
        self.assertEqual(
            [row["ts_code"] for row in financial_result.raw_data],
            [target_symbol],
        )
        self.assertTrue(any(
            "income.ts_code_mismatch" in gap for gap in financial_result.gaps
        ))

        retrieved = serenity_tools.retrieve_supply_chain(
            theme_name="",
            symbols=[target_symbol],
        )
        financial_sources = [
            source for source in retrieved.records
            if source.source_record_id.startswith(f"financials:{target_symbol}:")
        ]
        self.assertEqual(len(financial_sources), 1)
        source = financial_sources[0]
        self.assertEqual(source.source_record_id, f"financials:{target_symbol}:0")
        self.assertEqual(source.published_at, date(2026, 8, 15))
        self.assertIn("报告期: 20260630", source.summary)
        self.assertIn("披露日: 20260815", source.summary)
        self.assertIn("营业总收入: 1200000.5", source.summary)
        self.assertIn("归母净利润: 0", source.summary)
        self.assertIn("基本每股收益: 0.0", source.summary)
        self.assertNotIn("987654321", source.summary)

        context = SerenityRunContext(
            sources_by_id={source.source_record_id: source},
        )
        theme = ThemeInput(
            theme_id="financial-summary-test",
            theme_name="财务数据传递",
            background="只检查来源事实传递",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        prompt, _ = ResearchSynthesizer(llm_client=None)._build_research_pack(
            theme,
            context,
        )
        source_summary_json = prompt.split("来源摘要 (1 个):\n", 1)[1].split(
            "\n\n请整合",
            1,
        )[0]
        source_summary = json.loads(source_summary_json)[0]
        self.assertEqual(source_summary["id"], source.source_record_id)
        self.assertEqual(source_summary["as_of"], "2026-08-15")
        self.assertIn("营业总收入: 1200000.5", source_summary["summary"])
        self.assertLessEqual(len(source_summary["summary"]), 500)

    def test_mismatched_or_non_numeric_income_rows_are_gaps_not_sources(self):
        target_symbol = "603002.SH"
        rows = [
            {
                "ts_code": "600519.SH",
                "end_date": "20260630",
                "ann_date": "20260816",
                "total_revenue": 999999999,
                "n_income_attr_p": 888888888,
                "basic_eps": 99.0,
            },
            {
                "ts_code": target_symbol,
                "end_date": "20260630",
                "ann_date": "20260815",
                "total_revenue": None,
                "n_income_attr_p": float("nan"),
                "basic_eps": "not numeric",
            },
        ]
        _, serenity_tools = self._serenity_tools_for_income_rows(rows)

        retrieved = serenity_tools.retrieve_supply_chain(
            theme_name="",
            symbols=[target_symbol],
        )
        financial_sources = [
            source for source in retrieved.records
            if source.source_record_id.startswith(f"financials:{target_symbol}:")
        ]
        self.assertEqual(financial_sources, [])
        gap_text = " ".join(retrieved.gaps)
        self.assertIn("income.ts_code_mismatch", gap_text)
        self.assertIn(
            f"financials:{target_symbol}:no_usable_numeric_values",
            gap_text,
        )

    def _create_test_context(self):
        """Create a minimal test context."""
        context = SerenityRunContext()
        
        # Add a source
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
        )
        
        # Add a verified candidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["needs_verification"],
            data_gaps=[],
            unresolved_gaps=[],
        )
        
        return context
    
    def test_synthesizer_single_llm_call(self):
        """Synthesizer makes exactly 1 LLM call."""
        mock_llm = MockLLMClient('''{
            "demand_driver": "新能源汽车需求增长",
            "value_chain_layers": [{"layer": "上游", "description": "锂矿开采"}],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": []
        }''')
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        self.assertEqual(mock_llm.call_count, 1)
        self.assertIsInstance(synthesis, ResearchSynthesis)
    
    def test_synthesizer_produces_valid_schema(self):
        """Synthesizer output conforms to ResearchSynthesis schema."""
        mock_llm = MockLLMClient('''{
            "demand_driver": "新能源汽车需求增长",
            "value_chain_layers": [
                {"layer": "上游", "description": "锂矿开采"},
                {"layer": "中游", "description": "电池制造"}
            ],
            "suspected_bottleneck_layers": [
                {"layer": "中游", "reason": "产能限制", "supporting_source_ids": ["financials:300750.SZ:0"]}
            ],
            "hypothesis_draft": [
                {"hypothesis": "中游产能扩张", "rationale": "需求增长", "confidence": "medium"}
            ],
            "candidate_rationales": {
                "300750.SZ": {
                    "rationale": "产业链核心",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            "evidence_gaps": ["需要验证产能计划"]
        }''')
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        self.assertEqual(synthesis.demand_driver, "新能源汽车需求增长")
        self.assertEqual(len(synthesis.value_chain_layers), 2)
        self.assertEqual(len(synthesis.suspected_bottleneck_layers), 1)
        self.assertEqual(len(synthesis.hypothesis_draft), 1)
        self.assertIn("300750.SZ", synthesis.candidate_rationales)
        self.assertEqual(len(synthesis.evidence_gaps), 1)
    
    def test_synthesizer_validates_source_ids(self):
        """Synthesizer validates all source IDs exist in context."""
        mock_llm = MockLLMClient('''{
            "demand_driver": "测试",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [
                {"layer": "中游", "reason": "测试", "supporting_source_ids": ["financials:300750.SZ:0"]}
            ],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": []
        }''')
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        # 应该成功，因为 financials:300750.SZ:0 存在于 context
        synthesis = synthesizer.synthesize(theme, context, audit)
        self.assertEqual(len(synthesis.suspected_bottleneck_layers), 1)
    
    def test_synthesizer_rejects_non_existent_ids(self):
        """Synthesizer rejects non-existent source IDs."""
        mock_llm = MockLLMClient('''{
            "demand_driver": "测试",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [
                {"layer": "中游", "reason": "测试", "supporting_source_ids": ["fake:id:999"]}
            ],
            "hypothesis_draft": [],
            "candidate_rationales": {},
            "evidence_gaps": []
        }''')
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        # 应该失败，因为 fake:id:999 不存在于 context
        with self.assertRaises(ValueError) as ctx:
            synthesizer.synthesize(theme, context, audit)
        
        self.assertIn("non-existent source_id", str(ctx.exception))
    
    def test_synthesizer_malformed_json_fails(self):
        """Synthesizer fails explicitly on invalid JSON."""
        mock_llm = MockLLMClient("This is not JSON")
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        with self.assertRaises(ValueError) as ctx:
            synthesizer.synthesize(theme, context, audit)
        
        self.assertIn("Invalid JSON", str(ctx.exception))
    
    def test_llm_cannot_override_company_name(self):
        """LLM output cannot override company_name from verification."""
        mock_llm = MockLLMClient('''{
            "demand_driver": "测试",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {
                "300750.SZ": {
                    "rationale": "假公司名",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            "evidence_gaps": []
        }''')
        
        synthesizer = ResearchSynthesizer(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        context = self._create_test_context()
        audit = SerenityAgentAudit()
        
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        # 验证 context 中的 company_name 没有被 LLM 改变
        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(candidate.company_name, "宁德时代")  # 原始名称保持不变


if __name__ == "__main__":
    unittest.main()
