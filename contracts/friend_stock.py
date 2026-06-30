"""
Friend Stock Flow Contracts

Second complete business flow: friend recommendation → ticker verification
→ Serenity research → approval card → confirmed candidate pool.

Red lines:
R1. Flow only orchestrates, never reimplements research
R2. Ticker code only from tool queries, LLM cannot touch code filling
R3. User only sees approval card (continue/stop/downgrade) with counter-evidence
R4. confirmed_candidate_pool is forward-only and frozen on write
R5. Data fault only downgrades, never upgrades or backfills
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class FriendStockIntake(BaseModel, frozen=True, extra="forbid"):
    """Friend stock intake (raw input, preserved as-is)."""

    flow_id: str
    raw_company_input: str  # Friend's original words, preserved
    raw_code_input: Optional[str]  # If friend gave code directly
    source_note: str  # "朋友推荐，称产业链挖掘"等，原样
    created_at: datetime


class TickerVerificationResult(BaseModel, frozen=True, extra="forbid"):
    """
    Ticker verification result.
    
    Red line R2: Code only from tool, LLM cannot touch code.
    """

    flow_id: str
    status: Literal[
        "verified",  # 名↔码↔所 三者一致
        "ambiguous",  # 多个候选
        "not_found",  # 查无此股
        "mismatch",  # 名与码/所冲突
        "delisted",
        "suspended",
        "adapter_unsupported",  # stock_basic 源不可用
    ]
    resolved_ticker: Optional[str]  # 仅 verified 时非空，且来自工具
    resolved_name: Optional[str]
    exchange: Optional[str]  # SSE/SZSE
    board: Optional[str]  # 主板/科创板/创业板 (由代码段确定性判定)
    candidates: list[dict]  # ambiguous 时
    confidence: Literal["high", "medium", "low"]  # 由匹配规则给，非 LLM
    data_source: str  # 实际查询的源/方法名
    market_data_fault: Optional[str]  # 非 ok 时记 MarketDataFault 状态
    verified_at: datetime


class ConfirmedCandidatePool(BaseModel, frozen=True, extra="forbid"):
    """
    Confirmed candidate pool (forward-only, frozen on write).
    
    Red line R4: Write once, never modify.
    """

    pool_id: str
    flow_id: str
    ticker: str  # 来自 verified 结果
    name: str
    exchange: str
    confirmation_date: datetime  # 确认时点，冻结
    thesis_snapshot: str  # 论点快照 (LLM 起草、来源化)
    invalidation_rules: list[dict]  # 失效规则 (系统定，不让用户填)
    price_snapshot: dict  # {close, trade_date, source, fault_state}
    benchmark_snapshot: dict  # {index_code, close, trade_date, source}
    evidence_snapshot_ids: list[str]  # 指向已有证据 artifact
    counter_evidence_ids: list[str]
    source_provenance: dict  # 来源出处链
    approval_card_id: str
    approval_decision: str  # continue
    snapshot_hash: str  # over 冻结字段
    created_at: datetime

    @field_validator("approval_decision")
    @classmethod
    def decision_must_be_continue(cls, v: str) -> str:
        """Pool only created for 'continue' decision."""
        if v != "continue":
            raise ValueError("ConfirmedCandidatePool only for 'continue' decision")
        return v
