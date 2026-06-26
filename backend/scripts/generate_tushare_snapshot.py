#!/usr/bin/env python3
"""
Generate Tushare Snapshot - M3.2

Generate frozen snapshot from real Tushare API.
NOT run in CI - manual execution only.

Usage:
    python backend/scripts/generate_tushare_snapshot.py

Prerequisites:
    - Set TUSHARE_TOKEN environment variable
    - Ensure Tushare API access

Output:
    - data/tushare_snapshots/metadata/
    - data/tushare_snapshots/data/

Snapshot:
    - 10 stocks × 30 trading days (approximately 1 month)
    - Frozen for deterministic backtest
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.snapshot_generator import SnapshotGenerator


def main():
    """Generate 10-stock × 30-day snapshot."""
    
    print("=" * 60)
    print("Tushare Snapshot Generator - M3.2")
    print("=" * 60)
    
    # Load config from environment
    config = TushareConfig.from_env()
    
    try:
        config.ensure_token()
        print(f"✓ Tushare token configured")
    except ValueError as e:
        print(f"✗ {e}")
        print("\nPlease set TUSHARE_TOKEN environment variable:")
        print("  export TUSHARE_TOKEN='your_token_here'")
        sys.exit(1)
    
    print(f"✓ Snapshot root: {config.snapshot_root or config._default_snapshot_root()}")
    
    # 10 representative A-share stocks (diverse sectors)
    symbols = [
        "600519.SH",  # 贵州茅台 - 白酒
        "000001.SZ",  # 平安银行 - 银行
        "600036.SH",  # 招商银行 - 银行
        "000858.SZ",  # 五粮液 - 白酒
        "600276.SH",  # 恒瑞医药 - 医药
        "000333.SZ",  # 美的集团 - 家电
        "601318.SH",  # 中国平安 - 保险
        "600309.SH",  # 万华化学 - 化工
        "300750.SZ",  # 宁德时代 - 新能源
        "002475.SZ",  # 立讯精密 - 电子
    ]
    
    # Date range: last 30 trading days (approximately)
    # Note: Adjust dates based on when you run this script
    start_date = "20231201"  # YYYYMMDD
    end_date = "20231231"    # YYYYMMDD
    
    snapshot_id = "10stocks_30days_dec2023"
    
    print(f"\nSnapshot Configuration:")
    print(f"  ID: {snapshot_id}")
    print(f"  Symbols: {len(symbols)}")
    print(f"  Date range: {start_date} to {end_date}")
    
    # Confirm before proceeding
    response = input("\nProceed with snapshot generation? (y/N): ")
    if response.lower() != 'y':
        print("Aborted.")
        sys.exit(0)
    
    # Generate snapshot
    print("\n" + "=" * 60)
    print("Starting snapshot generation...")
    print("=" * 60 + "\n")
    
    generator = SnapshotGenerator(config)
    
    try:
        generator.generate_snapshot(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            snapshot_id=snapshot_id,
        )
        
        print("\n" + "=" * 60)
        print("Snapshot generation complete!")
        print("=" * 60)
        
        # Validate snapshot
        print("\nValidating snapshot...")
        result = generator.validate_snapshot()
        
        print(f"  Status: {result['status']}")
        print(f"  Checks: {len(result['checks_performed'])}")
        
        if result['errors']:
            print(f"  Errors: {len(result['errors'])}")
            for error in result['errors']:
                print(f"    - {error}")
        
        if result['warnings']:
            print(f"  Warnings: {len(result['warnings'])}")
            for warning in result['warnings']:
                print(f"    - {warning}")
        
        if result['status'] == 'pass':
            print("\n✓ Snapshot ready for use!")
        else:
            print(f"\n✗ Snapshot validation {result['status']}")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Snapshot generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
