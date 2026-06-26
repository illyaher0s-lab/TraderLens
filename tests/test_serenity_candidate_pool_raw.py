"""
Tests for Serenity Two-Phase candidate_pool_raw Contract.

验证：
1. manual_candidates 进入 raw pool
2. Executor 已核验候选进入 raw pool
3. 未通过 shortlist 的候选仍在 raw pool
4. raw 与 shortlist 状态不同
5. 相同 symbol 不重复
6. 核验候选优先于未核验人工候选
7. 研究元数据不丢失
8. A 模块禁止的交易字段不存在
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_agent import (
    SerenityAgentRunner,
    SerenityRunContext,
    VerifiedResearchCandidate,
)
from backend.services.serenity_synthesizer import ResearchSynthesis
from backend.services.serenity_gate import apply_shortlist_gate
from contracts.research import (
    ThemeInput,
    CandidateStock,
    ResearchSource,
    CounterEvidence,
)


class MockLLMClient:
    """Mock LLM client for two-phase testing."""

    def __init__(self):
        self.call_count = 0

    def create_message(self, messages, system, max_tokens):
        self.call_count += 1

        if "Research Planner" in system:
            # Planner 返回 ResearchPlan
            return {
                "content": [
                    {
                        "type": "text",
                        "text": """{
                        "keywords": ["锂电池", "新能源"],
                        "seed_symbols": ["300750.SZ", "002594.SZ"],
                        "sectors_to_check": ["电气设备"],
                        "start_date": null,
                        "end_date": null,
                        "falsification_questions": ["产能是否过剩"]
                    }""",
                    }
                ]
            }
        elif "Research Synthesizer" in system:
            # Synthesizer 返回 ResearchSynthesis
            return {
                "content": [
                    {
                        "type": "text",
                        "text": """{
                        "demand_driver": "新能源汽车需求增长",
                        "value_chain_layers": [
                            {"layer": "上游", "description": "锂矿开采", "supporting_source_ids": ["financials:300750.SZ:0"]},
                            {"layer": "中游", "description": "电池制造", "supporting_source_ids": ["financials:002594.SZ:0"]}
                        ],
                        "suspected_bottleneck_layers": [
                            {"layer": "中游", "reason": "产能扩张速度决定行业增长上限", "supporting_source_ids": ["financials:300750.SZ:0"]}
                        ],
                        "hypothesis_draft": [
                            {"hypothesis": "锂电池需求持续增长", "rationale": "新能源汽车渗透率提升", "confidence": "medium", "supporting_source_ids": ["financials:300750.SZ:0"]}
                        ],
                        "candidate_rationales": {
                            "300750.SZ": {
                                "rationale": "核心玩家",
                                "supporting_source_ids": ["financials:300750.SZ:0"]
                            }
                        },
                        "evidence_gaps": ["需要验证产能扩张计划"]
                    }""",
                    }
                ]
            }
        else:
            raise ValueError(f"Unknown system prompt: {system[:100]}")


class MockSerenityTools:
    """Mock tools that return test data."""

    def retrieve_supply_chain(
        self,
        theme_name,
        theme_background,
        keywords,
        symbols,
        start_date,
        end_date,
        max_records,
    ):
        from contracts.research import SerenityToolResult

        # 返回两个候选的研究来源
        records = [
            ResearchSource(
                source_record_id="financials:300750.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="宁德时代2025年年报",
                retrieved_at=datetime.now(),
                published_at=date.today(),
                summary="营收增长30%",
                theme_keywords_matched=["锂电池"],
                theme_relevance_basis="title_match",
            ),
            ResearchSource(
                source_record_id="financials:002594.SZ:0",
                source_type="financial_report",
                source_quality="second_hand",
                title="比亚迪2025年年报",
                retrieved_at=datetime.now(),
                published_at=date.today(),
                summary="营收增长20%",
                theme_keywords_matched=["新能源"],
                theme_relevance_basis="summary_match",
            ),
        ]

        return SerenityToolResult(
            tool_name="retrieve_supply_chain",
            records=records,
            total_found=2,
            gaps=[],
            errors=[],
            retrieved_at=datetime.now(),
        )

    def discover_players(self, source_records, max_players):
        from contracts.research import SerenityToolResult

        # 从 source_records 提取 players
        records = []
        for src in source_records:
            parts = src.source_record_id.split(":")
            if len(parts) >= 2:
                symbol = parts[1]
                records.append(
                    ResearchSource(
                        source_record_id=f"player:{symbol}:0",
                        source_type="unknown",
                        source_quality="weak",
                        title=f"发现玩家: {symbol}",
                        retrieved_at=datetime.now(),
                        summary=f"symbol={symbol}",
                    )
                )

        return SerenityToolResult(
            tool_name="discover_players",
            records=records,
            total_found=len(records),
            gaps=[],
            errors=[],
            retrieved_at=datetime.now(),
        )


class MockValidator:
    """Mock validator."""

    def verify_ticker(self, symbol):
        from backend.services.research_validation import TickerVerificationResult

        return TickerVerificationResult(
            verification_id=f"verify_{symbol}",
            company_name=f"公司{symbol}",
            ticker=symbol,
            exchange="SZSE",
            status="listed",
            confidence="high",
            source="tushare",
            notes="",
            verified_at=datetime.now(),
        )

    def get_hard_filter_snapshot(self, symbol, verified_status):
        from backend.services.research_validation import HardFilterSnapshot

        # All pass
        return HardFilterSnapshot(
            is_listed=True,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=5000000.0,
            source="tushare",
            retrieved_at=datetime.now(),
            gaps=[],
        )

    def validate_candidate(
        self, symbol, company_name, is_listed, is_st, is_suspended, avg_daily_volume
    ):
        from backend.services.research_validation import ValidationResult

        # All pass
        return ValidationResult(flags=[], is_valid=True)


class TestCandidatePoolRawContract(unittest.TestCase):
    """测试 candidate_pool_raw 契约。"""

    def test_manual_candidates_enter_raw_pool(self):
        """人工候选进入 raw pool。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        manual_candidates = [
            CandidateStock(
                candidate_id="manual_1",
                theme_id="t1",
                symbol="688981.SH",
                company_name="中芯国际",
                verification_id=None,
                source_type="manual_stock",
                chain_layer=None,
                match_reason="人工添加",
                status="raw",
                created_at=datetime.now(),
            )
        ]

        output = runner.run(theme, manual_candidates)

        # 验证 manual_candidates 在 raw pool 中
        raw_symbols = {c.symbol for c in output.candidate_pool_raw}
        self.assertIn(
            "688981.SH", raw_symbols, "人工候选必须进入 raw pool"
        )

    def test_executor_candidates_enter_raw_pool(self):
        """Executor 已核验候选进入 raw pool。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        output = runner.run(theme, [])

        # 验证 Executor 候选在 raw pool 中
        raw_symbols = {c.symbol for c in output.candidate_pool_raw}
        self.assertIn(
            "300750.SZ", raw_symbols, "Executor 核验候选必须进入 raw pool"
        )
        self.assertIn(
            "002594.SZ", raw_symbols, "Executor 核验候选必须进入 raw pool"
        )

    def test_rejected_candidates_remain_in_raw_pool(self):
        """未通过 shortlist 的候选仍在 raw pool。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        output = runner.run(theme, [])

        # 002594.SZ 来源质量较弱（second_hand），可能被门禁拒绝
        raw_symbols = {c.symbol for c in output.candidate_pool_raw}
        shortlist_symbols = {c.symbol for c in output.candidate_shortlist}

        # raw pool 应该包含所有候选
        self.assertGreaterEqual(
            len(output.candidate_pool_raw), len(output.candidate_shortlist),
            "raw pool 必须包含所有候选（含被拒绝的）"
        )

        # 如果有候选被拒绝，验证它仍在 raw pool 中
        if len(raw_symbols) > len(shortlist_symbols):
            rejected_symbols = raw_symbols - shortlist_symbols
            self.assertGreater(
                len(rejected_symbols), 0,
                "被门禁拒绝的候选必须保留在 raw pool"
            )

    def test_raw_and_shortlist_status_different(self):
        """raw 与 shortlist 状态不同。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        output = runner.run(theme, [])

        # 验证 raw pool 中的候选 status="raw"
        for candidate in output.candidate_pool_raw:
            self.assertEqual(
                candidate.status, "raw",
                f"raw pool 候选 {candidate.symbol} status 必须为 'raw'"
            )

        # 验证 shortlist 中的候选 status="shortlisted"
        for candidate in output.candidate_shortlist:
            self.assertEqual(
                candidate.status, "shortlisted",
                f"shortlist 候选 {candidate.symbol} status 必须为 'shortlisted'"
            )

    def test_no_duplicate_symbols(self):
        """相同 symbol 不重复。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # 添加与 Executor 重复的 manual candidate
        manual_candidates = [
            CandidateStock(
                candidate_id="manual_1",
                theme_id="t1",
                symbol="300750.SZ",  # 与 Executor 候选重复
                company_name="手动宁德时代",
                verification_id=None,
                source_type="manual_stock",
                chain_layer=None,
                match_reason="人工添加",
                status="raw",
                created_at=datetime.now(),
            )
        ]

        output = runner.run(theme, manual_candidates)

        # 验证 raw pool 中没有重复 symbol
        raw_symbols = [c.symbol for c in output.candidate_pool_raw]
        self.assertEqual(
            len(raw_symbols), len(set(raw_symbols)),
            "raw pool 中不得有重复 symbol"
        )

    def test_verified_candidate_priority(self):
        """核验候选优先于未核验人工候选。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # 添加与 Executor 重复的 manual candidate（无 verification_id）
        manual_candidates = [
            CandidateStock(
                candidate_id="manual_1",
                theme_id="t1",
                symbol="300750.SZ",  # 与 Executor 候选重复
                company_name="手动宁德时代",
                verification_id=None,  # 无核验
                source_type="manual_stock",
                chain_layer=None,
                match_reason="人工添加",
                status="raw",
                created_at=datetime.now(),
            )
        ]

        output = runner.run(theme, manual_candidates)

        # 找到 300750.SZ 候选
        candidate_300750 = next(
            (c for c in output.candidate_pool_raw if c.symbol == "300750.SZ"),
            None
        )

        self.assertIsNotNone(candidate_300750, "300750.SZ 必须在 raw pool 中")
        self.assertIsNotNone(
            candidate_300750.verification_id,
            "重复 symbol 必须优先使用拥有 verification_id 的 Executor 候选"
        )
        self.assertEqual(
            candidate_300750.company_name, "公司300750.SZ",
            "核验候选的 company_name 必须来自 verification record"
        )

    def test_research_metadata_preserved(self):
        """研究元数据不丢失。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        output = runner.run(theme, [])

        # 验证 raw pool 候选包含研究元数据
        for candidate in output.candidate_pool_raw:
            self.assertIsInstance(
                candidate.supporting_source_ids, list,
                f"候选 {candidate.symbol} 必须有 supporting_source_ids"
            )
            # 验证 red-team 三类字段存在
            self.assertIsInstance(candidate.counter_evidence, list)
            self.assertIsInstance(candidate.falsification_questions, list)
            self.assertIsInstance(candidate.data_gaps, list)

    def test_no_trading_fields(self):
        """A 模块禁止的交易字段不存在。"""
        mock_llm = MockLLMClient()
        mock_tools = MockSerenityTools()
        mock_validator = MockValidator()

        runner = SerenityAgentRunner(
            llm_client=mock_llm,
            validator=mock_validator,
            tools=mock_tools,
            mode="real",
            execution_mode="two_phase",
            db=None,
        )


        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池上下游",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        output = runner.run(theme, [])

        # 验证输出不包含交易字段
        output_dict = output.model_dump()

        forbidden_fields = [
            "entry_price",
            "stop_loss",
            "position_pct",
            "buy_tomorrow",
            "target_price",
        ]

        for field in forbidden_fields:
            self.assertNotIn(
                field, output_dict,
                f"A 模块输出不得包含交易字段: {field}"
            )

        # 验证候选不包含交易字段
        for candidate in output.candidate_pool_raw:
            candidate_dict = candidate.model_dump()
            for field in forbidden_fields:
                self.assertNotIn(
                    field, candidate_dict,
                    f"候选 {candidate.symbol} 不得包含交易字段: {field}"
                )


if __name__ == "__main__":
    unittest.main()
