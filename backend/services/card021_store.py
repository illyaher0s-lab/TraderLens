"""Append-only, market-only Card021 observation snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid


_SNAPSHOT_ID = re.compile(r"^card021_[0-9a-f]{32}$")
_INPUT_FIELDS = {
    "trade_cal": ("cal_date", "is_open"),
    "fund_daily": ("ts_code", "trade_date", "open", "close", "vol"),
    "fund_adj": ("ts_code", "trade_date", "adj_factor"),
    "signal_window": ("trade_date", "close", "adj_factor"),
    "anchor_market_rows": ("trade_date", "close", "vol", "adj_factor"),
    "fund_div": (
        "ts_code", "ann_date", "imp_anndate", "ex_date", "pay_date", "div_proc", "div_cash",
    ),
}
_RESULT_FIELDS = frozenset({
    "status", "failure_code", "failure_message", "strategy_id", "protocol_revision", "symbol",
    "evidence_level", "signal_date", "supersedes_signal_date", "latest_market_data_date",
    "retrieved_at", "signal_window_start", "signal_window_end", "valid_adjusted_close_count",
    "signal_volatility", "target_weight", "target_weight_percentage", "target_price_raw_cny",
    "model_account_cash_cny", "model_reference_shares", "action_decision",
    "earliest_attempt_after_signal_date", "first_attempt_status", "next_possible_attempt_date",
    "target_valid_until", "target_validity_status", "retry_policy_status", "retry_rule",
    "adjustment_source_status", "dividend_source", "market_constraints", "source_freshness",
    "source_origin_authenticated", "provider_call_attempted", "provider_responses_received", "sources",
})
_DIVIDEND_RESULT_FIELDS = frozenset({
    "endpoint", "query_status", "row_count", "implemented_history_event_count",
    "matched_signal_window_event_count", "latest_reported_ex_date", "coverage", "used_in_signal_math",
})
_MARKET_CONSTRAINT_FIELDS = frozenset({
    "orders_submitted", "round_lot_shares", "t_plus_one", "max_daily_volume_fraction",
    "previous_session_volume_hands", "volume_capacity_shares_for_next_possible_attempt",
    "volume_capacity_source_date", "volume_capacity_status", "commission_rate",
    "minimum_commission_cny", "commission_ratio_limit",
    "minimum_order_value_for_commission_filter_cny", "other_fees",
    "suspension_and_price_limits", "execution_price",
})
_FRESHNESS_FIELDS = frozenset({
    "market_data_as_of", "calendar_coverage_through", "origin_authenticated", "dividend_coverage",
})
_SOURCE_FIELDS = frozenset({
    "source", "endpoint", "request_started_at", "received_at", "retrieved_at", "row_count",
    "provider_origin_authenticated", "response_status", "error_type",
})
_RECEIPT_FIELDS = frozenset({
    "endpoint", "query_fields", "query_params", "request_started_at", "received_at",
    "row_count", "response_status", "error_type",
})


class Card021SnapshotIntegrityError(ValueError):
    """A saved market snapshot no longer matches its recorded hashes."""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest().upper()


def _pick(value: object, allowed: frozenset | tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in allowed if key in value}


def _market_inputs(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Card021 market inputs must be an object")
    result: dict[str, list[dict]] = {}
    for name, allowed in _INPUT_FIELDS.items():
        rows = value.get(name, [])
        if not isinstance(rows, list):
            raise ValueError(f"Card021 {name} inputs must be a list")
        result[name] = [_pick(row, allowed) for row in rows if isinstance(row, dict)]
    return result


def _market_result(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Card021 market result must be an object")
    result = {key: value[key] for key in _RESULT_FIELDS if key in value}
    if isinstance(value.get("dividend_source"), dict):
        result["dividend_source"] = _pick(value["dividend_source"], _DIVIDEND_RESULT_FIELDS)
    if isinstance(value.get("market_constraints"), dict):
        result["market_constraints"] = _pick(value["market_constraints"], _MARKET_CONSTRAINT_FIELDS)
    if isinstance(value.get("source_freshness"), dict):
        result["source_freshness"] = _pick(value["source_freshness"], _FRESHNESS_FIELDS)
    if isinstance(value.get("sources"), list):
        result["sources"] = [_pick(source, _SOURCE_FIELDS) for source in value["sources"]]
    return result


def _receipts(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("Card021 source receipts must be a list")
    return [_pick(item, _RECEIPT_FIELDS) for item in value if isinstance(item, dict)]


def _snapshot_hash_payload(row: dict) -> dict:
    return {
        "snapshot_id": row["snapshot_id"],
        "symbol": row["symbol"],
        "strategy_id": row["strategy_id"],
        "protocol_revision": row["protocol_revision"],
        "protocol_sha256": row["protocol_sha256"],
        "protocol_verified": row["protocol_verified"],
        "implementation_sha256": row["implementation_sha256"],
        "judgment_at": row["judgment_at"],
        "received_at": row["received_at"],
        "market_input_sha256": row["market_input_sha256"],
        "market_result_sha256": row["market_result_sha256"],
        "source_receipts": row["source_receipts"],
    }


class Card021SnapshotStore:
    """Persist only whitelisted market inputs and market-derived results."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS card021_market_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL CHECK (symbol = '510880.SH'),
                    strategy_id TEXT NOT NULL,
                    protocol_revision INTEGER NOT NULL,
                    protocol_sha256 TEXT NOT NULL,
                    protocol_verified INTEGER NOT NULL CHECK (protocol_verified IN (0, 1)),
                    implementation_sha256 TEXT NOT NULL,
                    judgment_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    market_input_sha256 TEXT NOT NULL,
                    market_result_sha256 TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    market_inputs_json TEXT NOT NULL,
                    source_receipts_json TEXT NOT NULL,
                    market_result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_card021_snapshots_received
                    ON card021_market_snapshots(received_at DESC);
                CREATE TRIGGER IF NOT EXISTS card021_snapshots_no_update
                BEFORE UPDATE ON card021_market_snapshots
                BEGIN SELECT RAISE(ABORT, 'Card021 market snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS card021_snapshots_no_delete
                BEFORE DELETE ON card021_market_snapshots
                BEGIN SELECT RAISE(ABORT, 'Card021 market snapshots are immutable'); END;
                """
            )
            self.connection.commit()

    def record_snapshot(
        self,
        *,
        market_inputs: dict,
        source_receipts: list[dict],
        market_result: dict,
        protocol_sha256: str,
        protocol_verified: bool,
        implementation_sha256: str,
        judgment_at: str,
        received_at: str,
    ) -> dict:
        inputs = _market_inputs(market_inputs)
        receipts = _receipts(source_receipts)
        result = _market_result(market_result)
        if result.get("symbol", "510880.SH") != "510880.SH":
            raise ValueError("Card021 snapshot symbol mismatch")
        snapshot_id = f"card021_{uuid.uuid4().hex}"
        record = {
            "snapshot_id": snapshot_id,
            "symbol": "510880.SH",
            "strategy_id": result.get("strategy_id", "510880-vol-budget-v1"),
            "protocol_revision": result.get("protocol_revision", 3),
            "protocol_sha256": protocol_sha256,
            "protocol_verified": bool(protocol_verified),
            "implementation_sha256": implementation_sha256,
            "judgment_at": judgment_at,
            "received_at": received_at,
            "market_input_sha256": _sha256(inputs),
            "market_result_sha256": _sha256(result),
            "source_receipts": receipts,
            "market_inputs": inputs,
            "market_result": result,
        }
        record["snapshot_sha256"] = _sha256(_snapshot_hash_payload(record))
        values = (
            record["snapshot_id"], record["symbol"], record["strategy_id"],
            record["protocol_revision"], record["protocol_sha256"], int(record["protocol_verified"]),
            record["implementation_sha256"], record["judgment_at"], record["received_at"],
            record["market_input_sha256"], record["market_result_sha256"], record["snapshot_sha256"],
            _json(inputs), _json(receipts), _json(result), received_at,
        )
        with self._lock:
            self.connection.execute(
                """INSERT INTO card021_market_snapshots (
                    snapshot_id, symbol, strategy_id, protocol_revision, protocol_sha256,
                    protocol_verified, implementation_sha256, judgment_at, received_at,
                    market_input_sha256, market_result_sha256, snapshot_sha256,
                    market_inputs_json, source_receipts_json, market_result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            self.connection.commit()
        return {
            key: record[key] for key in (
                "snapshot_id", "snapshot_sha256", "market_input_sha256", "market_result_sha256",
                "protocol_sha256", "protocol_verified", "implementation_sha256", "judgment_at", "received_at",
            )
        }

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            return None
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM card021_market_snapshots WHERE snapshot_id = ?", (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        stored = dict(row)
        record = {
            "snapshot_id": stored["snapshot_id"],
            "symbol": stored["symbol"],
            "strategy_id": stored["strategy_id"],
            "protocol_revision": stored["protocol_revision"],
            "protocol_sha256": stored["protocol_sha256"],
            "protocol_verified": bool(stored["protocol_verified"]),
            "implementation_sha256": stored["implementation_sha256"],
            "judgment_at": stored["judgment_at"],
            "received_at": stored["received_at"],
            "market_input_sha256": stored["market_input_sha256"],
            "market_result_sha256": stored["market_result_sha256"],
            "snapshot_sha256": stored["snapshot_sha256"],
            "market_inputs": json.loads(stored["market_inputs_json"]),
            "source_receipts": json.loads(stored["source_receipts_json"]),
            "market_result": json.loads(stored["market_result_json"]),
        }
        if (
            _sha256(record["market_inputs"]) != record["market_input_sha256"]
            or _sha256(record["market_result"]) != record["market_result_sha256"]
            or _sha256(_snapshot_hash_payload(record)) != record["snapshot_sha256"]
        ):
            raise Card021SnapshotIntegrityError("Card021 snapshot hash mismatch")
        return record
