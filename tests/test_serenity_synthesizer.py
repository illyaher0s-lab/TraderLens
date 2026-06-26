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
from datetime import datetime, date
from backend.services.serenity_synthesizer import ResearchSynthesizer, ResearchSynthesis
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit, VerifiedResearchCandidate
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
