#!/usr/bin/env python3
"""
Signal Expiration Script

Marks pending signals as expired when their intended_execution_date has passed.

Design Constraints (M4.1 Phase 2):
- Only updates pending → expired (不修改 watching/ignored/expired)
- Does NOT modify planned_action or strategy logic
- Does NOT call external APIs (local date-based check)
- Idempotent: safe to run multiple times
- Fail-loud on missing DB or invalid schema

Usage:
    # Expire signals as of today
    python backend/scripts/expire_signals.py \\
        --db data/signal_board.db \\
        --as-of-date 2024-01-02
    
    # With custom reviewed_by
    python backend/scripts/expire_signals.py \\
        --db data/signal_board.db \\
        --as-of-date 2024-01-02 \\
        --reviewed-by system_expiration

Example Output:
    Expiring pending signals as of 2024-01-02...
    ✓ Expired 5 signals
    Skipped 0 signals (already expired or non-pending)
    DB: data/signal_board.db
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.db.signal_board import SignalBoardDB


def expire_signals(
    db_path: Path,
    as_of_date: date,
    reviewed_by: str = "system_expiration"
) -> tuple[int, int]:
    """
    Expire pending signals whose intended_execution_date has passed.
    
    Args:
        db_path: Path to signal_board.db
        as_of_date: Current date to compare against intended_execution_date
        reviewed_by: Username to record (default: "system_expiration")
    
    Returns:
        (expired_count, skipped_count)
        expired_count: Number of signals marked as expired
        skipped_count: Number of signals already expired or non-pending
    
    Raises:
        FileNotFoundError: If DB does not exist
        sqlite3.OperationalError: If DB schema is invalid
    """
    # Verify DB exists
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    # Load database
    db = SignalBoardDB(db_path)
    
    # Count signals before expiration (for skipped count)
    all_signals = []
    offset = 0
    while True:
        page = db.list_signals(limit=500, offset=offset)
        all_signals.extend(page.items)
        if not page.has_more:
            break
        offset += len(page.items)
    
    # Filter: intended_execution_date < as_of_date AND review_status = pending
    pending_expired = [
        s for s in all_signals
        if s.intended_execution_date < as_of_date and s.review_status == "pending"
    ]
    
    # Expire pending signals
    expired_count = db.expire_pending_signals(
        as_of_date=as_of_date,
        reviewed_by=reviewed_by
    )
    
    # Calculate skipped (signals that were already expired or not pending)
    total_expired_before = len([
        s for s in all_signals
        if s.intended_execution_date < as_of_date and s.review_status in ["expired", "watching", "ignored"]
    ])
    
    skipped_count = total_expired_before
    
    return expired_count, skipped_count


def main():
    parser = argparse.ArgumentParser(
        description="Expire pending signals whose intended_execution_date has passed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Expire signals as of 2024-01-02
    python backend/scripts/expire_signals.py --db data/signal_board.db --as-of-date 2024-01-02
    
    # With custom reviewed_by
    python backend/scripts/expire_signals.py \\
        --db data/signal_board.db \\
        --as-of-date 2024-01-02 \\
        --reviewed-by manual_cleanup
        """
    )
    
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to signal_board.db"
    )
    
    parser.add_argument(
        "--as-of-date",
        type=date.fromisoformat,
        required=True,
        help="Current date to compare against intended_execution_date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--reviewed-by",
        type=str,
        default="system_expiration",
        help="Username to record (default: system_expiration)"
    )
    
    args = parser.parse_args()
    
    # Execute
    try:
        print(f"Expiring pending signals as of {args.as_of_date}...")
        
        expired_count, skipped_count = expire_signals(
            db_path=args.db,
            as_of_date=args.as_of_date,
            reviewed_by=args.reviewed_by
        )
        
        print(f"✓ Expired {expired_count} signals")
        print(f"Skipped {skipped_count} signals (already expired or non-pending)")
        print(f"DB: {args.db}")
        
        return 0
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
