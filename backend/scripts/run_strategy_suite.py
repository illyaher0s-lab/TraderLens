"""
Run Strategy Suite

Run multiple strategies and generate suite-level comparison report.

Usage:
    python backend/scripts/run_strategy_suite.py \\
      --fixture tests/fixed_fixture \\
      --strategies examples/strategies \\
      --output suite_results/sprint_001
"""
import argparse
import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.fixed_fixture import FixedFixtureDataSource
from backend.scripts.compare_backtests import compare_backtests
from backend.scripts.export_backtest_result import export_backtest_result
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config_dict
from strategy_core.trading_calendar import TradingCalendar


def run_strategy_suite(fixture_path: str, strategies_dir: str, output_dir: str):
    """
    Run a suite of strategies and generate comparison report.
    """
    fixture_path = Path(fixture_path)
    strategies_dir = Path(strategies_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("STRATEGY SUITE VALIDATION")
    print("=" * 70)
    print(f"Fixture: {fixture_path}")
    print(f"Strategies: {strategies_dir}")
    print(f"Output: {output_path}")
    print()

    print("Loading data source...")
    data_source = FixedFixtureDataSource(fixture_path)
    calendar = TradingCalendar(data_source)
    print(f"  OK Loaded {len(data_source.symbols())} symbols")
    print("  OK Trading calendar ready")
    print()

    strategy_files = list(strategies_dir.glob("*.yaml"))
    if not strategy_files:
        print(f"ERROR No strategy YAML files found in {strategies_dir}")
        sys.exit(1)

    print(f"Found {len(strategy_files)} strategy configurations")
    print()

    results = []
    export_dirs = []

    for i, strategy_file in enumerate(strategy_files, 1):
        print(f"[{i}/{len(strategy_files)}] Running {strategy_file.name}...")
        print("-" * 70)

        result = run_single_strategy(
            strategy_file=strategy_file,
            data_source=data_source,
            calendar=calendar,
            output_path=output_path,
        )

        results.append(result)
        if result["status"] == "success":
            export_dirs.append(result["export_dir"])

        print()

    print("=" * 70)
    print("GENERATING SUITE SUMMARY")
    print("=" * 70)

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    # Generate suite summary with schema version
    from contracts import SCHEMA_VERSION
    
    suite_summary = {
        # Schema metadata (M2)
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "suite_summary",
        
        # Suite metadata
        "generated_at": datetime.now().isoformat(),
        "fixture_path": str(fixture_path),
        "strategies_dir": str(strategies_dir),
        "output_dir": str(output_path),
        "strategy_count": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "data_source": "mock",
        "result_usage": "toolchain_validation_only",
        "results": results,
        "warnings": [
            "Data source is 'mock' - not real market data",
            "Results are for toolchain validation only",
            "Do not interpret strategy performance as real-world viability",
        ],
    }

    summary_path = output_path / "suite_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(suite_summary, f, indent=2, ensure_ascii=False)
    print(f"OK Suite summary: {summary_path}")

    if export_dirs:
        print()
        print("Generating suite comparison...")
        compare_backtests(
            input_dirs=[str(d) for d in export_dirs],
            output_dir=str(output_path / "suite_comparison"),
            sort_by="total_return",
            descending=True,
        )

    print()
    print("=" * 70)
    print("SUITE RESULTS")
    print("=" * 70)
    print(f"Total strategies: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print()

    for result in results:
        status_icon = "OK" if result["status"] == "success" else "ERROR"
        print(f"{status_icon} {result['strategy_name']}: {result['status']}")
        if result["status"] == "success":
            gate_status = result.get("prototype_gate_status", "unknown")
            print(f"   Gate: {gate_status}")
            print(f"   Return: {result.get('total_return_pct', 0):.2f}%")
            print(f"   Trades: {result.get('trade_count', 0)}")
        else:
            print(f"   Error: {result.get('error', 'unknown')}")

    print()
    print(f"OK All results saved to {output_path.absolute()}")


def run_single_strategy(strategy_file: Path, data_source, calendar, output_path: Path) -> dict:
    """Run a single strategy and export results."""
    result = {
        "strategy_name": strategy_file.stem,
        "strategy_file": str(strategy_file),
        "status": "unknown",
    }

    try:
        with open(strategy_file, "r", encoding="utf-8") as f:
            strategy_dict = yaml.safe_load(f)

        print(f"  OK Loaded config: {strategy_dict['strategy_name']}")

        config = parse_strategy_config_dict(strategy_dict)
        print("  OK Validated config")

        backtest_result = run_backtest(
            config,
            data_source,
            calendar,
            initial_capital=config.backtest_config.initial_capital,
        )
        print("  OK Backtest complete")
        print(f"     Return: {backtest_result.total_return * 100:.2f}%")
        print(f"     Trades: {len(backtest_result.trades)}")
        if backtest_result.prototype_gate_result:
            print(f"     Gate: {backtest_result.prototype_gate_result.status}")

        export_dir = output_path / strategy_file.stem
        export_dir.mkdir(parents=True, exist_ok=True)

        result_json_path = export_dir / "backtest_result.json"
        with open(result_json_path, "w", encoding="utf-8") as f:
            json.dump(backtest_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        with contextlib.redirect_stdout(io.StringIO()):
            export_backtest_result(str(result_json_path), str(export_dir))
        print(f"  OK Exported to {export_dir.name}/")

        result["status"] = "success"
        result["export_dir"] = str(export_dir)
        result["total_return"] = backtest_result.total_return
        result["total_return_pct"] = backtest_result.total_return * 100
        result["trade_count"] = len(backtest_result.trades)
        result["round_trips"] = len(backtest_result.round_trips)
        result["prototype_gate_status"] = (
            backtest_result.prototype_gate_result.status
            if backtest_result.prototype_gate_result
            else "not_evaluated"
        )
        result["entry_signal_count"] = backtest_result.entry_signal_count
        result["exit_signal_count"] = backtest_result.exit_signal_count
        result["buy_order_count"] = backtest_result.buy_order_count
        result["sell_order_count"] = backtest_result.sell_order_count
        result["buy_fill_count"] = backtest_result.buy_fill_count
        result["sell_fill_count"] = backtest_result.sell_fill_count
        result["exit_rejected_count"] = backtest_result.exit_rejected_count
        result["completed_round_trips"] = backtest_result.completed_round_trips
        result["exit_triggered_rules"] = backtest_result.exit_triggered_rules
        result["t1_blocked_exit_count"] = backtest_result.t1_blocked_exit_count
        result["partial_exit_due_to_t1_count"] = backtest_result.partial_exit_due_to_t1_count

    except Exception as e:
        print(f"  ERROR Failed: {e}")
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run strategy suite and generate comparison report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python backend/scripts/run_strategy_suite.py \\
    --fixture tests/fixed_fixture \\
    --strategies examples/strategies \\
    --output suite_results/sprint_001
        """,
    )

    parser.add_argument(
        "--fixture",
        required=True,
        help="Path to fixed fixture directory",
    )
    parser.add_argument(
        "--strategies",
        required=True,
        help="Directory containing strategy YAML files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for suite results",
    )

    args = parser.parse_args()

    run_strategy_suite(
        fixture_path=args.fixture,
        strategies_dir=args.strategies,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
