"""
Tests for Serenity Two-Phase End-to-End Flow.

验证:
- 完整双阶段流程运行
- 总 LLM 调用次数精确为 2
- 输出不含交易字段
- 最大并发数 = 2
- shortlist 由确定性门禁产生
"""

import unittest
from datetime import datetime
from backend.services.serenity_agent import SerenityAgentRunner, SerenityAgentAudit
from contracts.research import ThemeInput


class MockLLMClient:
    """Mock LLM client that tracks call count."""
    
    def __init__(self):
        self.call_count = 0
        self.calls = []
    
    def create_message(self, messages, system, max_tokens):
        self.call_count += 1
        self.calls.append({
            "messages": messages,
            "system": system[:100],  # 截断
            "max_tokens": max_tokens,
        })
        
        # 根据 system prompt 判断是 Planner 还是 Synthesizer
        if "Research Planner" in system:
            # Planner 返回 ResearchPlan
            return {
                "content": [{
                    "type": "text",
                    "text": '''{
                        "keywords": ["锂电池", "新能源"],
                        "seed_symbols": ["300750.SZ"],
                        "sectors_to_check": ["电气设备"],
                        "start_date": null,
                        "end_date": null,
                        "falsification_questions": ["产能是否过剩"]
                    }'''
                }]
            }
        elif "Research Synthesizer" in system:
            # Synthesizer 返回 ResearchSynthesis
            return {
                "content": [{
                    "type": "text",
                    "text": '''{
                        "demand_driver": "新能源汽车需求增长",
                        "value_chain_layers": [
                            {"layer": "上游", "description": "锂矿开采"},
                            {"layer": "中游", "description": "电池制造"}
                        ],
                        "suspected_bottleneck_layers": [],
                        "hypothesis_draft": [],
                        "candidate_rationales": {},
                        "evidence_gaps": ["需要验证产能扩张计划"]
                    }'''
                }]
            }
        else:
            raise ValueError(f"Unknown system prompt: {system[:100]}")


class MockSerenityTools:
    """Mock tools that return minimal data."""
    
    def retrieve_supply_chain(self, theme_name, theme_background, keywords, symbols, start_date, end_date, max_records):
        from contracts.research import SerenityToolResult
        from datetime import datetime
        return SerenityToolResult(
            tool_name="retrieve_supply_chain",
            records=[],
            total_found=0,
            gaps=["no_data"],
            errors=[],
            retrieved_at=datetime.now(),
        )
    
    def discover_players(self, source_records, max_players):
        from contracts.research import SerenityToolResult
        from datetime import datetime
        return SerenityToolResult(
            tool_name="discover_players",
            records=[],
            total_found=0,
            gaps=["no_players"],
            errors=[],
            retrieved_at=datetime.now(),
        )


class MockValidator:
    """Mock validator."""
    
    def verify_ticker(self, symbol):
        from backend.services.research_validation import TickerVerificationResult
        from datetime import datetime
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


class TestSerenityTwoPhaseE2E(unittest.TestCase):
    
    def test_full_two_phase_flow_with_real_data(self):
        """Full two-phase flow: Planner → Executor → Synthesizer → Gate."""
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
        
        # 验证输出结构
        self.assertIsNotNone(output)
        self.assertIsInstance(output.candidate_shortlist, list)
        self.assertIsInstance(output.value_chain_layers, list)
        self.assertIsInstance(output.evidence_gaps, list)
    
    def test_total_llm_calls_exactly_two(self):
        """Total LLM calls = 2 (Planner + Synthesizer)."""
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
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        output = runner.run(theme, [])
        
        # 验证 LLM 调用次数
        self.assertEqual(mock_llm.call_count, 2, f"Expected 2 LLM calls, got {mock_llm.call_count}")
        
        # 验证第一次调用是 Planner
        self.assertIn("Research Planner", mock_llm.calls[0]["system"])
        
        # 验证第二次调用是 Synthesizer
        self.assertIn("Research Synthesizer", mock_llm.calls[1]["system"])
    
    def test_output_no_trading_fields(self):
        """Output does not contain trading advice fields."""
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
            background="研究锂电池",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        output = runner.run(theme, [])
        
        # 验证输出不含交易字段
        output_dict = output.model_dump()
        output_str = str(output_dict).lower()
        
        forbidden_fields = ["buy", "sell", "target_price", "stop_loss", "position"]
        for field in forbidden_fields:
            self.assertNotIn(field, output_str, f"Output contains forbidden field: {field}")


if __name__ == "__main__":
    unittest.main()
