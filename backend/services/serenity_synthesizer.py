"""
Serenity Research Synthesizer (双阶段重构 - LLM 2/2).

整合已验证的研究结果，生成结构化分析输出。

输入: SerenityRunContext（已验证候选 + 真实来源）
输出: ResearchSynthesis（产业链分析 + 瓶颈假设 + 证据缺口）

硬约束:
- 单次 LLM 调用
- 所有 source IDs 必须存在于 context
- LLM 不能覆盖 company_name、verification_id
"""

from dataclasses import dataclass, field
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from backend.services.serenity_agent import SerenityRunContext, SerenityAgentAudit
from contracts.research import ThemeInput


class CandidateVerdictSchema(BaseModel):
    """The Synthesizer's evidence-bound decision for one verified symbol."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal[
        "research_positive",
        "research_watch",
        "research_reject",
        "research_unavailable",
    ]
    reason: str
    supporting_source_ids: list[str]
    counter_evidence: list[dict]
    invalidation_conditions: list[str]
    evidence_gaps: list[str]

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("candidate verdict reason must be non-empty")
        return value

    @model_validator(mode="after")
    def require_evidence_for_verdict(self):
        if self.verdict == "research_unavailable":
            if not self.evidence_gaps:
                raise ValueError("research_unavailable requires a non-empty evidence_gaps list")
        elif not self.supporting_source_ids:
            raise ValueError("research verdict requires supporting source IDs")
        return self


class ResearchSynthesisSchema(BaseModel):
    """Pydantic schema for Research Synthesizer output."""
    demand_driver: str
    value_chain_layers: list[dict]
    suspected_bottleneck_layers: list[dict]
    hypothesis_draft: list[dict]
    candidate_rationales: dict[str, dict] = Field(default_factory=dict)
    candidate_verdicts: dict[str, CandidateVerdictSchema] = Field(default_factory=dict)
    evidence_gaps: list[str]


@dataclass
class ResearchSynthesis:
    """Structured research synthesis from Synthesizer."""
    demand_driver: str
    value_chain_layers: list[dict]
    suspected_bottleneck_layers: list[dict]
    hypothesis_draft: list[dict]
    candidate_rationales: dict[str, dict]  # symbol → {rationale, supporting_source_ids}
    evidence_gaps: list[str]
    candidate_verdicts: dict[str, dict] = field(default_factory=dict)


class ResearchSynthesizer:
    """Synthesize research findings into structured output (LLM 2/2)."""
    
    SYSTEM_PROMPT = """You are a Research Synthesizer. Produce structured research synthesis.

OUTPUT SCHEMA:
{
  "demand_driver": "需求驱动因素",
  "value_chain_layers": [
    {"layer": "上游", "description": "...", "supporting_source_ids": ["financials:300750.SZ:0"]}
  ],
  "suspected_bottleneck_layers": [
    {"layer": "中游", "reason": "...", "supporting_source_ids": ["financials:300750.SZ:0"]}
  ],
  "hypothesis_draft": [
    {"hypothesis": "...", "rationale": "...", "confidence": "medium|high|low", "supporting_source_ids": ["financials:300750.SZ:0"]}
  ],
  "candidate_rationales": {
    "300750.SZ": {
      "rationale": "产业链核心环节",
      "supporting_source_ids": ["financials:300750.SZ:0"],
      "falsification_questions": ["产能扩张计划是否落实？"],
      "counter_evidence": [
        {"description": "营收下降 10%", "source_record_id": "financials:300750.SZ:0"}
      ]
    }
  },
  "candidate_verdicts": {
    "300750.SZ": {
      "verdict": "research_positive|research_watch|research_reject|research_unavailable",
      "reason": "基于已引用证据的简明研究理由",
      "supporting_source_ids": ["financials:300750.SZ:0"],
      "counter_evidence": [
        {"description": "结构化反证", "source_record_id": "financials:300750.SZ:0"}
      ],
      "invalidation_conditions": ["可观察的失效条件"],
      "evidence_gaps": ["仍缺少的关键信息"]
    }
  },
  "evidence_gaps": ["需要验证产能扩张计划"]
}

RULES:
- value_chain_layers, bottleneck, hypothesis 和 candidate_rationales 必须携带 supporting_source_ids
- candidate_rationales 的 key 必须是已验证的 symbol
- candidate_rationales 的 value 必须包含 rationale, supporting_source_ids, falsification_questions, counter_evidence
- candidate_verdicts 必须为每个已验证候选输出结构化 verdict、reason、supporting_source_ids、counter_evidence、invalidation_conditions、evidence_gaps
- verdict 只能是 research_positive、research_watch、research_reject、research_unavailable；research_unavailable 必须给出非空 reason 和 evidence_gaps，不能伪造引用
- 非 research_unavailable verdict 必须有至少一个 supporting_source_id；counter_evidence 的 source_record_id 必须真实存在且属于同一 symbol
- positive 只表示有继续人工审阅的研究依据，不是买入建议、候选入池或执行许可
- falsification_questions: 待验证问题，必须明确包含当前 symbol 或公司名或主题关键词
- counter_evidence: 反证，必须是结构化对象 {description, source_record_id}，source_record_id 必须属于该 symbol
- 公告标题和日期不能用于推断公告正文；公告列表来源只证明列表元数据，正文内容未知
- full_text_unavailable 是确定性证据缺口，不得忽略或声称已知正文内容
- 不要创造公司名、ticker、财务数字
- 不要输出 buy/sell/target/stop/position
- 必须输出有效 JSON，不要添加 markdown 代码块标记
"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.last_response_metadata = None  # 保存响应元数据（不包含敏感 prompt）

    @staticmethod
    def _failure_diagnostic(exc: Exception) -> dict:
        """Return only the safe failure class and, for HTTP failures, status."""
        chain = []
        current = exc
        seen = set()
        while isinstance(current, BaseException) and id(current) not in seen:
            seen.add(id(current))
            chain.append(current)
            current = current.__cause__ or current.__context__

        call_diagnostics = [
            getattr(item, "call_diagnostic", None)
            for item in chain
        ]
        call_diagnostics = [item for item in call_diagnostics if isinstance(item, dict)]

        is_timeout = any(
            diagnostic.get("timeout") is True
            for diagnostic in call_diagnostics
        ) or any(
            "timeout" in base.__name__.lower()
            for item in chain
            for base in type(item).__mro__
        )
        if is_timeout:
            return {"stage": "synthesizer", "failure_class": "timeout"}

        http_status = next(
            (
                diagnostic.get("http_status")
                for diagnostic in call_diagnostics
                if type(diagnostic.get("http_status")) is int
                and 100 <= diagnostic["http_status"] <= 599
            ),
            None,
        )
        if http_status is None:
            http_status = next(
                (
                    status
                    for item in chain
                    if type(status := getattr(item, "status_code", None)) is int
                    and 100 <= status <= 599
                ),
                None,
            )

        if http_status is not None:
            return {
                "stage": "synthesizer",
                "failure_class": "http",
                "http_status": http_status,
            }
        return {"stage": "synthesizer", "failure_class": "client_exception"}
    
    def synthesize(
        self,
        theme: ThemeInput,
        context: SerenityRunContext,
        audit: SerenityAgentAudit,
    ) -> ResearchSynthesis:
        """Synthesize research findings.
        
        Args:
            theme: ThemeInput with theme_name, background
            context: SerenityRunContext with verified candidates and sources
            audit: SerenityAgentAudit for recording errors
            
        Returns:
            ResearchSynthesis with validated fields
            
        Raises:
            ValueError: if LLM returns invalid JSON, schema, or non-existent source IDs
        """
        
        # 构建压缩后的研究包（带边界限制）
        research_pack, pack_meta = self._build_research_pack(theme, context)
        self.last_response_metadata = None

        try:
            response = self.llm_client.create_message(
                messages=[{"role": "user", "content": research_pack}],
                system=self.SYSTEM_PROMPT,
                max_tokens=1024,
            )
        except Exception as exc:
            audit.call_diagnostics.append(self._failure_diagnostic(exc))
            raise

        self.last_response_metadata = {
            "model": response.get("model"),
            "usage": response.get("usage"),
        }

        # Extract text from response
        text = self._extract_text(response)
        
        # Parse JSON
        synthesis_dict = self._parse_json(text)
        
        # Validate schema
        try:
            schema = ResearchSynthesisSchema(**synthesis_dict)
        except Exception as exc:
            raise ValueError(f"ResearchSynthesis schema validation failed: {exc}") from exc
        
        # Validate all source IDs exist in context
        self._validate_source_ids(synthesis_dict, context, audit)
        self._validate_candidate_verdicts(schema.candidate_verdicts, context)
        
        # 绑定 red-team 结果到候选
        self._bind_red_team_results(synthesis_dict, context, audit)
        
        # 将截断信息添加到 evidence_gaps
        evidence_gaps = list(schema.evidence_gaps)
        for source in context.sources_by_id.values():
            for gap in source.gaps:
                if gap not in evidence_gaps:
                    evidence_gaps.append(gap)
        if pack_meta['omitted_sources'] > 0:
            evidence_gaps.append(
                f"synthesizer_input_truncated: {pack_meta['omitted_sources']} sources omitted"
            )
        if pack_meta['omitted_source_ids'] > 0:
            evidence_gaps.append(
                f"synthesizer_input_truncated: {pack_meta['omitted_source_ids']} source_ids omitted from candidates"
            )
        
        return ResearchSynthesis(
            demand_driver=schema.demand_driver,
            value_chain_layers=schema.value_chain_layers,
            suspected_bottleneck_layers=schema.suspected_bottleneck_layers,
            hypothesis_draft=schema.hypothesis_draft,
            candidate_rationales=schema.candidate_rationales,
            evidence_gaps=evidence_gaps,
            candidate_verdicts={
                symbol: decision.model_dump(mode="json")
                for symbol, decision in schema.candidate_verdicts.items()
            },
        )

    def _validate_candidate_verdicts(self, verdicts, context):
        """Bind every Synthesizer decision reference to an existing same-symbol source."""
        for symbol, decision in verdicts.items():
            candidate = context.verified_candidates_by_symbol.get(symbol)
            if candidate is None:
                raise ValueError("Synthesizer verdict references an unverified symbol")

            def validate_reference(source_id):
                if not isinstance(source_id, str):
                    raise ValueError("Synthesizer verdict source reference must be a string")
                parts = source_id.split(":")
                if (
                    len(parts) != 3
                    or parts[1] != symbol
                    or not parts[2].isdigit()
                    or source_id not in context.sources_by_id
                ):
                    raise ValueError("Synthesizer verdict source reference is invalid")

            for source_id in decision.supporting_source_ids:
                validate_reference(source_id)
            for counter in decision.counter_evidence:
                if not isinstance(counter, dict):
                    raise ValueError("Synthesizer counter evidence must be structured")
                if not isinstance(counter.get("description"), str) or not counter["description"].strip():
                    raise ValueError("Synthesizer counter evidence requires a description")
                source_id = counter.get("source_record_id")
                validate_reference(source_id)
                if context.sources_by_id[source_id].source_quality == "weak":
                    raise ValueError("Synthesizer counter evidence source is weak")
            if any(not isinstance(value, str) or not value.strip() for value in decision.invalidation_conditions):
                raise ValueError("Synthesizer invalidation conditions must be non-empty strings")
            if any(not isinstance(value, str) or not value.strip() for value in decision.evidence_gaps):
                raise ValueError("Synthesizer evidence gaps must be non-empty strings")
            if decision.verdict != "research_unavailable" and not any(
                source_id.startswith(("financials:", "announcements:"))
                for source_id in decision.supporting_source_ids
            ):
                raise ValueError("Synthesizer verdict has no traceable financial or announcement source")
    
    def _build_research_pack(self, theme: ThemeInput, context: SerenityRunContext) -> tuple[str, dict]:
        """构建压缩的研究包（带确定性边界限制）.
        
        V2: 只综合目标标的的来源。
        
        Returns:
            (prompt_str, metadata_dict) 元组
            metadata contains only evidence omission counts used to report gaps.
        """
        # 硬边界
        MAX_SOURCE_IDS_PER_CANDIDATE = 10
        MAX_SOURCE_SUMMARY_COUNT = 20  # V2: 单标的上限
        
        pack = {
            "theme": theme.theme_name,
            "background": theme.background,
            "verified_candidates": [],
            "source_summary": [],
        }
        
        # 统计
        total_omitted_source_ids = 0
        
        # V2: 只发送第一个候选（目标标的）
        candidates_to_send = list(context.verified_candidates_by_symbol.items())[:1]
        
        for symbol, candidate in candidates_to_send:
            source_ids = candidate.supporting_source_ids[:MAX_SOURCE_IDS_PER_CANDIDATE]
            omitted = len(candidate.supporting_source_ids) - len(source_ids)
            
            total_omitted_source_ids += omitted
            
            pack["verified_candidates"].append({
                "symbol": symbol,
                "company_name": candidate.company_name,
                "source_ids": source_ids,
                "counter_evidence": candidate.counter_evidence,
                "falsification_questions": candidate.falsification_questions,
                "data_gaps": candidate.data_gaps,
                "unresolved_gaps": candidate.unresolved_gaps,
            })
        
        # 只发送来源类型和质量（限制数量）
        all_sources = list(context.sources_by_id.items())
        sources_to_send = all_sources[:MAX_SOURCE_SUMMARY_COUNT]
        omitted_sources = len(all_sources) - len(sources_to_send)
        
        for sid, source in sources_to_send:
            source_summary = {
                "id": sid,
                "type": source.source_type,
                "quality": source.source_quality,
                "title": source.title[:100],  # 截断标题
            }
            if sid.startswith("financials:"):
                source_summary["as_of"] = (
                    source.published_at.isoformat() if source.published_at else None
                )
                source_summary["summary"] = (source.summary or "")[:500]
            elif sid.startswith("stock_company:"):
                source_summary["as_of"] = source.retrieved_at.isoformat()
                source_summary["as_of_basis"] = "retrieved_at"
                source_summary["summary"] = (source.summary or "")[:500]
            elif source.source_type == "announcement":
                source_summary["as_of"] = (
                    source.published_at.isoformat() if source.published_at else None
                )
                source_summary["as_of_basis"] = "publication_date"
                source_summary["source_url"] = source.source_url
                source_summary["summary"] = (source.summary or "")[:500]
                source_summary["evidence_scope"] = "announcement_list_metadata_only"
                source_summary["gaps"] = list(source.gaps)
            pack["source_summary"].append(source_summary)
        
        prompt = f"""研究主题: {theme.theme_name}

已验证候选 ({len(pack['verified_candidates'])} 个):
{json.dumps(pack['verified_candidates'], ensure_ascii=False, indent=2)}

来源摘要 ({len(pack['source_summary'])} 个):
{json.dumps(pack['source_summary'], ensure_ascii=False, indent=2)}

请整合以上研究结果，生成结构化分析（仅输出 JSON，不要 markdown 代码块）。"""
        
        metadata = {
            "omitted_sources": omitted_sources,
            "omitted_source_ids": total_omitted_source_ids,
        }
        
        return prompt, metadata
    
    def _validate_source_ids(
        self, 
        synthesis_dict: dict, 
        context: SerenityRunContext, 
        audit: SerenityAgentAudit
    ):
        """验证所有 source IDs 存在于 context."""
        
        all_source_ids = set()
        
        # 收集所有 source IDs
        for layer in synthesis_dict.get("value_chain_layers", []):
            if "supporting_source_ids" in layer:
                all_source_ids.update(layer["supporting_source_ids"])
        
        for bottleneck in synthesis_dict.get("suspected_bottleneck_layers", []):
            if "supporting_source_ids" in bottleneck:
                all_source_ids.update(bottleneck["supporting_source_ids"])
        
        for hypothesis in synthesis_dict.get("hypothesis_draft", []):
            if "supporting_source_ids" in hypothesis:
                all_source_ids.update(hypothesis["supporting_source_ids"])
        
        # 验证 candidate_rationales 中的 source IDs
        for symbol, rationale_data in synthesis_dict.get("candidate_rationales", {}).items():
            if isinstance(rationale_data, dict) and "supporting_source_ids" in rationale_data:
                all_source_ids.update(rationale_data["supporting_source_ids"])
            
            # 验证 counter_evidence 中的 source IDs
            if isinstance(rationale_data, dict) and "counter_evidence" in rationale_data:
                for ce in rationale_data.get("counter_evidence", []):
                    if isinstance(ce, dict) and "source_record_id" in ce:
                        all_source_ids.add(ce["source_record_id"])

        for decision in synthesis_dict.get("candidate_verdicts", {}).values():
            if not isinstance(decision, dict):
                continue
            all_source_ids.update(decision.get("supporting_source_ids", []))
            for counter in decision.get("counter_evidence", []):
                if isinstance(counter, dict) and "source_record_id" in counter:
                    all_source_ids.add(counter["source_record_id"])
        
        # 验证每个 ID 存在
        for sid in all_source_ids:
            if sid not in context.sources_by_id:
                audit.errors.append(f"synthesizer: non-existent source_id: {sid}")
                raise ValueError(f"Synthesizer referenced non-existent source_id: {sid}")
    
    def _bind_red_team_results(
        self,
        synthesis_dict: dict,
        context: SerenityRunContext,
        audit: SerenityAgentAudit
    ):
        """确定性绑定 LLM 生成的 red-team 结果到候选。
        
        验证规则：
        1. falsification_question 必须包含 symbol/company_name/主题关键词
        2. counter_evidence 必须有 source_record_id，且属于该 symbol
        3. counter_evidence.source_record_id 必须存在且 source_quality != weak
        """
        for symbol, rationale_data in synthesis_dict.get("candidate_rationales", {}).items():
            if not isinstance(rationale_data, dict):
                continue
            
            candidate = context.verified_candidates_by_symbol.get(symbol)
            if not candidate:
                audit.errors.append(f"synthesizer: candidate {symbol} not found in context")
                continue
            
            # 1. 绑定 falsification_questions（验证相关性）
            questions = rationale_data.get("falsification_questions", [])
            for q in questions:
                if not isinstance(q, str):
                    continue
                
                # 验证问题同时包含候选归属和主题相关性
                q_lower = q.lower()
                
                # 候选归属：必须包含 symbol 或 company_name
                candidate_related = (
                    symbol.lower() in q_lower or
                    candidate.company_name.lower() in q_lower
                )
                
                # 主题相关：至少一个主题关键词命中
                theme_related = any(kw.lower() in q_lower for kw in context.theme_keywords if kw)
                
                if candidate_related and theme_related:
                    candidate.falsification_questions.append(q)
                else:
                    if not candidate_related:
                        audit.errors.append(
                            f"synthesizer: question '{q[:50]}' not related to candidate {symbol}/{candidate.company_name}"
                        )
                    if not theme_related:
                        audit.errors.append(
                            f"synthesizer: question '{q[:50]}' not related to theme"
                        )
            
            # 2. 绑定 counter_evidence（验证 source ID）
            counter_list = rationale_data.get("counter_evidence", [])
            for ce in counter_list:
                if not isinstance(ce, dict):
                    continue
                
                description = ce.get("description", "")
                source_id = ce.get("source_record_id", "")
                
                # 验证 description 非空
                if not description or not description.strip():
                    audit.errors.append(
                        f"synthesizer: counter_evidence missing description for {symbol}"
                    )
                    continue
                
                if not source_id:
                    audit.errors.append(
                        f"synthesizer: counter_evidence missing source_record_id for {symbol}"
                    )
                    continue
                
                # 严格格式校验：tool:symbol:index
                parts = source_id.split(":")
                if len(parts) != 3:
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} malformed (expected format: tool:symbol:index)"
                    )
                    continue
                
                tool_name, source_symbol, index_str = parts
                
                # 验证 tool 在白名单中（discovered_player 不能作为反证来源）
                VALID_TOOLS = {"financials", "announcements", "sector"}
                if tool_name not in VALID_TOOLS:
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} has invalid tool '{tool_name}' (valid: {VALID_TOOLS})"
                    )
                    continue
                
                # 验证 symbol 严格等于当前候选 symbol
                if source_symbol != symbol:
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} belongs to {source_symbol}, not {symbol}"
                    )
                    continue
                
                # 验证 index 是非负整数
                try:
                    idx = int(index_str)
                    if idx < 0:
                        raise ValueError("negative index")
                except ValueError:
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} has invalid index '{index_str}' (must be non-negative integer)"
                    )
                    continue
                
                # 验证 source 存在
                source = context.sources_by_id.get(source_id)
                if not source:
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} not found in context"
                    )
                    continue
                
                # 验证 source_quality != weak
                if source.source_quality == "weak":
                    audit.errors.append(
                        f"synthesizer: counter_evidence source {source_id} is weak"
                    )
                    continue
                
                # 通过验证，绑定（使用结构化对象）
                from contracts.research import CounterEvidence
                candidate.counter_evidence.append(CounterEvidence(
                    description=description,
                    source_record_id=source_id
                ))
    
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
