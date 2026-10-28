from __future__ import annotations

from types import SimpleNamespace

from backend.services.card020_preflight import prepare_card020_inputs


class FakeMarket:
    manifest = {"snapshot_id": "fixture-market", "status": "downloaded_unverified_for_research_use"}
    manifest_sha256 = "a" * 64
    raw_file_hashes = (("raw/example.json", "b" * 64),)

    def validate(self):
        return SimpleNamespace(
            status="degraded",
            errors=[],
            warnings=["Fixed hashes do not authenticate provider origin."],
            checks_performed=["pinned_manifest_sha256", "raw_file_sha256", "manifest_scope"],
        )


class InvalidFakeMarket(FakeMarket):
    def validate(self):
        return SimpleNamespace(
            status="failed",
            errors=["bar OHLC integrity check failed"],
            warnings=["Fixed hashes do not authenticate provider origin."],
            checks_performed=["pinned_manifest_sha256", "raw_file_sha256", "bar_price_fields"],
        )


def test_card020_preflight_binds_existing_window_evidence_without_computing_metrics():
    market_meta = {
        "snapshot_id": "fixture-market",
        "status": "downloaded_unverified_for_research_use",
        "manifest_sha256": "A" * 64,
        "raw_file_hashes": {"raw/example.json": "B" * 64},
        "first_date": "2009-01-05",
        "last_date": "2020-12-31",
        "preheat_end_present": True,
        "preheat_sessions_through_2017_12_29": 250,
        "research_window_sessions": 750,
        "window_start_present": True,
        "window_end_present": True,
    }
    coverage_note = "closed by pre-existing Card017 official window review; reused without reopening coverage"
    dividend_meta = {
        "snapshot_id": "fixture-dividends",
        "manifest_sha256": "C" * 64,
        "raw_file_hashes": {"raw/div.json": "D" * 64},
        "raw_snapshot_status": "raw_unverified",
        "window_events": [{"ts_code": "510880.SH", "ann_date": "2018-01-01"}] * 3,
        "official_spotcheck_dates": ["2019-01-10", "2020-01-13"],
        "historical_adapter_note": "Only two official spot checks are recorded.",
        "card017_window_coverage": coverage_note,
    }
    inherited = {
        "market": market_meta,
        "dividends": dividend_meta,
        "historical_strategy_metrics_computed": False,
    }

    prepared = prepare_card020_inputs(
        fixed_input_loader=lambda: (FakeMarket(), object(), dividend_meta["window_events"], inherited),
    )
    preflight = prepared["preflight"]

    assert preflight["historical_metrics_computed"] is False
    assert preflight["status"] == "passed_with_disclosed_data_limits"
    assert preflight["input_inventory"]["market"]["source_status"] == "downloaded_unverified_for_research_use"
    assert preflight["input_inventory"]["market"]["provider_origin_authenticated"] is False
    assert preflight["input_inventory"]["dividends"]["source_status"] == "raw_unverified"
    assert preflight["input_inventory"]["dividends"]["coverage_record"] == coverage_note
    assert preflight["input_inventory"]["dividends"]["window_event_count"] == 3
    assert preflight["critical_source_gaps"] == []
    assert preflight["evidence_level"] == "low"
    assert len(preflight["data_limitations"]) >= 3
    assert prepared["data_provenance"]["critical_source_gaps"] == preflight["critical_source_gaps"]
    assert prepared["data_provenance"]["data_limitations"] == preflight["data_limitations"]
    assert preflight["execution_fingerprint"]["bundle_sha256"]


def test_card020_preflight_blocks_a_real_validation_error_but_not_origin_warning():
    # Reuse a structurally complete fixed-input inventory; only validation's
    # substantive OHLC error changes between the accepted and blocked cases.
    market_meta = {
        "snapshot_id": "fixture-market", "status": "downloaded_unverified_for_research_use",
        "manifest_sha256": "A" * 64, "raw_file_hashes": {"raw/example.json": "B" * 64},
        "first_date": "2009-01-05", "last_date": "2020-12-31", "preheat_end_present": True,
        "preheat_sessions_through_2017_12_29": 250, "research_window_sessions": 750,
        "window_start_present": True, "window_end_present": True,
    }
    dividends = {
        "snapshot_id": "fixture-dividends", "manifest_sha256": "C" * 64,
        "raw_file_hashes": {"raw/div.json": "D" * 64}, "raw_snapshot_status": "raw_unverified",
        "window_events": [], "official_spotcheck_dates": [], "historical_adapter_note": "limited checks",
        "card017_window_coverage": "closed by pre-existing review",
    }
    inherited = {"market": market_meta, "dividends": dividends, "historical_strategy_metrics_computed": False}

    prepared = prepare_card020_inputs(
        fixed_input_loader=lambda: (InvalidFakeMarket(), object(), [], inherited),
    )

    assert prepared["preflight"]["status"] == "blocked"
    assert prepared["preflight"]["critical_source_gaps"] == [
        "Gate001 market validation error: bar OHLC integrity check failed",
        "Gate001 market validation failed.",
    ]
