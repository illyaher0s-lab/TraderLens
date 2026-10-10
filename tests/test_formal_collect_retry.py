"""Required daily PIT inputs must not treat one transient empty reply as final data."""

import importlib.util
from pathlib import Path

import pandas as pd


def _module():
    path = Path(__file__).parents[1] / "scripts" / "verify_gate0_data_feasibility.py"
    spec = importlib.util.spec_from_file_location("gate0_feasibility", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _Client:
    class _Pro:
        def __init__(self):
            self.calls = 0

        def daily_basic(self, **_params):
            self.calls += 1
            if self.calls == 1:
                return pd.DataFrame()
            return pd.DataFrame({"trade_date": ["20180723"]})

    def __init__(self):
        self.config = type("Config", (), {"retry_attempts": 2, "retry_delay_seconds": 0})()
        self.pro = self._Pro()

    def _enforce_rate_limit(self):
        pass


def test_required_daily_input_retries_a_transient_empty_response():
    module = _module()
    client = _Client()

    result = module._call_formal_api(
        client,
        "daily_basic",
        allow_empty=False,
        trade_date="20180723",
    )

    assert result["trade_date"].tolist() == ["20180723"]
    assert client.pro.calls == 2


def test_stock_basic_status_partition_can_be_legitimately_empty():
    module = _module()

    assert module._formal_api_allows_empty("stock_basic") is True
    assert module._formal_api_allows_empty("daily_basic") is False
