"""
Validate Fixed Fixture Data Integrity

Check:
1. Stock identity completeness
2. Daily bars completeness and validity
3. Daily status completeness
4. Manifest trustworthiness
5. Generate validation_report.json

Usage:
    python backend/scripts/validate_fixed_fixture.py [fixture_path]
    
Example:
    python backend/scripts/validate_fixed_fixture.py tests/fixed_fixture
"""
import json
import sys
from pathlib import Path
from datetime import date, datetime

import pyarrow.parquet as pq


def validate_fixed_fixture(fixture_path: Path) -> dict:
    """
    Validate fixed fixture and return validation report.
    
    Returns:
        dict: validation report with status (pass/failed/degraded)
    """
    report = {
        "validation_timestamp": datetime.now().isoformat(),
        "fixture_path": str(fixture_path.absolute()),
        "status": "pass",  # pass / degraded / failed
        "errors": [],
        "warnings": [],
        "missing_files": [],
        "missing_fields": [],
        "invalid_rows": [],
        "suspicious_rows": [],
        "per_symbol_summary": {},
    }
    
    metadata_path = fixture_path / "metadata"
    data_path = fixture_path / "data"
    
    # Check directory structure
    if not fixture_path.exists():
        report["status"] = "failed"
        report["errors"].append(f"Fixture path does not exist: {fixture_path}")
        return report
    
    if not metadata_path.exists():
        report["status"] = "failed"
        report["errors"].append("metadata/ directory not found")
        return report
    
    if not data_path.exists():
        report["status"] = "failed"
        report["errors"].append("data/ directory not found")
        return report
    
    # 1. Validate manifest
    manifest_file = metadata_path / "manifest.json"
    if not manifest_file.exists():
        report["status"] = "failed"
        report["errors"].append("manifest.json not found")
        return report
    
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    validate_manifest(manifest, report)
    
    # 2. Validate stock_list
    stock_list_file = metadata_path / "stock_list.json"
    if not stock_list_file.exists():
        report["status"] = "failed"
        report["errors"].append("stock_list.json not found")
        return report
    
    with open(stock_list_file, "r", encoding="utf-8") as f:
        stock_list = json.load(f)
    
    validate_stock_identities(stock_list, report)
    
    # 3. Validate trade_calendar
    calendar_file = metadata_path / "trade_calendar.json"
    if not calendar_file.exists():
        report["status"] = "failed"
        report["errors"].append("trade_calendar.json not found")
        return report
    
    with open(calendar_file, "r", encoding="utf-8") as f:
        calendar = json.load(f)
    
    trading_dates = set(calendar["trading_dates"])
    
    # 4. Validate each symbol's data
    for stock in stock_list:
        symbol = stock["symbol"]
        symbol_report = validate_symbol_data(symbol, data_path, trading_dates)
        report["per_symbol_summary"][symbol] = symbol_report
        
        # Aggregate errors/warnings
        if symbol_report["errors"]:
            report["errors"].extend([f"{symbol}: {e}" for e in symbol_report["errors"]])
        if symbol_report["warnings"]:
            report["warnings"].extend([f"{symbol}: {w}" for w in symbol_report["warnings"]])
    
    # Determine final status
    if report["errors"]:
        report["status"] = "failed"
    elif report["warnings"]:
        report["status"] = "degraded"
    else:
        report["status"] = "pass"
    
    return report


def validate_manifest(manifest: dict, report: dict):
    """Validate manifest completeness and trustworthiness."""
    required_fields = [
        "dataset_name",
        "version",
        "source",
        "date_range",
        "adjust_type",
        "schema_version",
        "stock_count",
    ]
    
    for field in required_fields:
        if field not in manifest:
            report["missing_fields"].append(f"manifest.{field}")
            report["errors"].append(f"manifest missing required field: {field}")
    
    # Check fetched_at
    if "fetched_at" not in manifest or manifest["fetched_at"] is None:
        report["warnings"].append("manifest.fetched_at is null (data not yet fetched)")
    
    # Check trading_days_count
    if "trading_days_count" not in manifest or manifest["trading_days_count"] is None:
        report["warnings"].append("manifest.trading_days_count is null")
    
    # Warn if source is mock
    if manifest.get("source") == "mock":
        report["warnings"].append("Data source is 'mock' (not real market data)")


def validate_stock_identities(stock_list: list, report: dict):
    """Validate stock identity completeness."""
    required_fields = ["symbol", "name", "exchange", "current_status"]
    
    for i, stock in enumerate(stock_list):
        for field in required_fields:
            if field not in stock:
                report["missing_fields"].append(f"stock_list[{i}].{field}")
                report["errors"].append(f"stock_list[{i}] missing field: {field}")
        
        # Check exchange validity
        if stock.get("exchange") not in ["SSE", "SZSE"]:
            report["warnings"].append(f"{stock.get('symbol', f'stock[{i}]')}: invalid exchange '{stock.get('exchange')}'")
        
        # Check current_status
        if stock.get("current_status") not in ["listed", "delisted"]:
            report["warnings"].append(f"{stock.get('symbol', f'stock[{i}]')}: unexpected current_status '{stock.get('current_status')}'")


def validate_symbol_data(symbol: str, data_path: Path, trading_dates: set) -> dict:
    """Validate data for a single symbol."""
    symbol_report = {
        "symbol": symbol,
        "errors": [],
        "warnings": [],
        "daily_bars_count": 0,
        "daily_status_count": 0,
        "missing_dates": [],
        "invalid_bars": [],
    }
    
    # Check daily bars file
    daily_file = data_path / f"{symbol}_daily.parquet"
    if not daily_file.exists():
        symbol_report["errors"].append(f"daily bars file not found: {daily_file.name}")
        return symbol_report
    
    # Read daily bars
    try:
        table = pq.read_table(daily_file)
        df = table.to_pandas()
        symbol_report["daily_bars_count"] = len(df)
        
        # Validate bar fields
        required_cols = ["date", "symbol", "open", "high", "low", "close", "volume", "amount", "adj_factor"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            symbol_report["errors"].append(f"missing columns: {missing_cols}")
        
        # Validate bar constraints
        for idx, row in df.iterrows():
            # OHLC constraints
            if row["high"] < max(row["open"], row["close"], row["low"]):
                symbol_report["invalid_bars"].append(f"row {idx}: high < max(open, close, low)")
            
            if row["low"] > min(row["open"], row["close"], row["high"]):
                symbol_report["invalid_bars"].append(f"row {idx}: low > min(open, close, high)")
            
            # Non-negative volume/amount
            if row["volume"] < 0:
                symbol_report["invalid_bars"].append(f"row {idx}: negative volume")
            
            if row["amount"] < 0:
                symbol_report["invalid_bars"].append(f"row {idx}: negative amount")
            
            # Positive prices
            if row["open"] <= 0 or row["high"] <= 0 or row["low"] <= 0 or row["close"] <= 0:
                symbol_report["invalid_bars"].append(f"row {idx}: non-positive price")
        
        # Check date continuity (only warn for gaps, as suspensions are allowed)
        bar_dates = set(row.strftime("%Y-%m-%d") if hasattr(row, "strftime") else str(row) for row in df["date"])
        missing_dates = trading_dates - bar_dates
        if missing_dates:
            symbol_report["warnings"].append(f"{len(missing_dates)} trading days missing (may be suspended)")
            symbol_report["missing_dates"] = sorted(list(missing_dates))[:10]  # Report first 10
    
    except Exception as e:
        symbol_report["errors"].append(f"failed to read daily bars: {e}")
    
    # Check daily status file
    status_file = data_path / f"{symbol}_status.parquet"
    if not status_file.exists():
        symbol_report["errors"].append(f"daily status file not found: {status_file.name}")
        return symbol_report
    
    try:
        table = pq.read_table(status_file)
        df = table.to_pandas()
        symbol_report["daily_status_count"] = len(df)
        
        # Validate status fields
        required_cols = ["date", "symbol", "is_st", "is_suspended", "is_limit_up", "is_limit_down"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            symbol_report["errors"].append(f"status missing columns: {missing_cols}")
        
        # Validate boolean types
        bool_cols = ["is_st", "is_suspended", "is_limit_up", "is_limit_down"]
        for col in bool_cols:
            if col in df.columns and df[col].dtype != bool:
                symbol_report["warnings"].append(f"status.{col} is not boolean type")
    
    except Exception as e:
        symbol_report["errors"].append(f"failed to read daily status: {e}")
    
    return symbol_report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        fixture_path = Path("tests/fixed_fixture")
    else:
        fixture_path = Path(sys.argv[1])
    
    print(f"Validating fixed fixture: {fixture_path.absolute()}")
    print()
    
    report = validate_fixed_fixture(fixture_path)
    
    # Print summary
    print(f"Status: {report['status'].upper()}")
    print(f"  Errors: {len(report['errors'])}")
    print(f"  Warnings: {len(report['warnings'])}")
    print(f"  Symbols validated: {len(report['per_symbol_summary'])}")
    print()
    
    if report["errors"]:
        print("Errors:")
        for error in report["errors"][:10]:  # Show first 10
            print(f"  ✗ {error}")
        if len(report["errors"]) > 10:
            print(f"  ... and {len(report['errors']) - 10} more errors")
        print()
    
    if report["warnings"]:
        print("Warnings:")
        for warning in report["warnings"][:10]:
            print(f"  ⚠ {warning}")
        if len(report["warnings"]) > 10:
            print(f"  ... and {len(report['warnings']) - 10} more warnings")
        print()
    
    # Save report
    report_path = fixture_path / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Validation report saved to: {report_path}")
    
    # Exit code
    if report["status"] == "failed":
        sys.exit(1)
    elif report["status"] == "degraded":
        sys.exit(0)  # Warnings are OK
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
