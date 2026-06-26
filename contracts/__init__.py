"""
TraderLens Contracts Package

Stability Tiers:
- stable: Used in M1/M2 production code, locked after M2
- draft: Defined but not implemented, subject to change
- reserved: Placeholder for future milestones

Schema Version: 1.0 (M2 freeze target)
"""

from contracts.stable import (
    # Market data
    StockIdentity,
    DailyBar,
    DailyStatus,
    
    # Strategy configuration
    DataRange,
    HypothesisSourceSnapshot,
    UniverseConfig,
    RuleGroup,
    RiskFilters,
    RebalanceConfig,
    FillHandling,
    FillModel,
    BenchmarkConfig,
    SampleSplit,
    BacktestConfig,
    AuditSnapshot,
    StrategyConfig,
    
    # Execution artifacts
    Signal,
    Order,
    OrderGenerationEvent,
    OrderGenerationResult,
    FrozenLot,
    Trade,
    
    # Backtest output
    DailyPortfolioValue,
    RoundTrip,
    BacktestMetrics,
    PrototypeGateConfig,
    PrototypeGateResult,
    BacktestResult,
)

from contracts.draft import (
    # Research contracts (not yet implemented)
    EvidenceItem,
    EvidenceOutput,
    KillCriteria,
    KillCriteriaSnapshot,
    HypothesisDraft,
    
    # Execution tracking (reserved for M3+)
    PositionPlan,
    InvalidCondition,
    TradePlan,
    ExecutionLog,
    ForwardCandidate,
    
    # Task abstractions (M2 boundary discussion)
    BacktestTask,
    BacktestReport,
    AuditLog,
)

__all__ = [
    # Stable contracts
    "StockIdentity",
    "DailyBar",
    "DailyStatus",
    "DataRange",
    "HypothesisSourceSnapshot",
    "UniverseConfig",
    "RuleGroup",
    "RiskFilters",
    "RebalanceConfig",
    "FillHandling",
    "FillModel",
    "BenchmarkConfig",
    "SampleSplit",
    "BacktestConfig",
    "AuditSnapshot",
    "StrategyConfig",
    "Signal",
    "Order",
    "OrderGenerationEvent",
    "OrderGenerationResult",
    "FrozenLot",
    "Trade",
    "DailyPortfolioValue",
    "RoundTrip",
    "BacktestMetrics",
    "PrototypeGateConfig",
    "PrototypeGateResult",
    "BacktestResult",
    
    # Draft contracts
    "EvidenceItem",
    "EvidenceOutput",
    "KillCriteria",
    "KillCriteriaSnapshot",
    "HypothesisDraft",
    "PositionPlan",
    "InvalidCondition",
    "TradePlan",
    "ExecutionLog",
    "ForwardCandidate",
    "BacktestTask",
    "BacktestReport",
    "AuditLog",
]

# Schema version for serialization
SCHEMA_VERSION = "1.0"
