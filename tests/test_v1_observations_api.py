"""
P2-1 Observation Pool API 测试

最小测试集：验证 API 基本功能和数据状态处理逻辑
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    ObservationPosition,
    DailyObservationSignal,
    PositionLifecycleState,
    DailySignalType,
    InvalidationTrigger,
    ExplanationSource,
)
from contracts.market_data_fault import MarketDataFaultState
from datetime import datetime
import json


client = TestClient(app)


def test_observations_empty_list():
    """空列表返回 200"""
    response = client.get("/api/observations?status=open")
    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert "total" in data
    assert isinstance(data["positions"], list)
    assert data["total"] == len(data["positions"])


def test_observations_detail_not_found():
    """不存在的 position_id 返回 404"""
    response = client.get("/api/observations/nonexistent_id")
    assert response.status_code == 404


def test_observations_data_state_mapping():
    """验证 market_data_state 字段存在且正确映射"""
    # 这个测试验证 API 返回的 JSON 字段名
    # market_data_state 是合同层字段名，前端通过它判断数据状态
    
    db = LiveTradeDB("live_trade.db")
    
    # 如果有持仓，检查返回格式
    positions = db.list_open_positions()
    if len(positions) > 0:
        response = client.get("/api/observations?status=open")
        assert response.status_code == 200
        data = response.json()
        
        if len(data["positions"]) > 0:
            pos = data["positions"][0]
            
            # 验证核心字段存在
            assert "position_id" in pos
            assert "symbol" in pos
            assert "name" in pos
            assert "lifecycle_state" in pos
            
            # 验证 latest_signal 结构
            if pos["latest_signal"]:
                sig = pos["latest_signal"]
                assert "signal_type" in sig
                assert "market_data_state" in sig  # 合同层字段名
                assert sig["market_data_state"] in ["ok", "insufficient", "fault"]


def test_observations_api_contract():
    """验证 API 返回符合约定格式"""
    response = client.get("/api/observations")
    assert response.status_code == 200
    data = response.json()
    
    # 顶层结构
    assert "positions" in data
    assert "total" in data
    
    # 如果有数据，验证 position 结构
    for pos in data["positions"]:
        # 必需字段
        assert "position_id" in pos
        assert "symbol" in pos
        assert "name" in pos
        assert "entry_price" in pos
        assert "quantity" in pos
        assert "entry_thesis" in pos
        assert "lifecycle_state" in pos
        assert "opened_at" in pos
        
        # lifecycle_state 只能是 open 或 closed
        assert pos["lifecycle_state"] in ["open", "closed"]
        
        # latest_signal 可以是 null 或包含特定字段
        if pos["latest_signal"]:
            sig = pos["latest_signal"]
            assert "signal_type" in sig
            assert "as_of_date" in sig
            assert "market_data_state" in sig
