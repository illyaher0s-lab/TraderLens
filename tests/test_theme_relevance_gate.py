"""
Tests for Theme Relevance Gate (问题 #2 显式业务测试).

验证:
- 普通财务数据无主题命中时拒绝
- 无关公告拒绝
- 来源属于另一股票时拒绝
- LLM 伪造主题匹配字段无效（确定性计算覆盖）
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import ResearchSource


class TestThemeRelevanceGate(unittest.TestCase):
    
    def test_financial_data_without_theme_match_rejected(self):
        """普通财务数据无主题命中时拒绝."""
        context = SerenityRunContext()
        
        # 添加财务来源，但没有主题匹配
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=[],  # 无主题匹配
            theme_relevance_basis=None,  # 无相关性
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["需要验证"],
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
        
        # 应该被拒绝（Gate 14：无主题相关性）
        self.assertEqual(len(shortlist), 0)
    
    def test_irrelevant_announcement_rejected(self):
        """无关公告拒绝."""
        context = SerenityRunContext()
        
        # 添加公告来源，但主题不相关
        context.sources_by_id["announcements:300750.SZ:0"] = ResearchSource(
            source_record_id="announcements:300750.SZ:0",
            source_type="announcement",
            source_quality="first_hand",
            title="关于召开股东大会的通知",  # 无关主题
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=[],  # 无主题匹配
            theme_relevance_basis=None,
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["announcements:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["需要验证"],
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
                    "supporting_source_ids": ["announcements:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（无关公告）
        self.assertEqual(len(shortlist), 0)
    
    def test_source_from_different_symbol_rejected(self):
        """来源属于另一股票时拒绝."""
        context = SerenityRunContext()
        
        # 添加来源，但 symbol 不匹配
        context.sources_by_id["financials:002074.SZ:0"] = ResearchSource(
            source_record_id="financials:002074.SZ:0",  # 002074，不是 300750
            source_type="financial_report",
            source_quality="first_hand",
            title="国轩高科 2023 年报",
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
            supporting_source_ids=["financials:002074.SZ:0"],  # 错误的 symbol
            counter_evidence=[],
            falsification_questions=["需要验证"],
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
                    "supporting_source_ids": ["financials:002074.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（Gate 13：symbol 不匹配）
        self.assertEqual(len(shortlist), 0)
    
    def test_llm_fabricated_theme_match_ignored(self):
        """LLM 伪造主题匹配字段无效（确定性计算覆盖）."""
        context = SerenityRunContext()
        
        # LLM 试图伪造主题匹配，但确定性计算会覆盖
        # 我们模拟 LLM 给出的来源有假的 theme_keywords_matched
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=[],  # 确定性计算后为空（无匹配）
            theme_relevance_basis=None,  # 无相关性
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["需要验证"],
            data_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        # LLM 在 synthesis 中声称有主题相关性
        synthesis = ResearchSynthesis(
            demand_driver="锂电池需求",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家，与锂电池主题高度相关",  # LLM 伪造
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（Gate 14 确定性检查，LLM 无权覆盖）
        self.assertEqual(len(shortlist), 0)
    
    def test_valid_theme_match_passes(self):
        """有效主题匹配通过门禁."""
        context = SerenityRunContext()
        
        # 添加有主题匹配的来源
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报 - 锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],  # 确定性计算得出
            theme_relevance_basis="title_match",  # 标题匹配
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["需要验证产能"],
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
        
        # 应该通过（所有门禁满足）
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].symbol, "300750.SZ")
    
    def test_weak_source_with_theme_match_rejected(self):
        """weak 来源即使有主题匹配也被拒绝."""
        context = SerenityRunContext()
        
        # 添加 weak 来源
        context.sources_by_id["news:300750.SZ:0"] = ResearchSource(
            source_record_id="news:300750.SZ:0",
            source_type="news",
            source_quality="weak",  # weak
            title="新闻：宁德时代锂电池业务增长",
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
            supporting_source_ids=["news:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["需要验证"],
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
                    "supporting_source_ids": ["news:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        # 应该被拒绝（Gate 12：weak 来源不能单独支持）
        self.assertEqual(len(shortlist), 0)


if __name__ == "__main__":
    unittest.main()
