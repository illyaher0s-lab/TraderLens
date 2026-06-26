#!/usr/bin/env python3
"""
Quick Test Data Loader for Signal Board Manual Testing

Creates sample signals with multiple strategies for testing the multi-strategy selector UI.

Usage:
    python backend/scripts/load_test_signals.py
"""

import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


def create_test_signals():
    """Create test signals with multiple strategies."""
    
    db_path = Path("data/signal_board.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    db = SignalBoardDB(db_path)
    
    # Strategy 1: momentum_v2
    signals_momentum = [
        PlannedSignal(
            signal_id=f"momentum_v2_v210_{i}",
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="test_snapshot_001",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol=f"60051{i}.SH",
            direction="buy",
            planned_action="enter",
            quantity=100,
            trigger_reason=f"Momentum signal {i}: Price broke above 20-day high",
            review_status="pending",
            current_price=50.0 + i,
            position_before=0,
            created_at=datetime(2023, 12, 29, 16, 0, 0),
            metadata={"test": True}
        )
        for i in range(5)
    ]
    
    signals_momentum_v2 = [
        PlannedSignal(
            signal_id=f"momentum_v2_v220_{i}",
            strategy_id="momentum_v2",
            strategy_version="v2.2.0",
            snapshot_hash="test_snapshot_001",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol=f"60052{i}.SH",
            direction="sell",
            planned_action="exit",
            quantity=100,
            trigger_reason=f"Momentum exit {i}: Price fell below 20-day low",
            review_status="pending",
            current_price=45.0 + i,
            position_before=100,
            created_at=datetime(2023, 12, 29, 16, 0, 0),
            metadata={"test": True}
        )
        for i in range(3)
    ]
    
    # Strategy 2: mean_reversion
    signals_mean_reversion = [
        PlannedSignal(
            signal_id=f"mean_reversion_v100_{i}",
            strategy_id="mean_reversion",
            strategy_version="v1.0.0",
            snapshot_hash="test_snapshot_001",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol=f"00000{i}.SZ",
            direction="buy",
            planned_action="enter",
            quantity=200,
            trigger_reason=f"Mean reversion {i}: RSI below 30",
            review_status="pending",
            current_price=30.0 + i,
            position_before=0,
            created_at=datetime(2023, 12, 29, 16, 0, 0),
            metadata={"test": True}
        )
        for i in range(4)
    ]
    
    # Strategy 3: breakout_strategy
    signals_breakout = [
        PlannedSignal(
            signal_id=f"breakout_strategy_v110_{i}",
            strategy_id="breakout_strategy",
            strategy_version="v1.1.0",
            snapshot_hash="test_snapshot_001",
            signal_date=date(2023, 12, 28),
            intended_execution_date=date(2023, 12, 29),
            symbol=f"30001{i}.SZ",
            direction="buy",
            planned_action="enter",
            quantity=150,
            trigger_reason=f"Breakout {i}: Volume surge + price breakout",
            review_status="watching",
            current_price=80.0 + i,
            position_before=0,
            created_at=datetime(2023, 12, 28, 16, 0, 0),
            metadata={"test": True}
        )
        for i in range(3)
    ]
    
    all_signals = signals_momentum + signals_momentum_v2 + signals_mean_reversion + signals_breakout
    
    print(f"Creating {len(all_signals)} test signals...")
    
    for signal in all_signals:
        try:
            db.create_signal(signal)
        except Exception as e:
            print(f"  Skipped {signal.signal_id} (already exists)")
    
    print(f"✓ Done!")
    print(f"\nStrategies created:")
    print(f"  - momentum_v2 (v2.1.0): 5 signals")
    print(f"  - momentum_v2 (v2.2.0): 3 signals")
    print(f"  - mean_reversion (v1.0.0): 4 signals")
    print(f"  - breakout_strategy (v1.1.0): 3 signals")
    print(f"\nTotal: {len(all_signals)} signals")
    print(f"\nDatabase: {db_path}")
    print(f"\nTest frontend at: http://localhost:3000/signals")


if __name__ == "__main__":
    create_test_signals()
