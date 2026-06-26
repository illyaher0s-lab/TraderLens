"""
Tests for Serenity Shortlist Gate (确定性门禁).

验证:
- 无来源候选被拒绝
- 全 weak 来源候选被拒绝
- 缺少 red-team 候选被拒绝
- low confidence 候选被拒绝
- 有效候选通过
- 无有效候选时返回空列表
- verification_id 保存到 candidate_stock
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import ResearchSource


class TestSerenityShortlistGate(unittest.TestCase):
    
    def test_no_sources_rejected_from_shortlist(self):
        """Candidates with no supporting sources are rejected."""
        context = SerenityRunContext()
        
        # 候选没有 supporting_source_ids
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=[],  # 空
            counter_evidence=[],
            falsification_questions=["test_question"],  # 有问题才能通过 gate 8
            data_gaps=[],
            unresolved_gaps=[],
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
        
        self.assertEqual(len(shortlist), 0)
    
    def test_all_weak_sources_rejected_from_shortlist(self):
        """Candidates with all weak sources are rejected."""
        context = SerenityRunContext()
        
        # 添加 weak source
        context.sources_by_id["news:300750.SZ:0"] = ResearchSource(
            source_record_id="news:300750.SZ:0",
            source_type="news",
            source_quality="weak",
            title="新闻",
            retrieved_at=datetime.now(),
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
            falsification_questions=["no_strong_data"],
            data_gaps=[],
            unresolved_gaps=[],
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
        
        self.assertEqual(len(shortlist), 0)
    
    def test_missing_red_team_rejected_from_shortlist(self):
        """Candidates without red_team check are rejected."""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["测试主题"],
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
            counter_evidence=[],
            falsification_questions=["gap"],
            data_gaps=[],
            unresolved_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        # 没有 red_team
        
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
        
        self.assertEqual(len(shortlist), 0)
    
    def test_low_confidence_rejected_from_shortlist(self):
        """Candidates with low confidence are rejected."""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["测试主题"],
            theme_relevance_basis="title_match",
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="low",  # low confidence
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["gap"],
            data_gaps=[],
            unresolved_gaps=[],
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
        
        self.assertEqual(len(shortlist), 0)
    
    def test_valid_candidate_passes_shortlist(self):
        """Valid candidate passes all gates."""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["测试主题"],
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
            counter_evidence=[],
            falsification_questions=["需要验证产能"],
            data_gaps=[],
            unresolved_gaps=[],
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
                    "rationale": "产业链核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].symbol, "300750.SZ")
        self.assertEqual(shortlist[0].company_name, "宁德时代")
        self.assertEqual(shortlist[0].verification_id, "verify_abc123")
        self.assertEqual(shortlist[0].match_confidence, "high")
        self.assertIn("产业链核心玩家", shortlist[0].match_reason)
    
    def test_empty_shortlist_when_no_valid_candidates(self):
        """Empty shortlist when no candidates pass gates."""
        context = SerenityRunContext()
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={},  # 没有候选
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0)
    
    def test_verification_id_saved_in_candidate_stock(self):
        """verification_id is saved in CandidateStock."""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2023 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["测试主题"],
            theme_relevance_basis="title_match",
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_xyz789",
            exchange="SZSE",
            listing_status="listed",
            confidence="medium",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["gap"],
            data_gaps=[],
            unresolved_gaps=[],
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
                    "rationale": "核心",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist[0].verification_id, "verify_xyz789")


if __name__ == "__main__":
    unittest.main()
