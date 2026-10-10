"""Task 3 RED boundary for v3 daily portfolio observations.

The current B4 result is intentionally final-snapshot-only.  These tests make
the missing comparison input explicit while preserving the valid B4 event
identity checks.
"""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

import pytest

from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.v3_b5_observation import _canonical, _sha_bytes
from scripts.run_v3_b5_instrumented_is_once import (
    _source_hashes,
    _validate_required_producer_source_hashes,
)


ROOT = Path(__file__).resolve().parents[1]
EVENT_PATH = ROOT / "data/pit/v3_b4_is_results/20960e9fd15cdb44/event_result.json"


class V3B5ObservationBoundaryTests(unittest.TestCase):
    def _load_current_event(self) -> tuple[dict, EventBacktestResult]:
        payload = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
        return payload, EventBacktestResult.model_validate(payload)

    def test_required_producer_sources_are_explicit_and_missing_wrapper_fails_loud(self):
        hashes = _source_hashes(ROOT)
        self.assertEqual(
            hashes["scripts/run_v3_b4_is_once.py"],
            _sha_bytes((ROOT / "scripts/run_v3_b4_is_once.py").read_bytes()),
        )
        self.assertEqual(
            hashes["backend/services/v3_b5_observation.py"],
            _sha_bytes((ROOT / "backend/services/v3_b5_observation.py").read_bytes()),
        )
        missing = {key: value for key, value in hashes.items() if key != "scripts/run_v3_b4_is_once.py"}
        with pytest.raises(ValueError, match="required producer source hash missing"):
            _validate_required_producer_source_hashes(
                {"producer_source_hashes": missing}, repo_root=ROOT
            )

    def test_tampered_wrapper_hash_fails_loud_and_changes_artifact_identity(self):
        hashes = _source_hashes(ROOT)
        valid_manifest = {"producer_source_hashes": hashes}
        tampered_hashes = dict(hashes)
        tampered_hashes["scripts/run_v3_b4_is_once.py"] = "0" * 64
        tampered_manifest = {"producer_source_hashes": tampered_hashes}
        self.assertNotEqual(
            _sha_bytes(_canonical(valid_manifest)),
            _sha_bytes(_canonical(tampered_manifest)),
        )
        with pytest.raises(ValueError, match="producer source hash mismatch"):
            _validate_required_producer_source_hashes(
                tampered_manifest, repo_root=ROOT
            )

    def test_current_b4_identity_is_valid_but_final_only_event_is_rejected(self):
        payload, event = self._load_current_event()

        self.assertEqual(
            event.result_id,
            "v3-result:6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111:2025-06-27:2026-03-19",
        )
        self.assertEqual(event.strategy_revision_id, "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc")
        self.assertEqual(event.protocol_snapshot_id, "6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111")
        self.assertEqual(len(event.fills), 124)
        self.assertEqual(len(event.order_intents), 136)
        self.assertEqual(len(event.future_violations), 0)
        self.assertNotIn("daily_portfolio_observations", payload)

        # RED: the authorized observation admission boundary does not exist yet.
        from backend.services.v3_b5_observation import (  # noqa: F401
            validate_event_for_daily_comparison,
        )

        decision = validate_event_for_daily_comparison(payload)
        self.assertEqual(decision["status"], "invalid")
        self.assertEqual(decision["reason"], "daily_portfolio_observations_missing")

    def test_required_observation_fields_and_is_cutoff_are_explicit(self):
        from backend.services.v3_b5_observation import (  # noqa: F401
            DAILY_OBSERVATION_FIELDS,
            validate_observation_payload,
        )

        self.assertEqual(
            DAILY_OBSERVATION_FIELDS,
            (
                "date",
                "cash",
                "portfolio_value",
                "gross_exposure",
                "net_exposure",
                "positions_value",
                "daily_return",
                "position_values_by_symbol",
            ),
        )
        validate_observation_payload(
            [
                {
                    "date": "2025-06-27",
                    "cash": 100.0,
                    "portfolio_value": 100.0,
                    "gross_exposure": 0.0,
                    "net_exposure": 0.0,
                    "positions_value": 0.0,
                    "daily_return": 0.0,
                    "position_values_by_symbol": {},
                }
            ],
            allowed_end=date(2026, 3, 19),
        )

    def test_observation_arithmetic_and_daily_return_are_recomputed(self):
        from backend.services.v3_b5_observation import validate_observation_payload

        rows = [
            {
                "date": "2025-06-27",
                "cash": 90.0,
                "portfolio_value": 100.0,
                "gross_exposure": 10.0,
                "net_exposure": 10.0,
                "positions_value": 10.0,
                "daily_return": 0.0,
                "position_values_by_symbol": {"000001.SZ": 10.0},
            },
            {
                "date": "2025-06-30",
                "cash": 88.0,
                "portfolio_value": 110.0,
                "gross_exposure": 22.0,
                "net_exposure": 22.0,
                "positions_value": 22.0,
                "daily_return": 0.1,
                "position_values_by_symbol": {"000001.SZ": 22.0},
            },
        ]
        result = validate_observation_payload(
            rows,
            allowed_end=date(2026, 3, 19),
            expected_dates=(date(2025, 6, 27), date(2025, 6, 30)),
        )
        assert result["status"] == "valid"
        assert result["observation_count"] == 2

    def test_observation_rejects_duplicate_gap_future_and_arithmetic_errors(self):
        from backend.services.v3_b5_observation import validate_observation_payload

        base = {
            "date": "2025-06-27",
            "cash": 90.0,
            "portfolio_value": 100.0,
            "gross_exposure": 10.0,
            "net_exposure": 10.0,
            "positions_value": 10.0,
            "daily_return": 0.0,
            "position_values_by_symbol": {"000001.SZ": 10.0},
        }
        with pytest.raises(ValueError, match="duplicate"):
            validate_observation_payload(
                [base, dict(base)], allowed_end=date(2026, 3, 19)
            )
        with pytest.raises(ValueError, match="date sequence"):
            validate_observation_payload(
                [base],
                allowed_end=date(2026, 3, 19),
                expected_dates=(date(2025, 6, 27), date(2025, 6, 30)),
            )
        future = dict(base, date="2026-03-20")
        with pytest.raises(ValueError, match="future/OOS"):
            validate_observation_payload([future], allowed_end=date(2026, 3, 19))
        mismatch = dict(base, portfolio_value=101.0)
        with pytest.raises(ValueError, match="portfolio arithmetic"):
            validate_observation_payload([mismatch], allowed_end=date(2026, 3, 19))
        negative = dict(base, cash=-1.0)
        with pytest.raises(ValueError, match="non-negative"):
            validate_observation_payload([negative], allowed_end=date(2026, 3, 19))


if __name__ == "__main__":
    unittest.main()
