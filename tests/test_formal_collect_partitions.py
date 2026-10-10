"""Formal collection may resume only verified immutable partitions."""

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


def test_verified_partition_is_resumable(tmp_path):
    module = _module()
    path = tmp_path / "daily" / "trade_date=20160104" / "part.parquet"
    frame = pd.DataFrame({"ts_code": ["600000.SH"], "trade_date": ["20160104"]})

    assert module._write_verified_partition(path, frame) is False
    assert module._write_verified_partition(path, frame) is True
    assert path.with_suffix(".parquet.sha256").exists()
