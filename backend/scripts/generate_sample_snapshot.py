#!/usr/bin/env python3
"""
Generate Real Tushare Snapshot for M3.4

Generate a frozen snapshot with real A-share data:
- 10 representative stocks
- 30 trading days (Dec 2023)
- Saved to data/tushare_snapshots/

Usage:
    export TUSHARE_TOKEN=your_token_here
    python backend/scripts/generate_sample_snapshot.py

Output:
    data/tushare_snapshots/10stocks_30days/
        metadata/
            manifest.json
            stock_list.json
            trade_calendar.json
        data/
            *.parquet (per-symbol files)
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from backend.app.tushare.snapshot_generator import SnapshotGenerator


def main():
    print("=" * 60)
    print("Generate Real Tushare Snapshot - M3.4")
    print("=" * 60)
    
    # Check token
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("\n✗ TUSHARE_TOKEN not set")
        print("\nPlease set your Tushare token:")
        print("  export TUSHARE_TOKEN=your_token_here")
        print("\nGet token at: https://tushare.pro/register")
        sys.exit(1)
    
    print(f"✓ TUSHARE_TOKEN found")
    
    # 10 representative stocks
    symbols = [
        "600519.SH",  # 贵州茅台 - 白酒龙头
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
    
    # Date range: 30 trading days in Dec 2023
    start_date = "20231201"
    end_date = "20231229"
    
    print(f"\nSnapshot configuration:")
    print(f"  Symbols: {len(symbols)}")
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Output: data/tushare_snapshots/10stocks_30days")
    
    # Create config
    config = TushareConfig(token=token)
    
    # Create client
    print(f"\nInitializing Tushare client...")
    client = TushareClient(token)
    
    # Generate snapshot
    print(f"\nGenerating snapshot (this may take a few minutes)...")
    generator = SnapshotGenerator(config, client)
    
    generator.generate_snapshot(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        snapshot_id="10stocks_30days"
    )
    
    print(f"\n" + "=" * 60)
    print("Snapshot Generation Complete")
    print("=" * 60)
    
    # Validate
    print(f"\nValidating snapshot...")
    validation_result = generator.validate_snapshot()
    
    if validation_result["status"] == "pass":
        print(f"✓ Validation passed")
        print(f"  Checks performed: {len(validation_result['checks_performed'])}")
    else:
        print(f"✗ Validation failed")
        print(f"  Errors: {len(validation_result['errors'])}")
        for error in validation_result['errors']:
            print(f"    - {error}")
        sys.exit(1)
    
    print(f"\n✓ Real snapshot ready for M3.4 backtest!")
    print(f"\nNext steps:")
    print(f"  1. Commit frozen snapshot to git")
    print(f"  2. Run backtest:")
    print(f"     python backend/scripts/run_a_share_backtest.py \\")
    print(f"       --snapshot-dir data/tushare_snapshots/10stocks_30days \\")
    print(f"       --strategy examples/strategies/m3_4_tushare_real_data.yaml \\")
    print(f"       --output output/m3_4_real")


if __name__ == "__main__":
    main()
