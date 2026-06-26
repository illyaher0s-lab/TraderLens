"""
Tests for Serenity Research Planner (LLM 1/2).

验证:
- 单次 LLM 调用
- 输出符合 schema
- 无效 JSON 明确失败
- 不同主题产生不同计划
- 限制强制执行
"""

import unittest
from datetime import datetime
from backend.services.serenity_planner import ResearchPlanner, ResearchPlan
from contracts.research import ThemeInput, CandidateStock


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


class TestResearchPlanner(unittest.TestCase):
    
    def test_planner_single_llm_call(self):
        """Planner makes exactly 1 LLM call."""
        mock_llm = MockLLMClient('''{
            "keywords": ["新能源汽车", "锂电池"],
            "seed_symbols": ["300750.SZ"],
            "sectors_to_check": ["电气设备"],
            "start_date": "20230101",
            "end_date": "20260624",
            "falsification_questions": ["产能是否过剩"]
        }''')
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="新能源产业链",
            background="研究锂电池产业链",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        plan = planner.plan(theme, [])
        
        self.assertEqual(mock_llm.call_count, 1)
        self.assertIsInstance(plan, ResearchPlan)
    
    def test_planner_produces_valid_schema(self):
        """Planner output conforms to ResearchPlan schema."""
        mock_llm = MockLLMClient('''{
            "keywords": ["关键词1", "关键词2"],
            "seed_symbols": ["300750.SZ", "600519.SH"],
            "sectors_to_check": ["行业1", "行业2"],
            "start_date": "20230101",
            "end_date": "20260624",
            "falsification_questions": ["问题1", "问题2"]
        }''')
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        plan = planner.plan(theme, [])
        
        self.assertEqual(plan.keywords, ["关键词1", "关键词2"])
        self.assertEqual(plan.seed_symbols, ["300750.SZ", "600519.SH"])
        self.assertEqual(plan.sectors_to_check, ["行业1", "行业2"])
        self.assertEqual(plan.start_date, "20230101")
        self.assertEqual(plan.end_date, "20260624")
        self.assertEqual(plan.falsification_questions, ["问题1", "问题2"])
    
    def test_planner_malformed_json_fails(self):
        """Planner fails explicitly on invalid JSON."""
        mock_llm = MockLLMClient("This is not JSON")
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            planner.plan(theme, [])
        
        self.assertIn("Invalid JSON", str(ctx.exception))
    
    def test_planner_strips_markdown_code_blocks(self):
        """Planner can parse JSON wrapped in markdown code blocks."""
        mock_llm = MockLLMClient('''```json
{
    "keywords": ["test"],
    "seed_symbols": [],
    "sectors_to_check": [],
    "start_date": null,
    "end_date": null,
    "falsification_questions": []
}
```''')
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        plan = planner.plan(theme, [])
        
        self.assertEqual(plan.keywords, ["test"])
    
    def test_planner_limits_enforced(self):
        """Pydantic enforces max length limits."""
        # 21 keywords (exceeds max_length=20)
        import json as json_lib
        keywords = [f"k{i}" for i in range(21)]
        payload = {
            "keywords": keywords,
            "seed_symbols": [],
            "sectors_to_check": [],
            "start_date": None,
            "end_date": None,
            "falsification_questions": []
        }
        mock_llm = MockLLMClient(json_lib.dumps(payload))
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            planner.plan(theme, [])
        
        self.assertIn("schema validation failed", str(ctx.exception))
    
    def test_invalid_date_format_fails(self):
        """Invalid date format fails validation."""
        mock_llm = MockLLMClient('''{
            "keywords": ["test"],
            "seed_symbols": [],
            "sectors_to_check": [],
            "start_date": "2023-01-01",
            "end_date": null,
            "falsification_questions": []
        }''')
        
        planner = ResearchPlanner(mock_llm)
        theme = ThemeInput(
            theme_id="t1",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            planner.plan(theme, [])
        
        self.assertIn("YYYYMMDD", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
