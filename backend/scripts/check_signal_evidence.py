#!/usr/bin/env python3
"""
Evidence Light Check for PlannedSignals

Performs fast risk checks on signals without deep research:
1. ST status (from StockIdentity)
2. Suspended (from DailyStatus)
3. Limit up (buy signals cannot execute)
4. Limit down (sell signals cannot execute)
5. Low liquidity (volume < threshold)

Design Constraints (from M4.1 Plan):
- Only adds risk_flags, does NOT modify planned_action
- Does NOT change signal generation logic
- Reads latest EOD snapshot only (no live API)
- Fast checks only (no LLM, no web search, no sentiment analysis)

Usage:
    # Update signals in database
    python backend/scripts/check_signal_evidence.py --db data/signal_board.db --date 2023-12-29
    
    # Check signals from JSON file
    python backend/scripts/check_signal_evidence.py --input signals.json --output checked.json
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Literal

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_data_source import TushareDataSource
from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


def check_signal_evidence(
    signal: PlannedSignal,
    data_source: TushareDataSource,
    min_liquidity_threshold: int = 1_000_000  # Default: 1M shares/day
) -> tuple[list[str], Literal["clean", "warning", "blocked"]]:
    """
    Perform evidence light_check on a single signal.
    
    Args:
        signal: PlannedSignal to check
        data_source: TushareDataSource for reading status/bar data
        min_liquidity_threshold: Minimum daily volume (shares)
    
    Returns:
        (risk_flags, evidence_status)
        risk_flags: List of detected risks
        evidence_status: "clean" | "warning" | "blocked"
    
    Risk Flags:
        - "ST": Stock is ST or *ST
        - "suspended": Stock is suspended
        - "limit_up": Stock hit limit up (buy signals blocked)
        - "limit_down": Stock hit limit down (sell signals blocked)
        - "low_liquidity": Volume below threshold
    
    Evidence Status:
        - "clean": No risks detected
        - "warning": Risks detected but tradeable (ST, low_liquidity)
        - "blocked": Cannot execute (suspended, limit_up for buy, limit_down for sell)
    """
    risk_flags: list[str] = []
    
    # Check 1: ST status (from StockIdentity)
    try:
        # Note: StockIdentity doesn't expose is_st directly in current implementation
        # We'll check via DailyStatus.is_st instead
        pass
    except Exception:
        pass
    
    # Check 2-4: DailyStatus (suspended, limit_up, limit_down, ST)
    try:
        status = data_source.get_daily_status(signal.symbol, signal.signal_date)
        
        if status.is_st:
            risk_flags.append("ST")
        
        if status.is_suspended:
            risk_flags.append("suspended")
        
        if status.is_limit_up and signal.direction == "buy":
            risk_flags.append("limit_up")
        
        if status.is_limit_down and signal.direction == "sell":
            risk_flags.append("limit_down")
    
    except KeyError as e:
        # Missing status data - cannot verify
        # This is acceptable: light_check is best-effort
        print(f"Warning: Cannot check status for {signal.symbol} on {signal.signal_date}: {e}", file=sys.stderr)
    
    # Check 5: Low liquidity (from DailyBar)
    try:
        bar = data_source.get_daily_bar(signal.symbol, signal.signal_date)
        
        if bar.volume < min_liquidity_threshold:
            risk_flags.append("low_liquidity")
    
    except KeyError as e:
        # Missing bar data - cannot verify liquidity
        print(f"Warning: Cannot check liquidity for {signal.symbol} on {signal.signal_date}: {e}", file=sys.stderr)
    
    # Determine evidence_status
    blocking_flags = {"suspended", "limit_up", "limit_down"}
    
    if any(flag in blocking_flags for flag in risk_flags):
        evidence_status = "blocked"
    elif len(risk_flags) > 0:
        evidence_status = "warning"
    else:
        evidence_status = "clean"
    
    return risk_flags, evidence_status


def check_signals_from_db(
    db_path: Path,
    signal_date: date,
    snapshot_root: Path,
    min_liquidity_threshold: int
) -> int:
    """
    Check signals in database for a given date.
    
    Args:
        db_path: Path to signal_board.db
        signal_date: Date to check signals for
        snapshot_root: Path to Tushare snapshot root
        min_liquidity_threshold: Minimum daily volume
    
    Returns:
        Number of signals checked
    """
    # Load database
    db = SignalBoardDB(db_path)
    
    # Load data source
    # Find snapshot matching signal_date (use latest available)
    config = TushareConfig(snapshot_root=snapshot_root)
    data_source = TushareDataSource(config)
    
    # Query signals for this date in pages to respect the Signal Board API cap.
    signals = []
    offset = 0
    while True:
        page = db.list_signals(signal_date=signal_date, limit=500, offset=offset)
        signals.extend(page.items)
        if not page.has_more:
            break
        offset += len(page.items)
    
    if not signals:
        print(f"No signals found for date {signal_date}")
        return 0
    
    print(f"Checking {len(signals)} signals for {signal_date}...")
    
    checked_count = 0
    for signal in signals:
        risk_flags, evidence_status = check_signal_evidence(
            signal, data_source, min_liquidity_threshold
        )
        
        # Update evidence in database
        checked_at = datetime.now()
        db.update_evidence(
            signal_id=signal.signal_id,
            risk_flags=risk_flags,
            evidence_status=evidence_status,
            evidence_checked_at=checked_at
        )
        checked_count += 1
        
        if risk_flags:
            print(f"  {signal.symbol} {signal.direction}: {risk_flags} -> {evidence_status}")
    
    print(f"✓ Checked {checked_count} signals")
    return checked_count


def check_signals_from_json(
    input_path: Path,
    output_path: Path,
    snapshot_root: Path,
    min_liquidity_threshold: int
) -> int:
    """
    Check signals from JSON file and write to output JSON.
    
    Args:
        input_path: Path to input signals JSON
        output_path: Path to output checked signals JSON
        snapshot_root: Path to Tushare snapshot root
        min_liquidity_threshold: Minimum daily volume
    
    Returns:
        Number of signals checked
    """
    # Load signals from JSON
    with open(input_path, "r", encoding="utf-8") as f:
        signals_data = json.load(f)
    
    signals = [PlannedSignal(**s) for s in signals_data]
    
    # Load data source
    config = TushareConfig(snapshot_root=snapshot_root)
    data_source = TushareDataSource(config)
    
    print(f"Checking {len(signals)} signals from {input_path}...")
    
    checked_signals = []
    for signal in signals:
        risk_flags, evidence_status = check_signal_evidence(
            signal, data_source, min_liquidity_threshold
        )
        
        # Update signal fields
        signal.risk_flags = risk_flags
        signal.evidence_status = evidence_status
        signal.evidence_checked_at = datetime.now()
        
        checked_signals.append(signal)
        
        if risk_flags:
            print(f"  {signal.symbol} {signal.direction}: {risk_flags} -> {evidence_status}")
    
    # Write to output JSON
    output_data = [s.model_dump(mode="json") for s in checked_signals]
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Checked {len(checked_signals)} signals -> {output_path}")
    return len(checked_signals)


def main():
    parser = argparse.ArgumentParser(description="Evidence light check for PlannedSignals")
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--db", type=Path, help="Path to signal_board.db (database mode)")
    mode_group.add_argument("--input", type=Path, help="Input signals JSON file (file mode)")
    
    # Database mode arguments
    parser.add_argument("--date", type=date.fromisoformat, help="Signal date to check (required for --db)")
    
    # File mode arguments
    parser.add_argument("--output", type=Path, help="Output signals JSON file (required for --input)")
    
    # Common arguments
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("data/snapshots"),
        help="Tushare snapshot root directory (default: data/snapshots)"
    )
    
    parser.add_argument(
        "--min-liquidity",
        type=int,
        default=1_000_000,
        help="Minimum daily volume threshold (default: 1,000,000 shares)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.db and not args.date:
        parser.error("--date is required when using --db")
    
    if args.input and not args.output:
        parser.error("--output is required when using --input")
    
    # Execute
    try:
        if args.db:
            check_signals_from_db(
                db_path=args.db,
                signal_date=args.date,
                snapshot_root=args.snapshot_root,
                min_liquidity_threshold=args.min_liquidity
            )
        else:
            check_signals_from_json(
                input_path=args.input,
                output_path=args.output,
                snapshot_root=args.snapshot_root,
                min_liquidity_threshold=args.min_liquidity
            )
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
