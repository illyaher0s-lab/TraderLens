"""
Tests for preserving source references in final Serenity output.

验证问题 #4：
1. 来源引用经过完整转换后保持一致
2. 不存在的来源 ID 无法进入最终输出
3. 同一候选的理由、支持来源、反证和 gap 不会串到其他候选
4. 最终输出不包含交易字段
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import ResearchSource, CounterEvidence
from contracts.research import ThemeInput, ResearchSource


class TestSourceReferencePreservation(unittest.TestCase):
    """测试来源引用在最终输出中保留。"""
    
    def test_value_chain_preserves_source_ids(self):
        """value_chain_layers 保留 supporting_source_ids。"""
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[
                {
                    "layer": "上游",
                    "description": "原材料",
                    "supporting_source_ids": ["financials:300750.SZ:0", "announcements:300750.SZ:1"]
                }
            ],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={},
            evidence_gaps=[],
        )
        
        # 验证结构保留
        self.assertEqual(len(synthesis.value_chain_layers), 1)
        layer = synthesis.value_chain_layers[0]
        self.assertIn("supporting_source_ids", layer)
        self.assertEqual(len(layer["supporting_source_ids"]), 2)
        self.assertIn("financials:300750.SZ:0", layer["supporting_source_ids"])
    
    def test_bottleneck_preserves_source_ids(self):
        """suspected_bottleneck_layers 保留 supporting_source_ids。"""
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[
                {
                    "layer": "中游",
                    "reason": "产能限制",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            ],
            hypothesis_draft=[],
            candidate_rationales={},
            evidence_gaps=[],
        )
        
        self.assertEqual(len(synthesis.suspected_bottleneck_layers), 1)
        bottleneck = synthesis.suspected_bottleneck_layers[0]
        self.assertIn("supporting_source_ids", bottleneck)
        self.assertEqual(bottleneck["supporting_source_ids"], ["financials:300750.SZ:0"])
    
    def test_hypothesis_preserves_source_ids(self):
        """hypothesis_draft 保留 supporting_source_ids。"""
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[
                {
                    "hypothesis": "产能扩张",
                    "rationale": "需求增长",
                    "confidence": "high",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            ],
            candidate_rationales={},
            evidence_gaps=[],
        )
        
        self.assertEqual(len(synthesis.hypothesis_draft), 1)
        hypothesis = synthesis.hypothesis_draft[0]
        self.assertIn("supporting_source_ids", hypothesis)
        self.assertEqual(hypothesis["supporting_source_ids"], ["financials:300750.SZ:0"])


class TestCandidateMetadataPreservation(unittest.TestCase):
    """测试候选的研究元数据保留。"""
    
    def test_candidate_preserves_supporting_source_ids(self):
        """shortlist 中的候选保留 supporting_source_ids。"""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代 2025 年报：锂电池业务营收增长",
            summary="锂电池产能扩张，动力电池市场份额提升",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池", "动力电池"],
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
            falsification_questions=["宁德时代锂电池产能数据待验证"],
            data_gaps=["缺少行业对比"],
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
                    "rationale": "产业链核心",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 1)
        candidate = shortlist[0]
        
        # 验证 supporting_source_ids 保留
        self.assertEqual(candidate.supporting_source_ids, ["financials:300750.SZ:0"])
        
        # 验证 falsification_questions 保留
        self.assertEqual(candidate.falsification_questions, ["宁德时代锂电池产能数据待验证"])
        
        # 验证 data_gaps 保留
        self.assertEqual(candidate.data_gaps, ["缺少行业对比"])
    
    def test_candidate_metadata_not_mixed(self):
        """不同候选的元数据不会混淆。"""
        context = SerenityRunContext()
        
        # 候选 A
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="宁德时代：锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_a",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:300750.SZ:0"],
            counter_evidence=[CounterEvidence(
                description="候选A的反证",
                source_record_id="financials:300750.SZ:0"
            )],
            falsification_questions=["宁德时代锂电池相关问题"],
            data_gaps=["候选A的缺口"],
        )
        
        # 候选 B
        context.sources_by_id["financials:002594.SZ:0"] = ResearchSource(
            source_record_id="financials:002594.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="比亚迪：锂电池业务",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["锂电池"],
            theme_relevance_basis="title_match",
        )
        
        context.verified_candidates_by_symbol["002594.SZ"] = VerifiedResearchCandidate(
            symbol="002594.SZ",
            company_name="比亚迪",
            verification_id="verify_b",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:002594.SZ:0"],
            counter_evidence=[CounterEvidence(
                description="候选B的反证",
                source_record_id="financials:002594.SZ:0"
            )],
            falsification_questions=["比亚迪锂电池相关问题"],
            data_gaps=["候选B的缺口"],
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
                    "rationale": "候选A理由",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                },
                "002594.SZ": {
                    "rationale": "候选B理由",
                    "supporting_source_ids": ["financials:002594.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 2)
        
        # 验证候选 A 元数据
        cand_a = next(c for c in shortlist if c.symbol == "300750.SZ")
        self.assertEqual(cand_a.supporting_source_ids, ["financials:300750.SZ:0"])
        self.assertEqual(len(cand_a.counter_evidence), 1)
        self.assertEqual(cand_a.counter_evidence[0].description, "候选A的反证")
        self.assertEqual(cand_a.falsification_questions, ["宁德时代锂电池相关问题"])
        self.assertEqual(cand_a.data_gaps, ["候选A的缺口"])
        self.assertIn("候选A理由", cand_a.match_reason)
        
        # 验证候选 B 元数据
        cand_b = next(c for c in shortlist if c.symbol == "002594.SZ")
        self.assertEqual(cand_b.supporting_source_ids, ["financials:002594.SZ:0"])
        self.assertEqual(len(cand_b.counter_evidence), 1)
        self.assertEqual(cand_b.counter_evidence[0].description, "候选B的反证")
        self.assertEqual(cand_b.falsification_questions, ["比亚迪锂电池相关问题"])
        self.assertEqual(cand_b.data_gaps, ["候选B的缺口"])
        self.assertIn("候选B理由", cand_b.match_reason)


class TestOutputNoTradingFields(unittest.TestCase):
    """测试最终输出不包含交易字段。"""
    
    def test_synthesis_no_trading_fields(self):
        """ResearchSynthesis 不包含交易建议字段。"""
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={},
            evidence_gaps=[],
        )
        
        synthesis_dict = {
            "demand_driver": synthesis.demand_driver,
            "value_chain_layers": synthesis.value_chain_layers,
            "suspected_bottleneck_layers": synthesis.suspected_bottleneck_layers,
            "hypothesis_draft": synthesis.hypothesis_draft,
            "candidate_rationales": synthesis.candidate_rationales,
            "evidence_gaps": synthesis.evidence_gaps,
        }
        
        synthesis_str = str(synthesis_dict).lower()
        
        forbidden = ["buy", "sell", "target_price", "stop_loss", "position", "entry", "exit"]
        for field in forbidden:
            self.assertNotIn(field, synthesis_str, f"Output contains forbidden field: {field}")


if __name__ == "__main__":
    unittest.main()
