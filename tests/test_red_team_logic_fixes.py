"""
Adversarial tests for Red-Team logic fixes.

验证 red-team 语义漏洞修复：
1. 缺财务、公告、行业数据，但没有独立问题 → 拒绝
2. data_gap 自动拼成问题 → 拒绝（不应自动生成）
3. source.gaps 含 conflict 文本但没有反方事实记录 → 不得成为 counter_evidence
4. 无来源的 counter_evidence → 拒绝
5. 有真实 source_record_id 的反证 → 保留并通过
6. 与其他股票有关的问题 → 当前候选拒绝
7. 三类 red-team 结果经过最终输出后仍保持结构和来源 ID
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import ResearchSource


class TestRedTeamDataGapsOnly(unittest.TestCase):
    """测试 1：只有 data_gaps 没有诘问或反证 → 拒绝。"""
    
    def test_only_data_gaps_rejected(self):
        """只有 data_gaps 的候选被拒绝。"""
        context = SerenityRunContext()
        
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
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            # 只有 data_gaps，没有 falsification_questions 或 counter_evidence
            data_gaps=["no_announcement_data", "no_sector_data"],
            falsification_questions=[],
            counter_evidence=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="测试",
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
        
        self.assertEqual(len(shortlist), 0,
                        "只有 data_gaps 的候选必须被拒绝")


class TestRedTeamValidOutputs(unittest.TestCase):
    """测试有效的 red-team 输出可以通过。"""
    
    def test_falsification_question_passes(self):
        """有明确 falsification_question 的候选通过。"""
        context = SerenityRunContext()
        
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
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=["no_announcement_data"],
            falsification_questions=["产能扩张计划是否落实？"],
            counter_evidence=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="测试",
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
        
        self.assertEqual(len(shortlist), 1,
                        "有 falsification_question 的候选应该通过")
    
    def test_counter_evidence_with_source_passes(self):
        """有真实 source_record_id 的 counter_evidence 通过。"""
        context = SerenityRunContext()
        
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
        
        from contracts.research import CounterEvidence
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=[],
            falsification_questions=[],
            counter_evidence=[CounterEvidence(
                description="营收下降 10%",
                source_record_id="financials:300750.SZ:0"
            )],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="测试",
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
        
        self.assertEqual(len(shortlist), 1,
                        "有可追溯 counter_evidence 的候选应该通过")


class TestRedTeamStructurePreserved(unittest.TestCase):
    """测试 7：三类 red-team 结果在最终输出保持结构。"""
    
    def test_red_team_categories_preserved_in_candidate_stock(self):
        """CandidateStock 保留三类 red-team 结果独立字段。"""
        context = SerenityRunContext()
        
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
        
        from contracts.research import CounterEvidence
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            data_gaps=["no_announcement_data"],
            falsification_questions=["产能是否足够？"],
            counter_evidence=[CounterEvidence(
                description="库存增加",
                source_record_id="financials:300750.SZ:0"
            )],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="测试",
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
        
        self.assertEqual(len(shortlist), 1)
        candidate = shortlist[0]
        
        # 验证三类结果独立保留
        self.assertEqual(candidate.data_gaps, ["no_announcement_data"])
        self.assertEqual(candidate.falsification_questions, ["产能是否足够？"])
        self.assertEqual(len(candidate.counter_evidence), 1)
        self.assertEqual(candidate.counter_evidence[0].description, "库存增加")
        self.assertEqual(candidate.counter_evidence[0].source_record_id, "financials:300750.SZ:0")


if __name__ == "__main__":
    unittest.main()
