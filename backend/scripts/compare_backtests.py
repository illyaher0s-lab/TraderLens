"""
Compare Backtest Results

Compare multiple backtest export directories and generate comparison report.

Usage:
    python backend/scripts/compare_backtests.py \\
      --inputs exports/run_001 exports/run_002 exports/run_003 \\
      --output exports/comparison_001

    Optional:
      --sort-by total_return
      --descending
"""
import json
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional


def compare_backtests(input_dirs: list[str], output_dir: str, sort_by: Optional[str] = None, descending: bool = False):
    """
    Compare backtest results from multiple export directories.
    
    Args:
        input_dirs: List of export directory paths
        output_dir: Output directory for comparison results
        sort_by: Optional field to sort by (e.g., 'total_return')
        descending: Sort in descending order if True
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not input_dirs:
        print("Error: No input directories provided")
        sys.exit(1)
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Comparing {len(input_dirs)} backtest results...")
    print()
    
    # Collect data from each input directory
    rows = []
    warnings = []
    failures = []
    
    for i, input_dir in enumerate(input_dirs, 1):
        input_path = Path(input_dir)
        print(f"[{i}/{len(input_dirs)}] Processing {input_path}...")
        
        if not input_path.exists():
            failure_msg = f"{input_dir}: directory does not exist"
            print(f"  ✗ {failure_msg}")
            failures.append(failure_msg)
            continue
        
        metrics_file = input_path / "metrics.json"
        if not metrics_file.exists():
            failure_msg = f"{input_dir}: metrics.json not found"
            print(f"  ✗ {failure_msg}")
            failures.append(failure_msg)
            continue
        
        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            
            row = extract_comparison_row(metrics, str(input_path), warnings)
            rows.append(row)
            print(f"  ✓ Loaded {row['strategy_name']}")
            
        except Exception as e:
            failure_msg = f"{input_dir}: failed to load metrics.json: {e}"
            print(f"  ✗ {failure_msg}")
            failures.append(failure_msg)
            continue
    
    if not rows:
        print("\n✗ No valid backtest results found. All inputs failed.")
        sys.exit(1)
    
    print()
    print(f"Successfully loaded {len(rows)} results")
    if failures:
        print(f"Failed: {len(failures)} directories")
    if warnings:
        print(f"Warnings: {len(warnings)} missing fields")
    print()
    
    # Sort if requested
    if sort_by:
        if sort_by not in rows[0]:
            print(f"Warning: sort field '{sort_by}' not found in data")
        else:
            rows = sorted(
                rows,
                key=lambda r: r[sort_by] if r[sort_by] is not None else float('-inf'),
                reverse=descending
            )
            print(f"Sorted by {sort_by} ({'descending' if descending else 'ascending'})")
    
    # Generate comparison JSON with schema version
    from contracts import SCHEMA_VERSION
    
    comparison = {
        # Schema metadata (M2)
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "comparison",
        
        # Comparison metadata
        "generated_at": datetime.now().isoformat(),
        "input_count": len(input_dirs),
        "valid_count": len(rows),
        "failed_count": len(failures),
        "rows": rows,
        "warnings": warnings,
        "failures": failures,
    }
    
    # Export comparison.json
    comparison_json_path = output_path / "comparison.json"
    with open(comparison_json_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"✓ Exported comparison.json")
    
    # Export comparison.csv
    comparison_csv_path = output_path / "comparison.csv"
    export_comparison_csv(rows, comparison_csv_path)
    print(f"✓ Exported comparison.csv ({len(rows)} rows)")
    
    print(f"\n✓ Comparison report saved to {output_path.absolute()}")


def extract_comparison_row(metrics: dict, export_dir: str, warnings: list) -> dict:
    """Extract comparison row from metrics.json."""
    
    def safe_get(key: str, default=None):
        """Safely get a field, record warning if missing."""
        if key not in metrics:
            warning_msg = f"{export_dir}: missing field '{key}'"
            if warning_msg not in warnings:
                warnings.append(warning_msg)
            return default
        return metrics[key]
    
    # Extract basic fields
    row = {
        "strategy_name": safe_get("strategy_id", "unknown"),
        "strategy_version": safe_get("strategy_version", "unknown"),
        "export_dir": export_dir,
        "initial_capital": safe_get("initial_capital"),
        "final_capital": safe_get("final_capital"),
        "total_return": safe_get("total_return"),
        "total_return_pct": safe_get("total_return_pct"),
        "max_drawdown": safe_get("max_drawdown"),
        "max_drawdown_pct": safe_get("max_drawdown_pct"),
        "total_trades": safe_get("total_trades"),
        "buy_trades": safe_get("buy_trades"),
        "sell_trades": safe_get("sell_trades"),
        "total_round_trips": safe_get("total_round_trips"),
        "winning_trips": safe_get("winning_trips"),
        "losing_trips": safe_get("losing_trips"),
        "win_rate": safe_get("win_rate"),
        "profit_factor": safe_get("profit_factor"),
        "avg_holding_days": safe_get("avg_holding_days"),
        "total_commission": safe_get("total_commission"),
        "total_stamp_duty": safe_get("total_stamp_duty"),
        "total_fees": safe_get("total_fees"),
        "t1_blocked_exit_count": safe_get("t1_blocked_exit_count"),
        "partial_exit_due_to_t1_count": safe_get("partial_exit_due_to_t1_count"),
        "rejected_orders": safe_get("rejected_orders"),
    }
    
    # Calculate excess return if benchmark_return exists
    benchmark_return = safe_get("benchmark_return")
    if benchmark_return is not None and row["total_return"] is not None:
        row["benchmark_return"] = benchmark_return
        row["excess_return"] = row["total_return"] - benchmark_return
    else:
        row["benchmark_return"] = None
        row["excess_return"] = None
    
    return row


def export_comparison_csv(rows: list[dict], output_path: Path):
    """Export comparison to CSV."""
    if not rows:
        return
    
    # Use keys from first row as fieldnames
    fieldnames = list(rows[0].keys())
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in rows:
            # Format numeric fields for CSV (preserve decimals)
            formatted_row = {}
            for key, value in row.items():
                if value is None:
                    formatted_row[key] = ""
                elif isinstance(value, float):
                    formatted_row[key] = f"{value:.6f}"
                else:
                    formatted_row[key] = value
            
            writer.writerow(formatted_row)


def main():
    parser = argparse.ArgumentParser(
        description="Compare multiple backtest results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/scripts/compare_backtests.py \\
    --inputs exports/run_001 exports/run_002 exports/run_003 \\
    --output exports/comparison_001

  python backend/scripts/compare_backtests.py \\
    --inputs exports/* \\
    --output exports/comparison_all \\
    --sort-by total_return \\
    --descending
        """
    )
    
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input export directories (must contain metrics.json)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for comparison results"
    )
    parser.add_argument(
        "--sort-by",
        help="Field to sort by (e.g., total_return, max_drawdown, win_rate)"
    )
    parser.add_argument(
        "--descending",
        action="store_true",
        help="Sort in descending order"
    )
    
    args = parser.parse_args()
    
    compare_backtests(
        input_dirs=args.inputs,
        output_dir=args.output,
        sort_by=args.sort_by,
        descending=args.descending
    )


if __name__ == "__main__":
    main()
