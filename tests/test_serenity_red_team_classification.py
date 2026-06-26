"""
Tests for Serenity Red-team Classification (问题 #5).

验证 red-team 正确区分：
- counter_evidence: 真实来源支持的反证
- falsification_questions: 待验证的问题
- data_gaps: 数据缺口

规则：
1. 数据缺失只能成为 data_gap，不能冒充已发现的反证
2. counter_evidence 必须引用真实 source_record_id
3. falsification_questions 可以没有来源，但必须明确标记 unresolved
4. 候选不能仅因为存在 data_gap 就满足 red-team 门禁
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_executor import DeterministicExecutor
from backend.services.serenity_planner import ResearchPlan
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_synthesizer import ResearchSynthesis
from backend.services.serenity_tools import SerenityTools
from backend.services.research_validation import ResearchValidator
from contracts.research import ResearchSource


class TestRedTeamClassification(unittest.TestCase):
    
    def test_data_gaps_only_do_not_satisfy_red_team_gate(self):
        """只有 data_gaps 的候选不能通过 red-team 门禁."""
        context = SerenityRunContext()
        
        # 添加一个有效来源
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        # 创建候选，只有 data_gaps
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],  # 空
            falsification_questions=[],  # 空
            data_gaps=["no_announcement_data", "no_sector_data"],  # 只有 gaps
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="锂电池需求",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（只有 data_gaps 不满足门禁）
        self.assertEqual(len(shortlist), 0)
    
    def test_counter_evidence_with_source_passes_gate(self):
        """有可追溯反证的候选通过门禁."""
        context = SerenityRunContext()
        
        # 添加来源，包含 gap 表明矛盾
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            gaps=["revenue_data_contradicts_announcement"],
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        from contracts.research import CounterEvidence
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[CounterEvidence(
                description="revenue_data_contradicts_announcement",
                source_record_id="financials:300750.SZ:0"
            )],
            falsification_questions=[],
            data_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="锂电池需求",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该通过（有真实反证）
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].counter_evidence[0].source_record_id, "financials:300750.SZ:0")
    
    def test_falsification_questions_pass_gate(self):
        """有待验证问题的候选通过门禁."""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["缺少完整数据，需验证 300750.SZ 是否真实参与主题产业链"],
            data_gaps=["no_announcement_data"],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="锂电池需求",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该通过（有待验证问题）
        self.assertEqual(len(shortlist), 1)
        self.assertIn("缺少完整数据", shortlist[0].falsification_questions[0])
    
    def test_complete_data_without_counter_evidence_rejected(self):
        """完整数据但没有反证时不会因"缺少 finding"产生错误结论."""
        context = SerenityRunContext()
        
        # 添加完整数据
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        context.sources_by_id["announcements:300750.SZ:0"] = ResearchSource(
            source_record_id="announcements:300750.SZ:0",
            source_type="announcement",
            source_quality="first_hand",
            title="宁德时代公告",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        context.sources_by_id["sector:300750.SZ:0"] = ResearchSource(
            source_record_id="sector:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="行业归属",
            retrieved_at=datetime.now(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="industry_match",
        )
        
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0", "announcements:300750.SZ:0", "sector:300750.SZ:0"],
            counter_evidence=[],  # 没有反证
            falsification_questions=[],  # 没有问题
            data_gaps=[],  # 没有缺口
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="锂电池需求",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（没有 red-team 工作）
        self.assertEqual(len(shortlist), 0)
    
    def test_executor_red_team_classification(self):
        """测试 executor 正确分类 red-team 结果."""
        # 创建 validator（不需要 Tushare）
        validator = ResearchValidator()
        tools = SerenityTools(validator=validator)
        
        # 不提供 data_tools，模拟无数据场景
        executor = DeterministicExecutor(
            serenity_tools=tools,
            validator=validator,
            db=None,
        )
        
        plan = ResearchPlan(
            keywords=["锂电池"],
            seed_symbols=["300750.SZ"],
            sectors_to_check=[],
            falsification_questions=[],
            start_date=None,
            end_date=None,
        )
        
        context = SerenityRunContext()
        audit = SerenityAgentAudit()
        audit.errors = []
        
        # 手动添加候选（跳过数据检索）
        from backend.services.serenity_agent import VerifiedResearchCandidate
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
        )
        
        # 添加假来源
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="财务数据",
            retrieved_at=datetime.now(),
        )
        
        context.completed_checks.add("source_audit")
        
        # 执行 red-team
        executor._red_team(context, audit)
        
        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        
        # 验证分类
        self.assertGreater(len(candidate.data_gaps), 0, "应该有 data_gaps")
        # falsification_questions 现在由 LLM 生成，executor 阶段为空
        self.assertEqual(len(candidate.falsification_questions), 0, "executor 阶段 falsification_questions 为空")
        # counter_evidence 需要真实来源的矛盾，这里没有
        self.assertEqual(len(candidate.counter_evidence), 0)
        
        # data_gaps 应该记录缺少的数据
        self.assertIn("no_announcement_data", candidate.data_gaps)
        self.assertIn("no_sector_data", candidate.data_gaps)


if __name__ == "__main__":
    unittest.main()
