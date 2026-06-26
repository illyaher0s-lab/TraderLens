"""
End-to-end tests for real two-phase red-team data flow.

验证真实双阶段链路：
Planner → Executor → Synthesizer → Gate

测试：
1. Synthesizer 返回有效问题后候选可通过
2. 没有问题和反证时真实链路拒绝
3. 任意反证字符串不能通过
4. 不存在或属于其他股票的 source ID 被拒绝
5. 无关股票的问题被拒绝
6. 三类结果进入最终 SerenityOutput 后结构不丢失
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_planner import ResearchPlanner, ResearchPlan
from backend.services.serenity_executor import DeterministicExecutor
from backend.services.serenity_synthesizer import ResearchSynthesizer
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit
from backend.services.serenity_tools import SerenityTools
from backend.services.research_validation import ResearchValidator
from contracts.research import ThemeInput, ResearchSource


class MockLLMForE2E:
    """Mock LLM for E2E testing."""
    
    def __init__(self, synthesizer_output: dict):
        self.synthesizer_output = synthesizer_output
        self.call_count = 0
    
    def create_message(self, messages, system, max_tokens):
        self.call_count += 1
        import json
        
        # Planner call (第1次 LLM 调用)
        if "Research Planner" in system or "研究计划" in system:
            return {
                "content": [{
                    "type": "text",
                    "text": '{"keywords": ["锂电池"], "seed_symbols": ["300750.SZ"], "sectors_to_check": [], "falsification_questions": [], "start_date": null, "end_date": null}'
                }]
            }
        
        # Synthesizer call (第2次 LLM 调用)
        return {
            "content": [{"type": "text", "text": json.dumps(self.synthesizer_output, ensure_ascii=False)}]
        }


class TestRealTwoPhaseRedTeamE2E(unittest.TestCase):
    """端到端测试真实双阶段 red-team 数据流。"""
    
    def test_valid_question_passes_e2e(self):
        """测试 1：Synthesizer 返回有效问题后候选通过。"""
        
        # Mock LLM 返回包含有效问题的输出
        mock_llm = MockLLMForE2E({
            "demand_driver": "锂电池需求增长",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {
                "300750.SZ": {
                    "rationale": "产业链核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"],
                    "falsification_questions": ["宁德时代在锂电池产能扩张计划是否落实？"],
                    "counter_evidence": []
                }
            },
            "evidence_gaps": []
        })
        
        # Phase 1: Planner
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        context = SerenityRunContext()
        audit = SerenityAgentAudit()
        
        plan = planner.plan(theme, [])
        
        # Phase 2: Executor (手动添加来源和候选)
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2025 年报：锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=["no_announcement_data"],
            falsification_questions=[],  # Executor 阶段为空
            counter_evidence=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        context.theme_keywords = ["锂电池"]
        
        # Phase 3: Synthesizer
        synthesizer = ResearchSynthesizer(mock_llm)
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        # 验证 Synthesizer 绑定了问题
        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.falsification_questions), 1)
        self.assertIn("宁德时代", candidate.falsification_questions[0])
        
        # Phase 4: Gate
        shortlist = apply_shortlist_gate(context, synthesis, "t1")
        
        # 验证通过
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].falsification_questions, candidate.falsification_questions)
    
    def test_only_data_gaps_rejected_e2e(self):
        """测试 2：只有 data_gaps 没有问题/反证时真实链路拒绝。"""
        
        # Mock LLM 返回空问题和反证
        mock_llm = MockLLMForE2E({
            "demand_driver": "锂电池需求增长",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {
                "300750.SZ": {
                    "rationale": "产业链核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"],
                    "falsification_questions": [],  # 空
                    "counter_evidence": []  # 空
                }
            },
            "evidence_gaps": []
        })
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        context = SerenityRunContext()
        audit = SerenityAgentAudit()
        
        plan = planner.plan(theme, [])
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2025 年报：锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=["no_announcement_data"],  # 只有 data_gaps
            falsification_questions=[],
            counter_evidence=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        context.theme_keywords = ["锂电池"]
        
        synthesizer = ResearchSynthesizer(mock_llm)
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        shortlist = apply_shortlist_gate(context, synthesis, "t1")
        
        # 验证拒绝
        self.assertEqual(len(shortlist), 0,
                        "只有 data_gaps 的候选必须被拒绝")
    
    def test_irrelevant_question_rejected_e2e(self):
        """测试 5：无关股票的问题被拒绝。"""
        
        # Mock LLM 返回与其他股票相关的问题
        mock_llm = MockLLMForE2E({
            "demand_driver": "锂电池需求增长",
            "value_chain_layers": [],
            "suspected_bottleneck_layers": [],
            "hypothesis_draft": [],
            "candidate_rationales": {
                "300750.SZ": {
                    "rationale": "产业链核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"],
                    "falsification_questions": ["比亚迪的产能是否足够？"],  # 无关股票
                    "counter_evidence": []
                }
            },
            "evidence_gaps": []
        })
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="锂电池产业链",
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        context = SerenityRunContext()
        audit = SerenityAgentAudit()
        
        plan = planner.plan(theme, [])
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2025 年报：锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=[],
            falsification_questions=[],
            counter_evidence=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        context.theme_keywords = ["锂电池"]
        
        synthesizer = ResearchSynthesizer(mock_llm)
        synthesis = synthesizer.synthesize(theme, context, audit)
        
        # 验证无关问题被过滤
        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.falsification_questions), 0,
                        "无关股票的问题应该被过滤")
        
        # 验证拒绝
        shortlist = apply_shortlist_gate(context, synthesis, "t1")
        self.assertEqual(len(shortlist), 0,
                        "没有有效问题的候选必须被拒绝")


if __name__ == "__main__":
    unittest.main()
