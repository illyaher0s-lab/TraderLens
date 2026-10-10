from datetime import date
from decimal import Decimal
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest


TARGET_SYMBOL = "510880.SH"
PINNED_MANIFEST_SHA256 = "C434E25E79736FD58F77A37F5B6D47A0465BAFD85DC08D06F6D6482C9EAEF9F4"


def test_market_adapter_module_exists():
    assert find_spec("strategy_core.gate001_market_adapter") is not None


def test_pinned_snapshot_maps_protocol_and_surfaces_evidence_gaps():
    from strategy_core.data_source_protocol import DataSourceValidationResult
    from strategy_core.gate001_market_adapter import Gate001MarketDataSource
    from strategy_core.trading_calendar import TradingCalendar
    from strategy_core.universe_builder import build_universe

    source = Gate001MarketDataSource()
    bars = source.get_daily_bars(TARGET_SYMBOL)
    statuses = source.get_daily_statuses(TARGET_SYMBOL)
    dates = [bar.date for bar in bars]
    metadata = source.get_metadata()
    validation = source.validate()

    assert source.symbols() == [TARGET_SYMBOL]
    assert len(bars) == len(statuses) == 2918
    assert dates == sorted(dates)
    assert dates[0] == date(2009, 1, 5)
    assert dates[-1] == date(2020, 12, 31)
    assert sum(day.year == 2009 for day in dates) == 244
    assert sum(day.year >= 2010 for day in dates) == 2674
    assert TradingCalendar(source).all_trading_dates() == dates
    assert source.get_daily_bar(TARGET_SYMBOL, dates[0]) == bars[0]
    assert source.get_daily_status(TARGET_SYMBOL, dates[0]) == statuses[0]
    assert source.get_price(TARGET_SYMBOL, dates[0]) == bars[0].close
    assert build_universe(
        SimpleNamespace(universe=SimpleNamespace(type="static_list", symbols=[TARGET_SYMBOL])),
        source,
    ) == [TARGET_SYMBOL]

    assert metadata.snapshot_id == "snapshot_20261005T002537Z"
    assert metadata.snapshot_hash == PINNED_MANIFEST_SHA256.lower()
    assert metadata.data_mode == "real_data"
    assert metadata.symbol_count == 1
    assert metadata.trading_days == 2918
    assert validation.status == "degraded"
    assert isinstance(validation, DataSourceValidationResult)
    assert validation.errors == []
    warning_text = "\n".join(validation.warnings).lower()
    assert "downloaded_unverified_for_research_use" in warning_text
    assert "derived" in warning_text and "open" in warning_text
    assert "queue" in warning_text
    assert "unit" in warning_text


def test_raw_units_and_real_adjustment_factor_are_preserved():
    from strategy_core.gate001_market_adapter import Gate001MarketDataSource

    source = Gate001MarketDataSource()
    bar = source.get_daily_bar(TARGET_SYMBOL, date(2014, 12, 31))

    assert bar.volume == 15_697_066
    assert bar.amount == pytest.approx(40_821_061.0)
    assert bar.adj_factor == pytest.approx(1.1245)


def test_opening_limit_status_uses_open_only_with_half_up_bands():
    from strategy_core.gate001_market_adapter import _derive_open_status

    day = date(2025, 1, 2)
    just_below_upper = _derive_open_status(
        TARGET_SYMBOL, day, Decimal("1.105"), Decimal("1.005")
    )
    at_upper = _derive_open_status(
        TARGET_SYMBOL, day, Decimal("1.106"), Decimal("1.005")
    )
    at_lower = _derive_open_status(
        TARGET_SYMBOL, day, Decimal("0.905"), Decimal("1.005")
    )

    assert just_below_upper.is_limit_up is False
    assert at_upper.is_limit_up is True
    assert at_lower.is_limit_down is True
    assert at_upper.is_suspended is False


def test_missing_or_invalid_critical_daily_fields_fail_loud():
    from strategy_core.gate001_market_adapter import _parse_daily_row

    row = {
        "ts_code": TARGET_SYMBOL,
        "trade_date": "20250102",
        "open": 1.0,
        "high": 1.1,
        "low": 0.9,
        "close": 1.0,
        "pre_close": 1.0,
        "vol": 100.0,
        "amount": 100.0,
    }
    parsed, status = _parse_daily_row(
        row, Decimal("1.25"), Path("synthetic.json"), 0
    )
    assert parsed.adj_factor == 1.25
    assert status.is_limit_up is False

    missing_pre_close = dict(row)
    del missing_pre_close["pre_close"]
    with pytest.raises(ValueError, match="pre_close"):
        _parse_daily_row(missing_pre_close, Decimal("1.25"), Path("synthetic.json"), 0)

    invalid_open = dict(row, open=0)
    with pytest.raises(ValueError, match="open"):
        _parse_daily_row(invalid_open, Decimal("1.25"), Path("synthetic.json"), 0)


def test_pinned_hash_verifier_rejects_tampered_content(tmp_path):
    from strategy_core.gate001_market_adapter import _verify_sha256

    path = tmp_path / "raw.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _verify_sha256(path, "0" * 64, "synthetic raw")
