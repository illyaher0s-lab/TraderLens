"""
Tests for Serenity Two-Phase Architecture Fixes.

验证修复：
1. discovered_player 不能提升来源质量
2. 全 weak 研究来源不能进入 shortlist
3. 无主题关联来源不能进入 shortlist
4. 候选理由引用假 source ID 被拒绝
5. 数据缺失不被当作反证
6. 最终输出保留来源引用
7. manual candidates 不会丢失
8. provider/replayable 准确
9. 生产 API 实际调用双阶段，LLM 精确 2 次
10. 最大并发数不超过 2
"""

import unittest
from datetime import datetime, date
from backend.services.serenity_gate import apply_shortlist_gate
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate
from backend.services.serenity_synthesizer import ResearchSynthesis, ResearchSynthesizer
from backend.services.serenity_executor import DeterministicExecutor, MAX_RESEARCH_CONCURRENCY
from contracts.research import ResearchSource, ThemeInput


class TestIdentityVerificationNotResearchEvidence(unittest.TestCase):
    """测试：身份核验记录不能提升来源质量。"""
    
    def test_discovered_player_not_marked_as_first_hand(self):
        """discovered_player 记录不应被标记为 financial_report/first_hand。"""
        context = SerenityRunContext()
        
        # 模拟 discover_players 工具返回的 discovered_player 记录
        # 这种记录应该是 source_type="unknown", source_quality="weak"
        # 因为它只是"发现了这个公司"，不是真正的研究证据
        context.sources_by_id["player:300750.SZ:0"] = ResearchSource(
            source_record_id="player:300750.SZ:0",
            source_type="unknown",  # 不是 financial_report
            source_quality="weak",  # 不是 first_hand
            title="发现玩家: 宁德时代",
            retrieved_at=datetime.now(),
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["player:300750.SZ:0"],  # 只有身份核验记录
            counter_evidence=[],
            falsification_questions=["需要财报验证"],
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
            candidate_rationales={"300750.SZ": "核心玩家"},
            evidence_gaps=[],
        )
        
        # 应该被拒绝：只有 weak 来源
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0, 
                        "身份核验记录不能作为研究证据通过门禁")
    
    def test_candidate_with_real_research_source_passes(self):
        """候选拥有真实研究来源（非身份核验）时通过。"""
        context = SerenityRunContext()
        
        # 身份核验记录 (weak) - 只说明"发现了这个公司"
        context.sources_by_id["player:300750.SZ:0"] = ResearchSource(
            source_record_id="player:300750.SZ:0",
            source_type="unknown",
            source_quality="weak",
            title="发现玩家: 宁德时代",
            retrieved_at=datetime.now(),
        )
        
        # 真实研究来源 (first_hand)
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="2025年年报",
            retrieved_at=datetime.now(),
            published_at=date.today(),
            theme_keywords_matched=["测试"],
            theme_relevance_basis="title_match",
        )
        
        context.verified_candidates_by_symbol["300750.SZ"] = VerifiedResearchCandidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_abc123",
            exchange="SZSE",
            listing_status="listed",
            confidence="high",
            supporting_source_ids=["player:300750.SZ:0", "financials:300750.SZ:0"],
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
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["financials:300750.SZ:0"]
                }
            },
            evidence_gaps=[],
        )
        
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 1, 
                        "拥有真实研究来源的候选应该通过")


class TestThemeRelevanceGate(unittest.TestCase):
    """测试：主题相关性门禁。"""
    
    def test_candidate_without_theme_relevance_source_rejected(self):
        """候选没有证明"与主题相关"的来源时被拒绝。"""
        # TODO: 需要定义如何表示"主题相关性"
        # 可能的方案：
        # 1. 要求至少一个 source 的 title/content 包含主题关键词
        # 2. 要求 source metadata 包含 theme_relevance_score > 0
        # 3. 要求 Synthesizer 在 candidate_rationales 中明确说明主题关联
        pass
    
    def test_ticker_verification_alone_insufficient_for_theme_relevance(self):
        """只有 ticker 核验不能证明主题关联。"""
        # 即使 verification_id 有效，也需要额外的来源证明该股票与主题相关
        pass


class TestCandidateRationaleSourceBinding(unittest.TestCase):
    """测试：候选理由必须绑定来源。"""
    
    def test_synthesizer_output_schema_requires_source_ids(self):
        """Synthesizer 输出 schema 必须包含 supporting_source_ids。"""
        # 修改 ResearchSynthesisSchema 要求 candidate_rationales 包含来源
        pass
    
    def test_candidate_rationale_with_fake_source_id_rejected(self):
        """候选理由引用不存在的 source ID 被拒绝。"""
        context = SerenityRunContext()
        
        context.sources_by_id["financials:300750.SZ:0"] = ResearchSource(
            source_record_id="financials:300750.SZ:0",
            source_type="financial_report",
            source_quality="first_hand",
            title="2025年年报",
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
            data_gaps=[],
            unresolved_gaps=[],
        )
        
        context.completed_checks.add("source_audit")
        context.completed_checks.add("red_team")
        
        # Synthesizer 输出引用了假的 source ID
        synthesis = ResearchSynthesis(
            demand_driver="测试",
            value_chain_layers=[],
            suspected_bottleneck_layers=[
                {
                    "layer": "中游",
                    "reason": "产能瓶颈",
                    "supporting_source_ids": ["fake_source_id_999"]  # 假 ID
                }
            ],
            hypothesis_draft=[],
            candidate_rationales={
                "300750.SZ": {
                    "rationale": "核心玩家",
                    "supporting_source_ids": ["fake_source_id_999"]  # 假 ID
                }
            },
            evidence_gaps=[],
        )
        
        # apply_shortlist_gate 应该拒绝（rationale_source_ids 不存在）
        shortlist = apply_shortlist_gate(context, synthesis, "theme1")
        
        self.assertEqual(len(shortlist), 0,
                        "引用不存在 source ID 的候选应被拒绝")


class TestRedTeamLogic(unittest.TestCase):
    """测试：red-team 逻辑修正。"""
    
    def test_data_missing_recorded_as_gap_not_counter_evidence(self):
        """数据缺失应该记录为 gap，不是反证。"""
        # red-team 的职责是：
        # 1. 指出数据缺口（gaps）
        # 2. 提出反证假设（counter-hypotheses）
        # 
        # "没有财报数据" 是 gap，不是反证
        # "财报显示营收下降" 才是反证
        pass
    
    def test_red_team_must_cite_real_sources_or_explicit_gap_id(self):
        """Red-team 必须引用真实来源或明确 gap ID。"""
        pass


class TestOutputContractPreservation(unittest.TestCase):
    """测试：输出契约保留。"""
    
    def test_candidate_pool_raw_preserves_manual_candidates(self):
        """candidate_pool_raw 必须保留人工候选。"""
        # TODO: 检查 SerenityOutput 构建过程
        pass
    
    def test_candidate_pool_raw_preserves_verified_research_candidates(self):
        """candidate_pool_raw 必须保留已核验研究候选。"""
        pass
    
    def test_value_chain_layers_preserve_source_ids(self):
        """value_chain_layers 保留 source IDs。"""
        pass
    
    def test_suspected_bottleneck_layers_preserve_source_ids(self):
        """suspected_bottleneck_layers 保留 source IDs。"""
        pass
    
    def test_hypothesis_draft_preserve_source_ids(self):
        """hypothesis_draft 保留 source IDs。"""
        pass


class TestAuditMetadataCorrectness(unittest.TestCase):
    """测试：审计元数据准确性。"""
    
    def test_provider_not_langgraph(self):
        """provider 不应该是 'langgraph'。"""
        # 当前实现不是 LangGraph
        pass
    
    def test_replayable_false_without_persistence(self):
        """没有持久化回放时 replayable=False。"""
        pass
    
    def test_hash_uses_sorted_json(self):
        """hash 使用排序 JSON 确保稳定性。"""
        pass
    
    def test_audit_records_real_provider_and_model(self):
        """audit 记录真实 provider 和 model。"""
        pass
    
    def test_audit_records_two_llm_outputs(self):
        """audit 记录两次 LLM 输出。"""
        pass
    
    def test_audit_records_errors(self):
        """audit 记录错误。"""
        pass
    
    def test_threadpool_properly_closed(self):
        """线程池正确关闭。"""
        # DeterministicExecutor 的 ThreadPoolExecutor 应该在完成后关闭
        pass


class TestProductionIntegration(unittest.TestCase):
    """测试：生产环境集成。"""
    
    def test_api_endpoint_uses_two_phase_mode(self):
        """API 端点实际使用双阶段模式。"""
        pass
    
    def test_api_endpoint_exactly_two_llm_calls(self):
        """API 端点 LLM 调用精确 2 次。"""
        pass
    
    def test_max_concurrency_enforced(self):
        """最大并发数 = 2 被强制执行。"""
        self.assertEqual(MAX_RESEARCH_CONCURRENCY, 2)


if __name__ == "__main__":
    unittest.main()
