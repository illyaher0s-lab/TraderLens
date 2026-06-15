"""
回测引擎 (MVP 简化版)

职责：
- 逐日回测策略（防未来函数）
- 基于技术指标生成买卖信号
- 计算回测指标（收益率、夏普、回撤、胜率）

简化假设（MVP）：
- 固定仓位 100%（全仓买入）
- 不考虑手续费和滑点
- 按日回测（每日收盘计算信号，次日开盘执行）
- 单次交易（买入后持有到卖出信号）

Phase 3+ 优化：
- 支持分批建仓
- 加入手续费和滑点
- 支持多品种组合回测
"""

import pandas as pd
import numpy as np
from typing import Literal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def calculate_ma(df: pd.DataFrame, window: int) -> pd.Series:
    """计算移动平均线"""
    return df['close'].rolling(window=window).mean()


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 RSI 指标"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_volume_surge(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """计算成交量放大倍数（相对于均量）"""
    avg_volume = df['volume'].rolling(window=window).mean()
    return df['volume'] / avg_volume


def generate_signals(df: pd.DataFrame, strategy_profile: Literal["trend", "growth", "value"]) -> pd.DataFrame:
    """
    生成买卖信号
    
    策略逻辑（基于 trade_plan_tool）：
    - 买入：MA20 上穿 MA60 + RSI < 70 + 成交量放大
    - 卖出：MA20 下穿 MA60 或 RSI > 70
    
    Returns:
        包含 signal 列的 DataFrame：1=买入, -1=卖出, 0=持有
    """
    df = df.copy()
    
    # 计算技术指标
    df['ma20'] = calculate_ma(df, 20)
    df['ma60'] = calculate_ma(df, 60)
    df['rsi'] = calculate_rsi(df, 14)
    df['volume_surge'] = calculate_volume_surge(df, 20)
    
    # 初始化信号列
    df['signal'] = 0
    
    # 买入信号：金叉 + RSI 未超买 + 成交量放大
    golden_cross = (df['ma20'] > df['ma60']) & (df['ma20'].shift(1) <= df['ma60'].shift(1))
    rsi_ok = df['rsi'] < 70
    volume_ok = df['volume_surge'] > 1.5
    
    buy_signal = golden_cross & rsi_ok & volume_ok
    df.loc[buy_signal, 'signal'] = 1
    
    # 卖出信号：死叉 或 RSI 超买
    death_cross = (df['ma20'] < df['ma60']) & (df['ma20'].shift(1) >= df['ma60'].shift(1))
    rsi_overbought = df['rsi'] > 70
    
    sell_signal = death_cross | rsi_overbought
    df.loc[sell_signal, 'signal'] = -1
    
    return df


def run_backtest(
    df: pd.DataFrame,
    strategy_profile: Literal["trend", "growth", "value"],
    initial_capital: float = 100000.0
) -> dict:
    """
    运行回测
    
    Args:
        df: 包含 OHLCV 的 DataFrame（必须有 date, open, high, low, close, volume）
        strategy_profile: 策略类型（trend/growth/value）
        initial_capital: 初始资金
    
    Returns:
        回测结果字典
    """
    
    # 生成信号
    df = generate_signals(df, strategy_profile)
    
    # 初始化回测变量
    capital = initial_capital
    position = 0  # 持仓数量
    trades = []  # 交易记录
    equity_curve = []  # 权益曲线
    
    # 逐日回测
    for i in range(len(df)):
        row = df.iloc[i]
        date = row['date'] if 'date' in df.columns else row.name
        
        # 计算当前权益
        current_equity = capital + position * row['close']
        equity_curve.append({
            'date': date,
            'equity': current_equity,
            'capital': capital,
            'position': position,
            'price': row['close']
        })
        
        # 执行信号（使用次日开盘价，防止未来函数）
        if i < len(df) - 1:
            next_open = df.iloc[i + 1]['open']
            
            # 买入信号 且 当前无持仓
            if row['signal'] == 1 and position == 0:
                shares = int(capital / next_open)
                if shares > 0:
                    cost = shares * next_open
                    capital -= cost
                    position = shares
                    trades.append({
                        'date': date,
                        'type': 'buy',
                        'price': next_open,
                        'shares': shares,
                        'cost': cost
                    })
            
            # 卖出信号 且 当前有持仓
            elif row['signal'] == -1 and position > 0:
                revenue = position * next_open
                capital += revenue
                trades.append({
                    'date': date,
                    'type': 'sell',
                    'price': next_open,
                    'shares': position,
                    'revenue': revenue,
                    'profit': revenue - trades[-1]['cost'] if trades and trades[-1]['type'] == 'buy' else 0
                })
                position = 0
    
    # 最终权益（如果还持仓，按最后收盘价平仓）
    final_price = df.iloc[-1]['close']
    final_equity = capital + position * final_price
    
    # 计算回测指标
    total_return = (final_equity - initial_capital) / initial_capital
    
    # 最大回撤
    equity_series = pd.Series([e['equity'] for e in equity_curve])
    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 胜率和交易次数
    completed_trades = [t for t in trades if t['type'] == 'sell']
    trade_count = len(completed_trades)
    win_count = len([t for t in completed_trades if t.get('profit', 0) > 0])
    win_rate = win_count / trade_count if trade_count > 0 else 0.0
    
    # 夏普比率（简化计算：年化收益 / 年化波动）
    if len(equity_series) > 1:
        returns = equity_series.pct_change().dropna()
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)  # 年化
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0
    
    result = {
        'initial_capital': initial_capital,
        'final_equity': final_equity,
        'total_return': total_return,
        'total_return_pct': total_return * 100,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': max_drawdown * 100,
        'win_rate': win_rate,
        'trade_count': trade_count,
        'trades': trades,
        'equity_curve': equity_curve,
        'start_date': df.iloc[0]['date'] if 'date' in df.columns else str(df.index[0]),
        'end_date': df.iloc[-1]['date'] if 'date' in df.columns else str(df.index[-1]),
    }
    
    logger.info(f"Backtest completed: {strategy_profile}, return={total_return:.2%}, sharpe={sharpe_ratio:.2f}, max_dd={max_drawdown:.2%}, trades={trade_count}")
    
    return result
