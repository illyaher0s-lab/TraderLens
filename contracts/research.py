"""
Research module contracts.

These contracts define:
- ThemeInput: research theme with source type, mode, status, and board_version
- CandidateStock: candidate stock with hard filter flags and status
- EvidenceItem: evidence with expiry tracking
- ConflictItem: conflicting evidence record
- AgentHarnessConfig: agent harness provider and configuration
- SerenityOutput: structured Serenity analysis output
- EvidenceOutput: structured Evidence analysis output with kill_criteria_hash
- ProposedAction: proposed action awaiting human review
- ConversationMessage: conversation message with linked proposed actions
- ConversationTurnResult: conversation turn with proposed actions
- AppliedAction: applied or rejected action audit record
- ConfirmedCandidate: confirmed candidate with forward_only=True and locked snapshots
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


ThemeSourceType = Literal["manual_theme", "manual_stock", "market_scan"]
ResearchMode = Literal["quick_scan", "standard", "deep_research"]
ThemeStatus = Literal["draft", "serenity_done", "evidence_done", "confirmed", "archived"]
CandidateStatus = Literal["raw", "shortlisted", "blocked", "needs_evidence", "confirmed", "rejected"]
EvidenceLevel = Literal["strong", "medium", "weak", "unknown", "falsified", "conflicted"]
SourceType = Literal["announcement", "financial_report", "prospectus", "interaction_platform", "news", "social_media", "unknown"]
SourceQuality = Literal["first_hand", "second_hand", "weak"]


class CounterEvidence(BaseModel):
    """结构化反证。
    
    description: 反证描述
    source_record_id: 来源 ID，必须存在于 context 且属于该候选
    """
    description: str
    source_record_id: str


ConversationRole = Literal["user", "agent", "system"]
ResearchAction = Literal[
    "create_theme",
    "add_candidate",
    "propose_confirm",
    "propose_reject",
    "reopen_to_serenity",
    "reopen_to_evidence",
]


class ThemeInput(BaseModel):
    """
    Research theme input.
    
    Tracks source type (manual_theme, manual_stock, market_scan),
    research mode, status, and board_version for optimistic concurrency control.
    
    New themes start with board_version=0.
    board_version increments by 1 after each successful reducer-applied state mutation.
    """
    theme_id: str
    theme_name: str
    background: str
    source_type: ThemeSourceType
    research_mode: ResearchMode = "standard"
    urgency: Literal["normal", "urgent"] = "normal"
    notes: str = ""
    status: ThemeStatus = "draft"
    board_version: int = 0
    research_output: dict | None = None
    created_at: datetime
    updated_at: datetime


class CandidateStock(BaseModel):
    """
    Candidate stock for a research theme.
    
    Carries hard_filter_flags for blocked candidates.
    Supports manual_stock, manual_theme, and market_scan source types.
    
    Research metadata (from Serenity):
    - supporting_source_ids: 支持该候选的来源 IDs
    - red_team_findings: red-team 发现的问题或反证
    - unresolved_gaps: 未解决的证据缺口
    """
    candidate_id: str
    theme_id: str
    symbol: str
    company_name: str | None = None
    verification_id: str | None = None
    source_type: ThemeSourceType
    chain_layer: str | None = None
    match_reason: str
    match_confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    status: CandidateStatus = "raw"
    hard_filter_flags: list[str] = Field(default_factory=list)
    override_reason: str | None = None
    created_at: datetime
    
    # Research metadata (from Serenity two-phase)
    supporting_source_ids: list[str] = Field(default_factory=list)
    
    # Red-team 结果（三类独立）
    counter_evidence: list[CounterEvidence] = Field(default_factory=list)  # 结构化反证
    falsification_questions: list[str] = Field(default_factory=list)  # 待验证问题（来自 LLM）
    data_gaps: list[str] = Field(default_factory=list)  # 数据缺口
    
    # 向后兼容字段（不作为新的事实来源）
    red_team_findings: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """
    Evidence item with source identity, traceable record reference, and expiry.

    Every claim must be traceable to a specific source and quality tier.
    source_record_id links this evidence to a specific row in a DataToolResult.
    Supports expiry_days or valid_until for time-bounded evidence.
    Carries supports / falsifies / conflicts to link to specific theses.
    """
    source: str
    source_type: SourceType = "unknown"
    source_quality: SourceQuality = "weak"
    source_record_id: str | None = None
    description: str
    published_at: date | None = None
    retrieved_at: datetime
    expiry_days: int | None = None
    valid_until: date | None = None
    supports: list[str] = Field(default_factory=list)
    falsifies: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ConflictItem(BaseModel):
    """
    Conflicting evidence record.
    
    Records conflicts between two sources.
    """
    source_a: str
    source_b: str
    conflict_type: str
    description: str


class AgentHarnessConfig(BaseModel):
    """
    Agent harness configuration.
    
    Identifies execution engine, LLM provider, tool whitelist, budget, and replayability.
    
    Fields:
    - execution_engine: "stub" (deterministic template) or "two_phase" (Planner → Executor → Synthesizer)
    - llm_provider: actual LLM provider name (e.g., "openai", "anthropic", "fake-provider")
    - provider: DEPRECATED - use execution_engine instead. Kept for backward compatibility.
    """
    execution_engine: Literal["stub", "two_phase"] = "stub"
    llm_provider: str = "unknown"
    provider: Literal["stub", "langgraph"] | None = None  # DEPRECATED - use execution_engine
    tool_whitelist: list[str]
    max_steps: int
    token_budget: int
    replayable: bool = True


class SerenityOutput(BaseModel):
    """
    Structured Serenity analysis output.
    
    Includes value chain layers, bottleneck layers, candidate pools,
    hypothesis draft, evidence gaps, and harness metadata.
    """
    theme_id: str
    demand_driver: str
    value_chain_layers: list[dict]
    suspected_bottleneck_layers: list[dict]
    candidate_pool_raw: list[CandidateStock]
    candidate_shortlist: list[CandidateStock]
    hypothesis_draft: list[dict]
    evidence_gaps: list[str]
    harness: AgentHarnessConfig
    created_at: datetime
    research_sources: list[dict] = Field(default_factory=list)
    candidate_verdicts: dict[str, dict] = Field(default_factory=dict)
    serenity_stage_trace: list[dict] = Field(default_factory=list)
    serenity_call_diagnostics: list[dict] = Field(default_factory=list)


class EvidenceOutput(BaseModel):
    """
    Structured Evidence analysis output.
    
    Requires kill_criteria_hash for contract stability.
    Supports supporting, falsifying, and conflicting evidence.
    Tracks blocking issues, evidence gaps, and tool trace.
    """
    candidate_id: str
    kill_criteria_hash: str
    evidence_level: EvidenceLevel
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    falsifying_evidence: list[EvidenceItem] = Field(default_factory=list)
    conflict_items: list[ConflictItem] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    created_at: datetime


class DataToolResult(BaseModel):
    """
    Unified return contract for all data tools.

    All data tools (get_financials, get_announcements, get_sector_and_peers, etc.)
    return this same structure. Missing data must NOT be filled with defaults or
    synthesized values — gaps and errors are recorded explicitly.

    LLM may only read and summarise these results; it must not fabricate or fill
    data that the tool did not return.
    """
    tool_name: str
    raw_data: list[dict] = Field(default_factory=list)
    source: str
    retrieved_at: datetime
    gaps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EvidenceDataPacket(BaseModel):
    """
    Immutable input for the Evidence Agent LLM.

    Aggregates the three data tool results into a single read-only packet.
    LLM may read this but must not override any tool-output fields.
    After LLM generation, source_type/source_quality are re-bound deterministically.
    """
    symbol: str
    snapshot_date: str | None = None
    verification_id: str | None = None
    financials: DataToolResult | None = None
    announcements: DataToolResult | None = None
    sector_and_peers: DataToolResult | None = None
    tool_gaps: list[str] = Field(default_factory=list)
    tool_errors: list[str] = Field(default_factory=list)
    created_at: datetime

    def compute_input_hash(self) -> str:
        """Deterministic hash of the input packet for audit."""
        import hashlib
        payload = {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date,
            "verification_id": self.verification_id,
            "tool_gaps": self.tool_gaps,
            "tool_errors": self.tool_errors,
        }
        if self.financials:
            payload["financials_hash"] = str(len(self.financials.raw_data))
        if self.announcements:
            payload["announcements_hash"] = str(len(self.announcements.raw_data))
        if self.sector_and_peers:
            payload["sector_and_peers_hash"] = str(len(self.sector_and_peers.raw_data))
        raw = str(payload).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class EvidenceAgentAudit(BaseModel):
    """Audit trail for Evidence Agent LLM execution."""
    model: str = "unknown"
    provider: str = "unknown"
    input_hash: str = ""
    tool_calls: list[dict] = Field(default_factory=list)
    llm_structured_output: dict | None = None
    token_usage: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    extraction_time_ms: float = 0.0


class ProposedAction(BaseModel):
    """
    Proposed action awaiting human review.
    
    Proposed != applied. Actions must go through reducer validation.
    Carries action_id for idempotency and board_version for stale detection.
    """
    action_id: str
    action: ResearchAction
    target_id: str
    args: dict
    rationale: str
    proposed_by: Literal["agent", "user"]
    proposed_at: datetime
    expires_at: datetime | None = None
    board_version: int | None = None


class ConversationMessage(BaseModel):
    """
    Conversation message.
    
    Can link to proposed action IDs without applying them.
    Conversation messages do not mutate board state.
    """
    message_id: str
    theme_id: str
    role: ConversationRole
    content: str
    linked_proposed_action_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class ConversationTurnResult(BaseModel):
    """
    Conversation turn result.
    
    Can return zero or more proposed actions.
    Agent explains, user decides, reducer validates and applies.
    """
    user_message: ConversationMessage
    agent_message: ConversationMessage
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


class AppliedAction(BaseModel):
    """
    Applied or rejected action audit record.
    
    Records proposed action, applied status, actor, reason, and timestamp.
    """
    action_id: str
    proposed_action: ProposedAction
    applied: bool
    actor_reason: str | None = None
    rejection_reason: str | None = None
    applied_by: str | None = None
    applied_at: datetime


class TickerVerificationRecord(BaseModel):
    """
    Ticker verification record.
    
    Persisted to prevent LLM from fabricating company names or bypassing verification.
    """
    verification_id: str
    symbol: str
    company_name: str
    exchange: str
    status: Literal["listed", "delisted", "suspended", "acquired", "private", "unknown"]
    confidence: Literal["high", "medium", "low"]
    source: str
    notes: str
    verified_at: datetime
    expires_at: datetime  # Verification expires after 24 hours


class ConfirmedCandidate(BaseModel):
    """
    Confirmed candidate in the forward-only pool.
    
    forward_only=True cannot be changed.
    Locks thesis, invalidation rules, price snapshot, benchmark snapshot,
    and evidence_snapshot_ids at confirmation time.
    Requires at least one valid evidence snapshot to confirm.
    pool_snapshot_date tracks when this candidate was confirmed.
    """
    confirmed_id: str
    theme_id: str
    candidate_id: str
    source_serenity_run_id: str | None = None
    source_evidence_run_id: str | None = None
    symbol: str
    company_name: str
    verification_id: str | None = None
    chain_layer: str | None = None
    thesis_snapshot: str
    invalidation_rules: list[dict] = Field(default_factory=list)
    price_snapshot: dict
    benchmark_snapshot: dict
    confirmation_reason: str
    evidence_level: EvidenceLevel
    evidence_snapshot_ids: list[str] = Field(default_factory=list)
    primary_evidence_snapshot_id: str | None = None
    confirmed_by: str
    confirmed_at: datetime
    pool_snapshot_date: date
    forward_only: Literal[True] = True


class EvidenceSnapshot(BaseModel):
    """
    Immutable Evidence snapshot.

    Every Evidence run generates a unique snapshot record.
    Snapshots are append-only — never updated or overwritten.
    Stores the full EvidenceOutput, input hashes, and audit trail.
    """
    snapshot_id: str
    candidate_id: str
    verification_id: str | None = None
    snapshot_date: str | None = None
    symbol: str
    evidence_output: dict      # serialised EvidenceOutput
    packet_input_hash: str = ""
    tool_result_hash: str = ""
    audit_id: str | None = None  # reference to EvidenceAgentAudit
    created_at: datetime


class ResearchSource(BaseModel):
    """
    Unified research source record for Serenity tool chain.

    Every retrieved source — whether from a data tool, web search,
    or structured database — conforms to this contract.

    Missing source_type/source_quality = "unknown"/"weak" (conservative default).
    
    Theme relevance fields (computed by deterministic executor, NOT by LLM):
    - theme_keywords_matched: keywords from theme that matched this source
    - theme_relevance_basis: where the match occurred (title/summary/industry)
    """
    source_record_id: str
    source_type: SourceType = "unknown"
    source_quality: SourceQuality = "weak"
    title: str = ""
    published_at: date | None = None
    retrieved_at: datetime
    summary: str = ""           # raw excerpt or structured fact summary
    source_url: str = ""        # announcement URL, article link, etc.
    announcement_code: str = "" # Tushare ann_type or similar code
    gaps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    
    # Theme relevance (deterministic matching only)
    theme_keywords_matched: list[str] = Field(default_factory=list)
    theme_relevance_basis: str | None = None  # "title_match" | "summary_match" | "industry_match"


class SerenityToolResult(BaseModel):
    """
    Unified return wrapper for Serenity tool results.

    Each tool returns structured records and metadata.
    Empty results always record a gap.
    """
    tool_name: str
    records: list[ResearchSource] = Field(default_factory=list)
    total_found: int = 0
    gaps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retrieved_at: datetime
