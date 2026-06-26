"""
Stable Contracts - TraderLens Schema v1.0

These contracts are locked after M2 and used in production code.
Breaking changes require schema version bump and migration path.

Stability: STABLE (M2 freeze target)
Used by: strategy_core, backend/scripts, tests
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    """Base contract with strict validation."""
    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Market Data Contracts
# =============================================================================

class StockIdentity(ContractModel):
    """
    Stock identity and listing metadata.
    
    Stability: STABLE
    Used by: data sources, universe builder
    """
    symbol: str
    name: str
    exchange: Literal["SSE", "SZSE"]
    list_date: date
    delist_date: date | None = None
    current_status: Literal["listed", "delisted", "suspended_long_term", "delisting_risk"]
    industry: str
    sector: str


class DailyBar(ContractModel):
    """
    Daily OHLCV bar with adjustment factor.
    
    Stability: STABLE
    Used by: data sources, signal generation, price provider
    
    Constraints:
    - All prices >= 0
    - low <= open, close <= high
    - adj_factor > 0 (for forward-adjusted prices)
    """
    date: date
    symbol: str
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: int = Field(ge=0)
    amount: float = Field(ge=0)
    adj_factor: float = Field(gt=0)

    @model_validator(mode="after")
    def prices_are_ordered(self) -> "DailyBar":
        if self.low > self.high:
            raise ValueError("low cannot be greater than high")
        if not self.low <= self.open <= self.high:
            raise ValueError("open must be within low/high")
        if not self.low <= self.close <= self.high:
            raise ValueError("close must be within low/high")
        return self


class DailyStatus(ContractModel):
    """
    Daily trading status flags.
    
    Stability: STABLE
    Used by: fill simulator, signal generation
    
    A-share specific constraints:
    - Cannot be both limit_up and limit_down
    - ST stocks have restricted trading
    """
    date: date
    symbol: str
    is_st: bool
    is_suspended: bool
    is_limit_up: bool
    is_limit_down: bool
    suspend_reason: str | None = None
    st_type: Literal["ST", "*ST"] | None = None

    @model_validator(mode="after")
    def cannot_be_both_limit_up_and_down(self) -> "DailyStatus":
        if self.is_limit_up and self.is_limit_down:
            raise ValueError("a stock cannot be both limit-up and limit-down")
        return self


# =============================================================================
# Strategy Configuration Contracts
# =============================================================================

class DataRange(ContractModel):
    """Date range for data operations."""
    start: date
    end: date

    @model_validator(mode="after")
    def start_not_after_end(self) -> "DataRange":
        if self.start > self.end:
            raise ValueError("start cannot be after end")
        return self


class HypothesisSourceSnapshot(ContractModel):
    """
    Immutable snapshot of hypothesis generation source.
    
    Stability: STABLE (structure), draft (research integrations)
    
    Tracks:
    - Manual entry vs. Serenity-generated
    - Evidence pack IDs (reserved for Evidence Agent)
    - Data range used for research
    """
    source_type: Literal["serenity", "manual", "evidence", "user"]
    source_run_id: str
    evidence_pack_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    data_range_used_for_generation: DataRange
    llm_model: str | None = None
    prompt_version: str | None = None


class UniverseConfig(ContractModel):
    """
    Stock universe definition.
    
    Stability: STABLE (static_list), draft (sector_plus_filters)
    
    Supported types:
    - static_list: explicit symbol list
    - sector_plus_filters: reserved for sector-based universe (M3+)
    """
    type: Literal["static_list", "sector_plus_filters", "custom_list"]
    symbols: list[str] = Field(default_factory=list)
    sector: str | None = None
    chain_layer: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class RuleGroup(ContractModel):
    """
    Entry/exit rule group with logic operator.
    
    Stability: STABLE
    
    Logic:
    - AND: all rules must match
    - OR: any rule can match
    
    Rules are validated by validator.py for supported types.
    """
    logic: Literal["AND", "OR"]
    rules: list[dict[str, Any]] = Field(default_factory=list)
    market_state_filter: dict[str, Any] | None = None


class RiskFilters(ContractModel):
    """
    Position sizing and risk constraints.
    
    Stability: STABLE
    
    A-share specific:
    - Position ratios are percentage of available capital
    - Lot size enforced at order generation
    """
    max_position_per_stock: float = Field(gt=0, le=1)
    max_total_position: float = Field(gt=0, le=1)
    restrict_limit_up_buy: bool
    restrict_limit_down_sell: bool
    restrict_suspended: bool
    min_liquidity_for_trade: float = Field(ge=0)


class RebalanceConfig(ContractModel):
    """Rebalance frequency and check timing."""
    frequency: Literal["daily", "weekly", "monthly"]
    check_time: Literal["close"]


class FillHandling(ContractModel):
    """Fill rejection and deferral rules."""
    limit_up_buy: Literal["skip", "defer_next_day"]
    limit_down_sell: Literal["skip", "defer_next_day"]
    suspended: Literal["skip"]


class FillModel(ContractModel):
    """
    Fill simulation parameters.
    
    Stability: STABLE
    
    A-share constraints:
    - T+1 settlement (buy today, sell tomorrow)
    - Commission (both directions, min 5 RMB)
    - Stamp duty (sell only, 0.1%)
    - Lot size 100 shares
    """
    signal_to_execution: Literal["T+1"]
    execution_price: Literal["open", "vwap", "conservative"]
    commission: float = Field(ge=0)
    stamp_tax: float = Field(ge=0)
    slippage: float = Field(ge=0)
    lot_size: int = Field(gt=0)
    lot_rounding: Literal["floor"]
    handling: FillHandling


class BenchmarkConfig(ContractModel):
    """Benchmark for performance comparison."""
    type: Literal["index", "sector", "custom_universe"]
    code: str
    name: str


class SampleSplit(ContractModel):
    """
    In-sample / Out-of-sample split for backtest validation.
    
    Stability: STABLE
    
    OOS must start after IS ends (no overlap).
    """
    in_sample_end: date
    out_of_sample_start: date

    @model_validator(mode="after")
    def oos_starts_after_in_sample(self) -> "SampleSplit":
        if self.in_sample_end >= self.out_of_sample_start:
            raise ValueError("out_of_sample_start must be after in_sample_end")
        return self


class BacktestConfig(ContractModel):
    """
    Backtest execution parameters.
    
    Stability: STABLE
    
    Enforces:
    - Sample split falls within backtest range
    - Initial capital > 0
    """
    initial_capital: float = Field(gt=0)
    start_date: date
    end_date: date
    sample_split: SampleSplit
    benchmark: BenchmarkConfig
    data_source: str
    include_delisted: Literal["none", "partial", "full"]

    @model_validator(mode="after")
    def date_ranges_are_consistent(self) -> "BacktestConfig":
        if self.start_date > self.sample_split.in_sample_end:
            raise ValueError("in_sample_end must fall within backtest range")
        if self.sample_split.out_of_sample_start > self.end_date:
            raise ValueError("out_of_sample_start must fall within backtest range")
        return self


class AuditSnapshot(ContractModel):
    """Audit metadata for strategy configuration."""
    created_at: datetime
    created_by: str
    last_modified_at: datetime
    config_hash: str


class StrategyConfig(ContractModel):
    """
    Complete strategy configuration.
    
    Stability: STABLE (M2 freeze target)
    
    This is the primary input contract for strategy_core.
    All strategy execution derives from this configuration.
    """
    strategy_name: str
    version: str
    status: Literal["draft", "backtesting", "rejected", "prototype_passed", "execution_validating"]
    hypothesis_source_snapshot: HypothesisSourceSnapshot
    universe: UniverseConfig
    entry_conditions: RuleGroup
    exit_conditions: RuleGroup
    risk_filters: RiskFilters
    rebalance: RebalanceConfig
    fill_model: FillModel
    backtest_config: BacktestConfig
    prototype_gate: "PrototypeGateConfig" = Field(default_factory=lambda: PrototypeGateConfig(enabled=False))
    audit: AuditSnapshot


# =============================================================================
# Execution Artifacts
# =============================================================================

class Signal(ContractModel):
    """
    Trading signal generated by strategy_core.
    
    Stability: STABLE
    
    Signal types:
    - entry: buy signal
    - exit: sell signal
    - hold: no action
    """
    signal_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    signal_date: date
    signal_type: Literal["entry", "exit", "hold"]
    triggered_rules: list[str]
    generated_by: str = "strategy_core"
    audit_id: str


class Order(ContractModel):
    """
    Order intent with fill status.
    
    Stability: STABLE
    
    Status lifecycle:
    - planned: generated but not yet executed
    - filled: successfully executed
    - rejected: execution failed (with reason)
    
    Note: actual_execution_date is always set after fill (required for filled/rejected).
    """
    order_id: str
    signal_id: str
    signal_date: date
    intended_execution_date: date
    actual_execution_date: date | None = None  # Set by fill simulator
    symbol: str
    direction: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    reason: str
    strategy_version: str
    generated_by: str = "strategy_core"
    audit_id: str
    
    # Fill status fields
    status: Literal["planned", "filled", "rejected"] = "planned"
    actual_price: float | None = None
    actual_quantity: int | None = None
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def intended_execution_after_signal(self) -> "Order":
        if self.intended_execution_date <= self.signal_date:
            raise ValueError("intended_execution_date must be after signal_date")
        return self


class OrderGenerationEvent(ContractModel):
    """
    Audit record for order generation process.
    
    Stability: STABLE
    
    Not a real order; used for reporting and debugging.
    Records pre-checks, T+1 violations, conflicts, and rejections.
    """
    event_type: Literal[
        "no_position_to_exit",
        "t1_frozen",
        "partial_exit_due_to_t1_freeze",
        "signal_conflict",
        "zero_quantity",
    ]
    symbol: str
    signal_id: str | None = None
    intended_execution_date: date
    reason: str
    requested_quantity: int | None = None
    generated_quantity: int | None = None
    sellable_quantity: int | None = None
    total_quantity: int | None = None


class OrderGenerationResult(ContractModel):
    """
    Result of order generation including valid orders and audit events.
    
    Stability: STABLE
    """
    valid_orders: list[Order]
    events: list[OrderGenerationEvent]


class FrozenLot(ContractModel):
    """
    A frozen lot representing shares bought that cannot be sold until unlock_date.
    
    Stability: STABLE
    
    T+1 rule: shares bought on day T can only be sold on day T+1 (next trading day).
    """
    quantity: int = Field(gt=0, description="Frozen quantity")
    unlock_date: date = Field(description="Trading day when this lot becomes sellable")


class Trade(ContractModel):
    """
    Record of an executed trade with transaction cost breakdown.
    
    Stability: STABLE
    
    M2 decision: trade_date is always set (required), not optional.
    If fill simulator rejects, no Trade is created (rejection goes to Order.rejection_reason).
    """
    trade_id: str
    order_id: str
    symbol: str
    direction: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)
    trade_date: date  # M2: always set, not optional
    
    # Transaction cost breakdown
    gross_amount: float = Field(gt=0)  # price * quantity
    commission: float = Field(ge=0)
    stamp_duty: float = Field(ge=0)
    transfer_fee: float = Field(ge=0, default=0.0)
    total_fee: float = Field(ge=0)  # commission + stamp_duty + transfer_fee
    
    # Net cash flow (negative for buy, positive for sell)
    net_cash_flow: float
    
    # Deprecated: kept for backward compatibility
    cost: float  # alias for net_cash_flow for now


# =============================================================================
# Backtest Output Contracts
# =============================================================================

class DailyPortfolioValue(ContractModel):
    """
    Daily snapshot of portfolio value.
    
    Stability: STABLE
    """
    date: date
    cash: float = Field(ge=0)
    market_value: float = Field(ge=0)
    total_value: float = Field(ge=0)


class RoundTrip(ContractModel):
    """
    A completed trading round-trip (buy → sell) with FIFO lot matching.
    
    Stability: STABLE
    
    One sell trade may generate multiple round-trips if it closes multiple buy lots.
    All quantities refer to the matched portion, not the original trade quantities.
    """
    round_trip_id: str
    symbol: str
    
    # Buy leg (matched portion)
    buy_trade_id: str
    buy_date: date
    buy_price: float
    buy_trade_quantity: int  # Original buy trade quantity
    matched_quantity: int  # Quantity matched in this round-trip
    buy_cost: float  # Cost for matched_quantity (including proportional commission)
    
    # Sell leg (matched portion)
    sell_trade_id: str
    sell_date: date
    sell_price: float
    sell_trade_quantity: int  # Original sell trade quantity
    sell_proceeds: float  # Net proceeds for matched_quantity (after proportional fees)
    
    # PnL
    realized_pnl: float  # sell_proceeds - buy_cost
    holding_days: int  # sell_date - buy_date


class BacktestMetrics(ContractModel):
    """
    Performance metrics calculated from backtest.
    
    Stability: STABLE
    """
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    filled_orders: int
    completed_round_trips: int = 0
    
    # Round-trip based metrics (closed lot statistics)
    closed_lot_win_rate: float = 0.0  # winning_matched_segments / completed_matched_segments
    profit_factor: float = 0.0  # total_profit / abs(total_loss)
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Warnings
    unmatched_sells: int = 0  # Count of sell trades without matching buy lots


class PrototypeGateConfig(ContractModel):
    """
    Prototype Gate configuration for backtest validation.
    
    Stability: STABLE
    
    Note: This is prototype-level validation, NOT production admission.
    Gate only provides recommendations; does not modify strategy.status.
    """
    enabled: bool = False  # Default disabled, explicit opt-in required
    
    # Full-period thresholds
    min_total_return: float | None = Field(None, description="Minimum total return (e.g., 0.05 = 5%)")
    max_drawdown: float | None = Field(None, description="Maximum drawdown (negative, e.g., -0.15 = -15%)")
    min_sharpe_ratio: float | None = Field(None, description="Minimum Sharpe ratio")
    min_trades: int | None = Field(None, ge=0, description="Minimum number of filled trades")
    
    # OOS-specific thresholds
    min_oos_return: float | None = Field(None, description="Minimum OOS return")
    max_oos_drawdown: float | None = Field(None, description="Maximum OOS drawdown")
    min_oos_trades: int | None = Field(None, ge=0, description="Minimum OOS filled trades")
    
    # Round-trip thresholds
    min_completed_round_trips: int | None = Field(None, ge=0, description="Minimum completed round-trips (FIFO matched)")
    min_closed_lot_win_rate: float | None = Field(None, ge=0, le=1, description="Minimum closed lot win rate (0-1, disabled by default)")
    min_profit_factor: float | None = Field(None, ge=0, description="Minimum profit factor (disabled by default)")


class PrototypeGateResult(ContractModel):
    """
    Prototype gate evaluation result.
    
    Stability: STABLE
    
    IMPORTANT: This is a recommendation, not an automatic status change.
    Strategy.status transitions must go through human_required_sync.
    """
    status: Literal["not_evaluated", "passed", "needs_review", "failed"]
    failed_checks: list[str] = Field(default_factory=list)
    warning_checks: list[str] = Field(default_factory=list)
    recommendation: Literal["reject", "review", "candidate_for_prototype_passed"]
    
    # Metrics snapshots
    metrics_full: BacktestMetrics
    metrics_is: BacktestMetrics | None = None
    metrics_oos: BacktestMetrics | None = None
    
    # OOS segment info
    oos_split_date: date | None = None
    oos_start_value: float | None = None
    oos_end_value: float | None = None


class BacktestResult(ContractModel):
    """
    Complete backtest result with trades, daily values, and warnings.
    
    Stability: STABLE (M2 freeze target)
    
    This is the primary output contract for strategy_core backtest engine.
    All exports and reports derive from this result.
    """
    strategy_id: str
    strategy_version: str
    initial_capital: float = Field(gt=0)
    final_capital: float = Field(ge=0)
    total_return: float
    trades: list[Trade]
    daily_portfolio_values: list[DailyPortfolioValue]
    rejected_orders: list[Order]
    round_trips: list[RoundTrip] = Field(default_factory=list)
    prototype_gate_result: PrototypeGateResult | None = None
    order_generation_events: list[OrderGenerationEvent] = Field(default_factory=list)
    entry_signal_count: int = Field(default=0, ge=0)
    exit_signal_count: int = Field(default=0, ge=0)
    buy_order_count: int = Field(default=0, ge=0)
    sell_order_count: int = Field(default=0, ge=0)
    buy_fill_count: int = Field(default=0, ge=0)
    sell_fill_count: int = Field(default=0, ge=0)
    exit_rejected_count: int = Field(default=0, ge=0)
    completed_round_trips: int = Field(default=0, ge=0)
    exit_triggered_rules: list[str] = Field(default_factory=list)
    t1_blocked_exit_count: int = Field(default=0, ge=0)
    partial_exit_due_to_t1_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=lambda: [
        "Transaction costs included: commission (default 0.03%, min 5 RMB) and stamp duty (0.1%, sell only).",
        "Transfer fee not included (negligible impact, default 0%).",
        "Slippage not simulated; fill price is execution_date open price."
    ])
