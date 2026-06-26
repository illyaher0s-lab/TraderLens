"""
Backend App Contracts (Compatibility Layer)

This module re-exports contracts from the shared contracts package.
Maintained for backward compatibility during M2 migration.

New code should import from contracts.stable or contracts.draft directly.
This layer will be deprecated after all imports are migrated.

Migration status: COMPATIBILITY LAYER (M2)
Target: Remove after strategy_core migration complete
"""

from contracts.stable import (
    # Base
    ContractModel,
    
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
    # Research contracts
    EvidenceItem,
    EvidenceOutput,
    KillCriteria,
    KillCriteriaSnapshot,
    HypothesisDraft,
    
    # Execution tracking
    PositionPlan,
    InvalidCondition,
    TradePlan,
    ExecutionLog,
    ForwardCandidate,
    
    # Task abstractions
    BacktestTask,
    BacktestReport,
    AuditLog,
)

# Re-export all for backward compatibility
__all__ = [
    # Base
    "ContractModel",
    
    # Market data
    "StockIdentity",
    "DailyBar",
    "DailyStatus",
    
    # Strategy configuration
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
    
    # Execution artifacts
    "Signal",
    "Order",
    "OrderGenerationEvent",
    "OrderGenerationResult",
    "FrozenLot",
    "Trade",
    
    # Backtest output
    "DailyPortfolioValue",
    "RoundTrip",
    "BacktestMetrics",
    "PrototypeGateConfig",
    "PrototypeGateResult",
    "BacktestResult",
    
    # Research contracts
    "EvidenceItem",
    "EvidenceOutput",
    "KillCriteria",
    "KillCriteriaSnapshot",
    "HypothesisDraft",
    
    # Execution tracking
    "PositionPlan",
    "InvalidCondition",
    "TradePlan",
    "ExecutionLog",
    "ForwardCandidate",
    
    # Task abstractions
    "BacktestTask",
    "BacktestReport",
    "AuditLog",
]
