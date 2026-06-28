#!/usr/bin/env python3
"""
Generate Planned Signals - M4 Phase 2

Generate PlannedSignal JSON from frozen Tushare snapshot + strategy YAML.

Usage:
    python backend/scripts/generate_planned_signals.py \
        --snapshot-dir data/tushare_snapshots \
        --strategy examples/strategies/live_strategy.yaml \
        --signal-date 2023-12-29 \
        --output signals/2023-12-29.json

Hard Constraints:
- No strategy_core modification
- No backtest_engine modification
- No DataSource Protocol modification
- No new signal rules
- No Tushare API calls
- No network access
- Only read frozen snapshots
- All signals bind to snapshot_hash + strategy_version
- Deterministic signal_id (sha256 hash, no uuid4)
- planned_action: enter/exit (not 买入/卖出建议)
- review_status: pending (default)
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_data_source import TushareDataSource
from backend.db.strategy import StrategyDB
from backend.services.c_admission_gate import CAdmissionGate
from contracts.signal_board import PlannedSignal
from contracts.stable import Signal, StrategyConfig
from strategy_core.signals import generate_signals
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.universe_builder import build_universe


def compute_deterministic_signal_id(
    strategy_id: str,
    strategy_version: str,
    snapshot_hash: str,
    signal_date: date,
    intended_execution_date: date,
    symbol: str,
    direction: str,
    trigger_reason: str,
) -> str:
    """
    Compute deterministic signal_id using sha256 hash.
    
    Same inputs → same signal_id (enables upsert and reproducibility).
    
    Args:
        strategy_id: Strategy identifier
        strategy_version: Strategy version
        snapshot_hash: Data snapshot hash
        signal_date: Signal generation date
        intended_execution_date: Next trading day (T+1)
        symbol: Stock symbol
        direction: buy or sell
        trigger_reason: Human-readable explanation
    
    Returns:
        64-character hex string (sha256 hash)
    """
    components = [
        strategy_id,
        strategy_version,
        snapshot_hash,
        signal_date.isoformat(),
        intended_execution_date.isoformat(),
        symbol,
        direction,
        trigger_reason,
    ]
    
    # Join with separator to avoid collision (e.g., "ab" + "c" vs "a" + "bc")
    composite = "|".join(components)
    
    # SHA256 hash
    hash_bytes = hashlib.sha256(composite.encode("utf-8")).digest()
    
    # Return hex string (64 chars)
    return hash_bytes.hex()


def map_direction_to_planned_action(direction: str) -> str:
    """
    Map signal direction to planned_action for UI display.
    
    Args:
        direction: "buy" or "sell" (data layer)
    
    Returns:
        "enter" or "exit" (UI display: 入场/离场)
    
    Raises:
        ValueError: If direction is invalid
    """
    if direction == "buy":
        return "enter"
    elif direction == "sell":
        return "exit"
    else:
        raise ValueError(f"Invalid direction: {direction}. Expected 'buy' or 'sell'.")


def convert_signal_to_planned_signal(
    signal: Signal,
    snapshot_hash: str,
    signal_date: date,
    intended_execution_date: date,
    data_source: TushareDataSource,
    strategy_config: StrategyConfig,
) -> PlannedSignal:
    """
    Convert strategy_core Signal to PlannedSignal.
    
    Args:
        signal: Signal from strategy_core.signals.generate_signals()
        snapshot_hash: Data snapshot hash (for reproducibility)
        signal_date: When signal was generated (EOD)
        intended_execution_date: Next trading day (T+1)
        data_source: Data source (to fetch current_price)
        strategy_config: Strategy configuration (for metadata)
    
    Returns:
        PlannedSignal ready for Signal Board
    
    Raises:
        ValueError: If signal has invalid fields or missing trigger_reason
    """
    # Map signal_type to direction
    if signal.signal_type == "entry":
        direction = "buy"
    elif signal.signal_type == "exit":
        direction = "sell"
    else:
        raise ValueError(f"Unsupported signal_type: {signal.signal_type}. Expected 'entry' or 'exit'.")
    
    # Map direction to planned_action
    planned_action = map_direction_to_planned_action(direction)
    
    # Build trigger_reason from triggered_rules
    if not signal.triggered_rules:
        raise ValueError(
            f"Signal has no triggered_rules: {signal.signal_id}. "
            "Cannot generate trigger_reason. Fail loud: signals must have explanations."
        )
    
    trigger_reason = " AND ".join(signal.triggered_rules)
    
    # Fetch current_price (close price on signal_date)
    try:
        current_price = data_source.get_price(signal.symbol, signal_date)
    except KeyError:
        # Symbol not available on signal_date (e.g., delisted, suspended)
        current_price = None
    
    # Compute deterministic signal_id
    signal_id = compute_deterministic_signal_id(
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        snapshot_hash=snapshot_hash,
        signal_date=signal_date,
        intended_execution_date=intended_execution_date,
        symbol=signal.symbol,
        direction=direction,
        trigger_reason=trigger_reason,
    )
    
    # Build metadata
    metadata = {
        "source_signal_id": signal.signal_id,
        "source_signal_type": signal.signal_type,
        "audit_id": signal.audit_id,
        "strategy_params": {
            "entry_logic": strategy_config.entry_conditions.logic,
            "entry_rules_count": len(strategy_config.entry_conditions.rules),
            "exit_logic": strategy_config.exit_conditions.logic,
            "exit_rules_count": len(strategy_config.exit_conditions.rules),
        },
        "generation_inputs": {
            "snapshot_hash": snapshot_hash,
            "signal_date": signal_date.isoformat(),
            "intended_execution_date": intended_execution_date.isoformat(),
        },
    }
    
    # Create PlannedSignal
    return PlannedSignal(
        signal_id=signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        snapshot_hash=snapshot_hash,
        signal_date=signal_date,
        intended_execution_date=intended_execution_date,
        symbol=signal.symbol,
        direction=direction,
        planned_action=planned_action,
        quantity=None,  # M4 Phase 2: no position sizing yet
        trigger_reason=trigger_reason,
        review_status="pending",
        reviewed_at=None,
        reviewed_by=None,
        rejection_reason=None,
        current_price=current_price,
        position_before=None,  # M4 Phase 2: no real positions yet
        created_at=datetime.utcnow(),
        metadata=metadata,
    )


def load_strategy_config(strategy_path: Path) -> StrategyConfig:
    """
    Load and parse strategy YAML file.
    
    Args:
        strategy_path: Path to strategy YAML file
    
    Returns:
        Parsed StrategyConfig
    
    Raises:
        FileNotFoundError: If strategy file not found
        ValueError: If strategy YAML is invalid
    """
    if not strategy_path.exists():
        raise FileNotFoundError(f"Strategy file not found: {strategy_path}")
    
    with open(strategy_path, "r", encoding="utf-8") as f:
        strategy_dict = yaml.safe_load(f)
    
    # Parse into StrategyConfig (Pydantic validation)
    try:
        config = StrategyConfig(**strategy_dict)
    except Exception as e:
        raise ValueError(f"Invalid strategy YAML: {strategy_path}\n{e}") from e
    
    return config


def generate_planned_signals_from_snapshot(
    snapshot_dir: Path,
    strategy_config: StrategyConfig,
    signal_date: date,
    strategy_revision_id: str | None = None,
    strategy_db_path: str | None = None,
) -> list[PlannedSignal]:
    """
    Generate PlannedSignals from frozen snapshot + strategy config.

    Args:
        snapshot_dir: Path to Tushare snapshot directory
        strategy_config: Parsed strategy configuration
        signal_date: Date when signals are generated (EOD)
        strategy_revision_id: Strategy revision ID for C admission gate check
        strategy_db_path: Path to StrategyDB for lifecycle state lookup

    Returns:
        List of PlannedSignal objects

    Raises:
        FileNotFoundError: If snapshot not found
        ValueError: If admission metadata is missing, signal_date is not a trading day,
            or strategy is not prototype_passed
    """
    # C0 admission gate: only prototype_passed strategies can generate signals
    if not strategy_revision_id:
        raise ValueError("strategy_revision_id is required for C module admission")
    if strategy_db_path is None:
        raise ValueError("strategy_db_path is required for C module admission")

    strategy_db = StrategyDB(strategy_db_path)
    try:
        lifecycle_state = strategy_db.get_latest_lifecycle_state(strategy_revision_id)
        if lifecycle_state is None:
            raise ValueError(f"Strategy revision '{strategy_revision_id}' not found in StrategyDB")

        # Call C admission gate
        admission_gate = CAdmissionGate()
        admission_gate.require_prototype_passed(
            strategy_revision_id=strategy_revision_id,
            lifecycle_state=lifecycle_state.state,
        )
    finally:
        strategy_db.close()
    # Load TushareDataSource
    tushare_config = TushareConfig(snapshot_dir=snapshot_dir)
    data_source = TushareDataSource(tushare_config)
    
    # Get metadata (snapshot_hash, etc.)
    metadata = data_source.get_metadata()
    snapshot_hash = metadata.snapshot_hash
    
    # Build trading calendar
    calendar = TradingCalendar(data_source)
    
    # Validate signal_date is a trading day
    if not calendar.is_trading_day(signal_date):
        raise ValueError(
            f"signal_date {signal_date} is not a trading day. "
            "Signals can only be generated on trading days (EOD)."
        )
    
    # Compute intended_execution_date (next trading day, T+1)
    try:
        intended_execution_date = calendar.next_trading_day(signal_date)
    except ValueError as e:
        raise ValueError(
            f"Cannot compute intended_execution_date for signal_date {signal_date}: {e}. "
            "Signal date may be the last trading day in the snapshot."
        ) from e
    
    # Build universe
    universe = build_universe(strategy_config, data_source)
    
    # Generate signals (strategy_core)
    signals = generate_signals(strategy_config, data_source, signal_date, universe)
    
    # Convert to PlannedSignals
    planned_signals = []
    for signal in signals:
        planned_signal = convert_signal_to_planned_signal(
            signal=signal,
            snapshot_hash=snapshot_hash,
            signal_date=signal_date,
            intended_execution_date=intended_execution_date,
            data_source=data_source,
            strategy_config=strategy_config,
        )
        planned_signals.append(planned_signal)
    
    return planned_signals


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate PlannedSignals from frozen snapshot + strategy YAML"
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        required=True,
        help="Path to Tushare snapshot directory (e.g., data/tushare_snapshots)",
    )
    parser.add_argument(
        "--strategy",
        type=Path,
        required=True,
        help="Path to strategy YAML file (e.g., examples/strategies/live_strategy.yaml)",
    )
    parser.add_argument(
        "--signal-date",
        type=str,
        required=True,
        help="Signal generation date in ISO format (YYYY-MM-DD, e.g., 2023-12-29)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON file path (e.g., signals/2023-12-29.json)",
    )
    parser.add_argument(
        "--strategy-revision-id",
        type=str,
        required=True,
        help="Strategy revision ID for C admission gate check",
    )
    parser.add_argument(
        "--strategy-db",
        type=str,
        required=True,
        help="Path to StrategyDB",
    )

    args = parser.parse_args()

    # Parse signal_date
    try:
        signal_date = date.fromisoformat(args.signal_date)
    except ValueError as e:
        print(f"Error: Invalid signal_date format: {args.signal_date}", file=sys.stderr)
        print(f"Expected ISO format YYYY-MM-DD (e.g., 2023-12-29)", file=sys.stderr)
        sys.exit(1)
    
    # Load strategy config
    try:
        strategy_config = load_strategy_config(args.strategy)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Generate planned signals
    try:
        planned_signals = generate_planned_signals_from_snapshot(
            snapshot_dir=args.snapshot_dir,
            strategy_config=strategy_config,
            signal_date=signal_date,
            strategy_revision_id=args.strategy_revision_id,
            strategy_db_path=args.strategy_db,
        )
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"Error generating signals: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Sort signals by (strategy_id, strategy_version, signal_date, intended_execution_date, symbol, direction, trigger_reason)
    # For stable output order (deterministic JSON)
    planned_signals.sort(
        key=lambda s: (
            s.strategy_id,
            s.strategy_version,
            s.signal_date,
            s.intended_execution_date,
            s.symbol,
            s.direction,
            s.trigger_reason,
        )
    )
    
    # Export to JSON
    output_data = [signal.model_dump(mode="json") for signal in planned_signals]
    
    # Create output directory if not exists
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Print summary
    metadata = TushareDataSource(TushareConfig(snapshot_dir=args.snapshot_dir)).get_metadata()
    
    print(f"✓ Generated {len(planned_signals)} planned signals")
    print(f"  output_path: {args.output}")
    print(f"  snapshot_hash: {metadata.snapshot_hash}")
    print(f"  strategy_id: {strategy_config.strategy_name}")
    print(f"  strategy_version: {strategy_config.version}")
    print(f"  signal_date: {signal_date}")
    print(f"  intended_execution_date: {planned_signals[0].intended_execution_date if planned_signals else 'N/A'}")


if __name__ == "__main__":
    main()
