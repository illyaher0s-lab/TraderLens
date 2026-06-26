#!/usr/bin/env python3
"""
Load Planned Signals into SQLite Database

Load PlannedSignal JSON (from generate_planned_signals.py) into signal_board.db.

Usage:
    python backend/scripts/load_planned_signals.py \
        --input signals/2023-12-29.json \
        --db data/signal_board.db

Hard Constraints:
- Use deterministic signal_id (no duplicate imports)
- Do NOT overwrite existing review_status (preserve human decisions)
- Do NOT modify signals already reviewed by humans
- Print import statistics

Design:
- New signal (signal_id not in DB) → INSERT
- Existing signal (signal_id in DB) → SKIP (preserve review decisions)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


def load_planned_signals(input_path: Path, db_path: Path) -> dict:
    """
    Load PlannedSignals from JSON into SQLite database.
    
    Args:
        input_path: Path to JSON file (output from generate_planned_signals.py)
        db_path: Path to SQLite database file
    
    Returns:
        Statistics dict with counts
    
    Raises:
        FileNotFoundError: If input JSON not found
        ValueError: If JSON is invalid or contains invalid signals
    """
    # Load JSON
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    with open(input_path, "r", encoding="utf-8") as f:
        signals_data = json.load(f)
    
    if not isinstance(signals_data, list):
        raise ValueError(f"Expected list of signals, got {type(signals_data)}")
    
    # Parse into PlannedSignal objects
    signals = []
    for i, signal_dict in enumerate(signals_data):
        try:
            signal = PlannedSignal(**signal_dict)
            signals.append(signal)
        except Exception as e:
            raise ValueError(f"Invalid signal at index {i}: {e}") from e
    
    # Initialize database
    db = SignalBoardDB(db_path=str(db_path))
    
    # Load signals (skip existing to preserve review decisions)
    imported_count = 0
    skipped_count = 0
    
    for signal in signals:
        # Check if signal already exists
        existing = db.get_signal(signal.signal_id)
        
        if existing:
            # Signal exists → SKIP (preserve human review decisions)
            skipped_count += 1
        else:
            # New signal → INSERT
            db.create_signal(signal)
            imported_count += 1
    
    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "total_signals": len(signals),
        "db_path": str(db_path),
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load PlannedSignals from JSON into SQLite database"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to JSON file (e.g., signals/2023-12-29.json)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to SQLite database (e.g., data/signal_board.db)",
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Create parent directory for DB if not exists
    args.db.parent.mkdir(parents=True, exist_ok=True)
    
    # Load signals
    try:
        stats = load_planned_signals(args.input, args.db)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Print statistics
    print(f"✓ Loaded {stats['total_signals']} signals from {args.input}")
    print(f"  imported_count: {stats['imported_count']} (new signals)")
    print(f"  skipped_count: {stats['skipped_count']} (already exists, preserved)")
    print(f"  db_path: {stats['db_path']}")


if __name__ == "__main__":
    main()
