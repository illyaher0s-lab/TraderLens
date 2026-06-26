"""
Serenity Research Planner (双阶段重构 - LLM 1/2).

生成结构化研究计划，替代多轮 LLM 工具调用。

输入: ThemeInput + manual_candidates
输出: ResearchPlan (keywords, seed_symbols, sectors, falsification_questions)

硬约束:
- 单次 LLM 调用
- Pydantic 严格验证
- 无效 schema → 明确失败
"""

from dataclasses import dataclass
import json
import re
from pydantic import BaseModel, Field, field_validator


class ResearchPlanSchema(BaseModel):
    """Pydantic schema for Research Planner output."""
    keywords: list[str] = Field(max_length=20)
    seed_symbols: list[str] = Field(max_length=10)
    sectors_to_check: list[str] = Field(max_length=5)
    start_date: str | None = None
    end_date: str | None = None
    falsification_questions: list[str] = Field(max_length=10)

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v):
        if v is not None and not re.match(r'^\d{8}$', v):
            raise ValueError(f"Date must be YYYYMMDD format, got: {v}")
        return v


@dataclass
class ResearchPlan:
    """Structured research plan from Planner."""
    keywords: list[str]
    seed_symbols: list[str]
    sectors_to_check: list[str]
    start_date: str | None
    end_date: str | None
    falsification_questions: list[str]


class ResearchPlanner:
    """Generate structured research plan from theme (LLM 1/2)."""
    
    SYSTEM_PROMPT = """You are a Research Planner. Generate a structured research plan.
    
OUTPUT SCHEMA:
{
  "keywords": ["关键词1", "关键词2"],
  "seed_symbols": ["300750.SZ", "600519.SH"],
  "sectors_to_check": ["电气设备", "食品饮料"],
  "start_date": "20230101",
  "end_date": "20260624",
  "falsification_questions": ["问题1", "问题2"]
}

RULES:
- keywords: 最多 20 个
- seed_symbols: 最多 10 个（这些是检索起点，不是已验证玩家）
- sectors_to_check: 最多 5 个
- falsification_questions: 最多 10 个
- 日期格式必须是 YYYYMMDD
- 不要输出 buy/sell/target/stop/position
- 必须输出有效 JSON，不要添加 markdown 代码块标记
"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.last_response_metadata = None  # 保存响应元数据（不包含敏感 prompt）
    
    def plan(self, theme, manual_candidates: list) -> ResearchPlan:
        """Generate research plan from theme.
        
        Args:
            theme: ThemeInput with theme_name, background, research_mode
            manual_candidates: list[CandidateStock] already provided
            
        Returns:
            ResearchPlan with validated fields
            
        Raises:
            ValueError: if LLM returns invalid JSON or schema
        """
        prompt = f"""研究主题: {theme.theme_name}
背景: {theme.background}
研究模式: {theme.research_mode}
已有人工候选: {', '.join(c.symbol for c in manual_candidates) if manual_candidates else '无'}

请生成研究计划（仅输出 JSON，不要 markdown 代码块）。"""
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            system=self.SYSTEM_PROMPT,
            max_tokens=1024,
        )
        
        # 保存响应元数据用于审计（不包含完整 prompt）
        self.last_response_metadata = {
            "model": response.get("model"),
            "usage": response.get("usage"),
        }
        
        # Extract text from response
        text = self._extract_text(response)
        
        # Parse JSON
        plan_dict = self._parse_json(text)
        
        # Pydantic validation
        try:
            schema = ResearchPlanSchema(**plan_dict)
        except Exception as exc:
            raise ValueError(f"ResearchPlan schema validation failed: {exc}") from exc
        
        return ResearchPlan(
            keywords=schema.keywords,
            seed_symbols=schema.seed_symbols,
            sectors_to_check=schema.sectors_to_check,
            start_date=schema.start_date,
            end_date=schema.end_date,
            falsification_questions=schema.falsification_questions,
        )
    
    def _extract_text(self, response: dict) -> str:
        """Extract text content from LLM response."""
        content = response.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
        elif isinstance(content, str):
            return content
        raise ValueError("No text content in LLM response")
    
    def _parse_json(self, text: str) -> dict:
        """Parse JSON from text, stripping markdown code blocks if present."""
        text = text.strip()
        
        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}. Text: {text[:200]}") from exc
