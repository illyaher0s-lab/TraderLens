"""
Serenity stub runner.

Deterministic Serenity runner implementing the same interface future real agent will use.

Returns SerenityOutput with:
- demand driver
- value chain layers
- suspected bottleneck layers
- candidate raw pool
- candidate shortlist
- hypothesis draft
- evidence gaps
- harness config

Harness config includes:
- provider: 'stub' (future: 'langgraph')
- tool whitelist
- max steps
- token budget
- replayable flag

This implementation uses rule-based templates. It does not pretend to be completed LLM research.

LangGraph adapter boundary:
- SerenityStubRunner and future LangGraphSerenityRunner return the same SerenityOutput
- No runner may write DB state directly
- Any action suggested by a runner must be returned as ProposedAction
"""

from datetime import datetime
from contracts.research import (
    ThemeInput,
    CandidateStock,
    SerenityOutput,
    AgentHarnessConfig,
)


class SerenityRunner:
    """Serenity runner interface."""

    def run(self, theme: ThemeInput, manual_candidates: list[CandidateStock]) -> SerenityOutput:
        """
        Run Serenity analysis on a theme.
        
        Args:
            theme: Research theme
            manual_candidates: User-provided manual candidates
        
        Returns:
            Structured Serenity output
        """
        raise NotImplementedError


class SerenityStubRunner(SerenityRunner):
    """
    Deterministic Serenity stub runner.
    
    Uses rule-based templates to generate structured output.
    Future LangGraphSerenityRunner will replace this with real LLM analysis.
    """

    def run(self, theme: ThemeInput, manual_candidates: list[CandidateStock]) -> SerenityOutput:
        """
        Run stub Serenity analysis.
        
        Args:
            theme: Research theme
            manual_candidates: User-provided manual candidates
        
        Returns:
            Structured Serenity output with stub data
        """
        now = datetime.now()

        # Determine shortlist limit by research mode
        shortlist_limits = {
            "quick_scan": 3,
            "standard": 5,
            "deep_research": 10,
        }
        shortlist_limit = shortlist_limits.get(theme.research_mode, 5)

        # Stub demand driver
        demand_driver = f"基于主题「{theme.theme_name}」的需求驱动分析（stub）"

        # Stub value chain layers
        value_chain_layers = [
            {"layer": "上游原材料", "description": "锂矿、钴矿等"},
            {"layer": "中游制造", "description": "电池制造、电机制造"},
            {"layer": "下游应用", "description": "新能源汽车、储能系统"},
        ]

        # Stub suspected bottleneck layers
        suspected_bottleneck_layers = [
            {"layer": "中游制造", "reason": "产能扩张速度决定行业增长上限"},
        ]

        # Build raw candidate pool (preserve manual candidates)
        candidate_pool_raw = list(manual_candidates)

        # Stub: add some generated candidates
        stub_candidates = self._generate_stub_candidates(theme, len(manual_candidates))
        candidate_pool_raw.extend(stub_candidates)

        # Build shortlist (limit by research mode)
        candidate_shortlist = []
        for candidate in candidate_pool_raw[:shortlist_limit]:
            shortlisted = CandidateStock(
                candidate_id=candidate.candidate_id,
                theme_id=candidate.theme_id,
                symbol=candidate.symbol,
                company_name=candidate.company_name,
                source_type=candidate.source_type,
                chain_layer=candidate.chain_layer,
                match_reason=candidate.match_reason,
                match_confidence="medium",
                status="shortlisted",
                hard_filter_flags=candidate.hard_filter_flags,
                override_reason=candidate.override_reason,
                created_at=candidate.created_at,
            )
            candidate_shortlist.append(shortlisted)

        # Stub hypothesis draft
        hypothesis_draft = [
            {
                "hypothesis": "产业链中游制造环节是关键瓶颈",
                "rationale": "需求快速增长，产能扩张需要时间",
                "confidence": "medium",
            },
            {
                "hypothesis": "龙头企业具有规模优势和技术壁垒",
                "rationale": "资本密集型行业，先发优势明显",
                "confidence": "high",
            },
        ]

        # Stub evidence gaps
        evidence_gaps = [
            "需要验证产能扩张计划的可行性",
            "需要确认龙头企业的市场份额数据",
            "需要评估原材料价格波动风险",
        ]

        # Harness config
        harness = AgentHarnessConfig(
            provider="stub",
            tool_whitelist=["read_theme", "list_manual_candidates", "template_analysis"],
            max_steps=10,
            token_budget=5000,
            replayable=True,
        )

        return SerenityOutput(
            theme_id=theme.theme_id,
            demand_driver=demand_driver,
            value_chain_layers=value_chain_layers,
            suspected_bottleneck_layers=suspected_bottleneck_layers,
            candidate_pool_raw=candidate_pool_raw,
            candidate_shortlist=candidate_shortlist,
            hypothesis_draft=hypothesis_draft,
            evidence_gaps=evidence_gaps,
            harness=harness,
            created_at=now,
        )

    def _generate_stub_candidates(
        self, theme: ThemeInput, manual_count: int
    ) -> list[CandidateStock]:
        """
        Generate stub candidates for testing.
        
        Args:
            theme: Research theme
            manual_count: Number of manual candidates already added
        
        Returns:
            List of stub candidates
        """
        now = datetime.now()

        # Stub candidate templates
        stub_templates = [
            {"symbol": "300750.SZ", "company_name": "宁德时代", "chain_layer": "中游制造"},
            {"symbol": "002594.SZ", "company_name": "比亚迪", "chain_layer": "下游应用"},
            {"symbol": "603799.SH", "company_name": "华友钴业", "chain_layer": "上游原材料"},
            {"symbol": "002460.SZ", "company_name": "赣锋锂业", "chain_layer": "上游原材料"},
            {"symbol": "688005.SH", "company_name": "容百科技", "chain_layer": "中游制造"},
        ]

        candidates = []
        for idx, template in enumerate(stub_templates):
            candidate_id = f"serenity_cand_{manual_count + idx + 1}"
            candidate = CandidateStock(
                candidate_id=candidate_id,
                theme_id=theme.theme_id,
                symbol=template["symbol"],
                company_name=template["company_name"],
                source_type="market_scan",
                chain_layer=template["chain_layer"],
                match_reason="Serenity 产业链分析匹配（stub）",
                match_confidence="medium",
                status="raw",
                hard_filter_flags=[],
                override_reason=None,
                created_at=now,
            )
            candidates.append(candidate)

        return candidates
