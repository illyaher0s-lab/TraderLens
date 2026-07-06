"""
Runtime Test Helpers

Utilities for isolating and managing runtime verification test data.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_run_id() -> str:
    """Generate a unique run ID for this verification run."""
    return datetime.now().strftime("P2RUN_%Y%m%d_%H%M%S")


def cleanup_test_data(db_path: str, dry_run: bool = True, verbose: bool = True) -> dict:
    """
    Clean up test data marked with P2RUN_ tags.
    
    Args:
        db_path: Path to live_trade.db
        dry_run: If True (default), only show what would be deleted
        verbose: If True, print details
    
    Returns:
        dict with counts: {
            "positions": N,
            "logs": N,
            "reviews": N,
            "signals": N,
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    counts = {
        "positions": 0,
        "logs": 0,
        "reviews": 0,
        "signals": 0,
    }
    
    try:
        # Find test positions (entry_thesis contains P2RUN_)
        test_positions = cursor.execute(
            """
            SELECT position_id, symbol, name, entry_thesis, opened_at
            FROM observation_positions
            WHERE entry_thesis LIKE '%P2RUN_%'
            """
        ).fetchall()
        
        counts["positions"] = len(test_positions)
        
        if verbose:
            print(f"Found {counts['positions']} test positions:")
            for pos in test_positions:
                print(f"  - {pos['position_id']}: {pos['name']} ({pos['symbol']}) @ {pos['opened_at']}")
        
        if not dry_run:
            # Delete test positions
            cursor.execute(
                "DELETE FROM observation_positions WHERE entry_thesis LIKE '%P2RUN_%'"
            )
            if verbose:
                print(f"Deleted {counts['positions']} test positions")
        
        # Find test logs (reason contains P2RUN_)
        test_logs = cursor.execute(
            """
            SELECT log_id, confirmed_action, confirmed_at
            FROM execution_observation_logs
            WHERE reason LIKE '%P2RUN_%'
            """
        ).fetchall()
        
        counts["logs"] = len(test_logs)
        
        if verbose:
            print(f"Found {counts['logs']} test execution logs")
        
        if not dry_run:
            cursor.execute(
                "DELETE FROM execution_observation_logs WHERE reason LIKE '%P2RUN_%'"
            )
            if verbose:
                print(f"Deleted {counts['logs']} test logs")
        
        # Find test reviews (linked to deleted positions)
        if counts["positions"] > 0:
            position_ids = [pos["position_id"] for pos in test_positions]
            placeholders = ",".join(["?" for _ in position_ids])
            
            test_reviews = cursor.execute(
                f"""
                SELECT review_id, position_id, created_at
                FROM discipline_reviews
                WHERE position_id IN ({placeholders})
                """,
                position_ids
            ).fetchall()
            
            counts["reviews"] = len(test_reviews)
            
            if verbose:
                print(f"Found {counts['reviews']} test reviews")
            
            if not dry_run:
                cursor.execute(
                    f"DELETE FROM discipline_reviews WHERE position_id IN ({placeholders})",
                    position_ids
                )
                if verbose:
                    print(f"Deleted {counts['reviews']} test reviews")
            
            # Find test signals (linked to deleted positions)
            test_signals = cursor.execute(
                f"""
                SELECT signal_record_id, position_id, signal_type, as_of_date
                FROM daily_observation_signals
                WHERE position_id IN ({placeholders})
                """,
                position_ids
            ).fetchall()
            
            counts["signals"] = len(test_signals)
            
            if verbose:
                print(f"Found {counts['signals']} test daily signals")
            
            if not dry_run:
                cursor.execute(
                    f"DELETE FROM daily_observation_signals WHERE position_id IN ({placeholders})",
                    position_ids
                )
                if verbose:
                    print(f"Deleted {counts['signals']} test signals")
        
        if dry_run:
            if verbose:
                print("\nWARNING: DRY RUN - no data was deleted")
                print("To actually delete, run with --apply flag")
        else:
            conn.commit()
            if verbose:
                print("\nCleanup complete")
        
    finally:
        conn.close()
    
    return counts


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up P2 runtime verification test data")
    parser.add_argument(
        "--db",
        default="data/live_trade.db",
        help="Path to live_trade.db (default: data/live_trade.db)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete data (default: dry-run only)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output"
    )
    
    args = parser.parse_args()
    
    # Resolve db path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        # Assume relative to script's parent directory
        script_dir = Path(__file__).parent
        db_path = (script_dir.parent / args.db).resolve()
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        exit(1)
    
    print(f"Database: {db_path}")
    print(f"Mode: {'APPLY (will delete)' if args.apply else 'DRY RUN (no changes)'}")
    print()
    
    counts = cleanup_test_data(
        str(db_path),
        dry_run=not args.apply,
        verbose=not args.quiet
    )
    
    print("\nSummary:")
    print(f"  Positions: {counts['positions']}")
    print(f"  Logs: {counts['logs']}")
    print(f"  Reviews: {counts['reviews']}")
    print(f"  Signals: {counts['signals']}")
