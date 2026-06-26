"""
Adversarial tests for Serenity Shortlist Gate.

验证门禁对抗性测试：
1. discovered_player 不能单独让候选通过门禁
2. 候选引用 discovered_player:* 加不存在的来源时必须拒绝
3. supporting_source_ids 全部为 weak 时必须拒绝
4. 来源存在但与候选 symbol 不匹配时必须拒绝
5. 来源属于候选，但不能证明其与当前 theme 相关时仍必须拒绝
6. LLM 伪造、越权或遗漏 source ID 时必须拒绝
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis
from contracts.research import ResearchSource


class TestDiscoveredPlayerCannotPassAlone(unittest.TestCase):
    """测试 1：discovered_player 不能单独让候选通过门禁。"""
    
    def test_discovered_player_alone_rejected(self):
        """只有 discovered_player 来源的候选被拒绝。"""
        context = SerenityRunContext()
        
        # 只有 discovered_player 来源（weak）
        context.sources_by_id["discovered_player:300750.SZ"] = ResearchSource(
            source_record_id="discovered_player:300750.SZ",
            source_type="unknown",
            source_quality="weak",
            title="已验证玩家: 宁德时代",
            retrieved_at=datetime.now(),
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["discovered_player:300750.SZ"],
            counter_evidence=[],
            falsification_questions=["需要真实研究证据"],
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
                    "supporting_source_ids": ["discovered_player:300750.SZ"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "只有身份核验记录的候选必须被拒绝")


class TestMixedSourceValidation(unittest.TestCase):
    """测试 2：候选引用 discovered_player:* 加不存在的来源时必须拒绝。"""
    
    def test_discovered_player_plus_nonexistent_source_rejected(self):
        """discovered_player + 不存在的来源 → 拒绝。"""
        context = SerenityRunContext()
        
        context.sources_by_id["discovered_player:300750.SZ"] = ResearchSource(
            source_record_id="discovered_player:300750.SZ",
            source_type="unknown",
            source_quality="weak",
            title="已验证玩家: 宁德时代",
            retrieved_at=datetime.now(),
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["discovered_player:300750.SZ"],
            counter_evidence=[],
            falsification_questions=["gap"],
            unresolved_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        # rationale 引用了不存在的来源
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["discovered_player:300750.SZ", "fake_source_999"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "引用不存在来源的候选必须被拒绝")


class TestAllWeakSourcesRejection(unittest.TestCase):
    """测试 3：supporting_source_ids 全部为 weak 时必须拒绝。"""
    
    def test_all_weak_sources_in_rationale_rejected(self):
        """rationale 的所有来源都是 weak → 拒绝。"""
        context = SerenityRunContext()
        
        # 两个 weak 来源
        context.sources_by_id["news:300750.SZ:0"] = ResearchSource(
            source_record_id="news:300750.SZ:0",
            source_type="news",
            source_quality="weak",
            title="新闻1",
            retrieved_at=datetime.now(),
        )
        
        context.sources_by_id["social:300750.SZ:0"] = ResearchSource(
            source_record_id="social:300750.SZ:0",
            source_type="social_media",
            source_quality="weak",
            title="社交媒体",
            retrieved_at=datetime.now(),
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["news:300750.SZ:0", "social:300750.SZ:0"],
            counter_evidence=[],
            falsification_questions=["gap"],
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
                    "supporting_source_ids": ["news:300750.SZ:0", "social:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "所有来源都是 weak 的候选必须被拒绝")


class TestSourceSymbolMismatch(unittest.TestCase):
    """测试 4：来源存在但与候选 symbol 不匹配时必须拒绝。"""
    
    def test_source_for_different_symbol_rejected(self):
        """来源属于其他 symbol → 拒绝。"""
        context = SerenityRunContext()
        
        # 来源是另一个 symbol 的
        context.sources_by_id["financials:600519.SH:0"] = ResearchSource(
            source_record_id="financials:600519.SH:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="贵州茅台 2025 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["financials:600519.SH:0"],  # 错误的 symbol
            counter_evidence=[],
            falsification_questions=["gap"],
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
                    "supporting_source_ids": ["financials:600519.SH:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "来源与候选 symbol 不匹配的必须被拒绝")


class TestThemeRelevanceRequired(unittest.TestCase):
    """测试 5：来源属于候选，但不能证明其与当前 theme 相关时仍必须拒绝。"""
    
    def test_source_without_theme_relevance_rejected(self):
        """候选有财报，但无主题相关性证据 → 拒绝（待实现）。"""
        # TODO: 需要定义主题相关性的验证逻辑
        # 当前暂时 skip
        pass


class TestLLMSourceIDFabrication(unittest.TestCase):
    """测试 6：LLM 伪造、越权或遗漏 source ID 时必须拒绝。"""
    
    def test_llm_fabricated_source_id_rejected(self):
        """LLM 伪造不存在的 source ID → 在 Synthesizer 验证时拒绝。"""
        # 这个测试在 test_serenity_synthesizer.py 中已覆盖
        # （test_synthesizer_rejects_non_existent_source_ids）
        pass
    
    def test_llm_omitted_required_source_id_rejected(self):
        """LLM 遗漏必需的 source ID → 在门禁拒绝。"""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="2025 年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
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
            unresolved_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        # LLM 在 rationale 中遗漏了 supporting_source_ids
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": []  # 空列表
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "遗漏 supporting_source_ids 的候选必须被拒绝")


if __name__ == "__main__":
    unittest.main()
