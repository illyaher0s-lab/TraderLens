#!/usr/bin/env python3
"""添加示例数据到观察池"""

import sys
import os
sys.path.insert(0, '/home/ubuntu/TraderLens')

from src.ui.pages.watchlist import add_to_watchlist

# 添加示例股票
stocks = [
    {
        "stock_code": "000001",
        "stock_name": "平安银行",
        "reason": "技术面良好，MA20 金叉，RSI 处于健康区间，板块表现优异",
        "strategy_profile": "trend",
        "analysis_summary": {
            "market": "震荡市，指数在 3000-3200 区间波动",
            "technicals": "MA20 金叉，RSI=55，成交量放大",
            "fundamentals": "ROE=12.5%，PE=5.8，行业排名前 20%"
        },
        "trade_plan": {
            "action": "buy",
            "entry_price": 12.50,
            "stop_loss": 11.80,
            "take_profit": 14.20,
            "position_size": 0.1
        }
    },
    {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "reason": "价值投资标的，基本面扎实，长期持有",
        "strategy_profile": "value",
        "analysis_summary": {
            "market": "震荡市",
            "technicals": "价格在 1800 附近盘整，等待突破",
            "fundamentals": "ROE=28%，净利润率 50%+，行业龙头"
        },
        "trade_plan": {
            "action": "buy",
            "entry_price": 1800.00,
            "stop_loss": 1700.00,
            "take_profit": 2000.00,
            "position_size": 0.05
        }
    },
    {
        "stock_code": "300750",
        "stock_name": "宁德时代",
        "reason": "成长股，新能源赛道龙头，营收高增长",
        "strategy_profile": "growth",
        "analysis_summary": {
            "market": "震荡市",
            "technicals": "突破前高，成交量放大",
            "fundamentals": "营收增长 80%+，毛利率稳定，市占率第一"
        },
        "trade_plan": {
            "action": "buy",
            "entry_price": 180.00,
            "stop_loss": 165.00,
            "take_profit": 210.00,
            "position_size": 0.08
        }
    }
]

print("正在添加示例数据到观察池...")

for stock in stocks:
    add_to_watchlist(
        stock_code=stock["stock_code"],
        stock_name=stock["stock_name"],
        reason=stock["reason"],
        strategy_profile=stock["strategy_profile"],
        analysis_summary=stock["analysis_summary"],
        trade_plan=stock["trade_plan"]
    )
    print(f"✅ 已添加: {stock['stock_code']} - {stock['stock_name']}")

print("\n完成！观察池现在有 3 只股票")
print("访问 http://localhost:8501 查看")
