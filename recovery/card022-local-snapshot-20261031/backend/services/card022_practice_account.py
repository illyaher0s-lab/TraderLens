"""Isolated Card022 simulated account, cash journal, and observation history."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import TradeType


SHANGHAI = ZoneInfo("Asia/Shanghai")
PRACTICE_ACCOUNT_ID = "card022-510880"
STARTING_CASH_CENTS = 500_000
_ACCOUNT_TABLE = "card022_practice_accounts"
_CASH_TABLE = "card022_practice_cash_events"
_OBSERVATION_TABLE = "card022_practice_observations"


class PracticeAccountConflictError(RuntimeError):
    """The isolated practice database exists but is not safe to initialize."""


@contextmanager
def _read_only_connection(path: Path):
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def _write_connection(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _parse_recorded_at(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=SHANGHAI)
    return result.astimezone(SHANGHAI)


def _json_sha256(value: dict) -> tuple[str, str]:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest().upper()


class Card022PracticeAccountStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    def _validate_existing(self) -> dict:
        if not self.db_path.exists():
            return {"status": "not_initialized", "account_id": PRACTICE_ACCOUNT_ID}
        try:
            with _read_only_connection(self.db_path) as connection:
                tables = self._tables(connection)
                required = {_ACCOUNT_TABLE, _CASH_TABLE, _OBSERVATION_TABLE}
                if not required.issubset(tables):
                    raise PracticeAccountConflictError("现有模拟练习数据结构不完整，已保留原数据且未初始化。")
                triggers = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
                }
                required_triggers = {
                    "card022_practice_cash_events_no_update",
                    "card022_practice_cash_events_no_delete",
                    "card022_practice_observations_no_update",
                    "card022_practice_observations_no_delete",
                }
                if not required_triggers.issubset(triggers):
                    raise PracticeAccountConflictError("模拟练习数据缺少不可改写保护，已保留原数据。")
                account = connection.execute(
                    f"SELECT * FROM {_ACCOUNT_TABLE} WHERE account_id = ?",
                    (PRACTICE_ACCOUNT_ID,),
                ).fetchone()
                if account is None:
                    raise PracticeAccountConflictError("现有模拟练习数据与 Card022 账户不匹配，已保留原数据。")
                account_count = connection.execute(f"SELECT COUNT(*) FROM {_ACCOUNT_TABLE}").fetchone()[0]
                initial_event = connection.execute(
                    f"SELECT 1 FROM {_CASH_TABLE} WHERE account_id = ? AND event_type = 'initialization' AND revision = 0",
                    (PRACTICE_ACCOUNT_ID,),
                ).fetchone()
                if account_count != 1 or not initial_event:
                    raise PracticeAccountConflictError("现有模拟练习账户无法核对，已保留原数据。")
                cash_events = connection.execute(
                    f"SELECT revision, cash_delta_cents, cash_after_cents FROM {_CASH_TABLE} "
                    "WHERE account_id = ? ORDER BY revision",
                    (PRACTICE_ACCOUNT_ID,),
                ).fetchall()
                expected_cash = 0
                for index, event in enumerate(cash_events):
                    expected_cash += int(event["cash_delta_cents"])
                    if (
                        int(event["revision"]) != index
                        or expected_cash < 0
                        or int(event["cash_after_cents"]) != expected_cash
                    ):
                        raise PracticeAccountConflictError("模拟账户现金流水不连续或余额不符，已保留原数据。")
                if (
                    len(cash_events) != int(account["revision"]) + 1
                    or expected_cash != int(account["cash_cents"])
                ):
                    raise PracticeAccountConflictError("模拟账户现金余额与流水版本不符，已保留原数据。")
                return {
                    "status": "existing",
                    "account_id": account["account_id"],
                    "cash_cents": int(account["cash_cents"]),
                    "revision": int(account["revision"]),
                    "opened_at": account["opened_at"],
                }
        except PracticeAccountConflictError:
            raise
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
            raise PracticeAccountConflictError("现有模拟练习账户无法安全核对，已保留原数据。") from exc

    def get_status(self) -> dict:
        return self._validate_existing()

    def initialize(
        self,
        *,
        initialized_at: datetime | None = None,
    ) -> dict:
        if self.db_path.exists():
            return self._validate_existing()

        opened_at = initialized_at or datetime.now(SHANGHAI)
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=SHANGHAI)
        opened_at = opened_at.astimezone(SHANGHAI)
        LiveTradeDB(self.db_path)
        try:
            with _write_connection(self.db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_ACCOUNT_TABLE} (
                        account_id TEXT PRIMARY KEY,
                        initial_cash_cents INTEGER NOT NULL CHECK(initial_cash_cents >= 0),
                        cash_cents INTEGER NOT NULL CHECK(cash_cents >= 0),
                        revision INTEGER NOT NULL CHECK(revision >= 0),
                        opened_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_CASH_TABLE} (
                        event_id TEXT PRIMARY KEY,
                        account_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK(event_type IN ('initialization', 'trade', 'void')),
                        source_log_id TEXT,
                        execution_date TEXT,
                        cash_delta_cents INTEGER NOT NULL,
                        cash_after_cents INTEGER NOT NULL CHECK(cash_after_cents >= 0),
                        revision INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(account_id, revision)
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_OBSERVATION_TABLE} (
                        observation_id TEXT PRIMARY KEY,
                        market_snapshot_id TEXT,
                        account_revision INTEGER NOT NULL,
                        result_json TEXT NOT NULL,
                        result_sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS card022_practice_cash_events_no_update
                    BEFORE UPDATE ON {_CASH_TABLE}
                    BEGIN SELECT RAISE(ABORT, 'Card022 practice cash events are append-only'); END
                    """
                )
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS card022_practice_cash_events_no_delete
                    BEFORE DELETE ON {_CASH_TABLE}
                    BEGIN SELECT RAISE(ABORT, 'Card022 practice cash events are append-only'); END
                    """
                )
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS card022_practice_observations_no_update
                    BEFORE UPDATE ON {_OBSERVATION_TABLE}
                    BEGIN SELECT RAISE(ABORT, 'Card022 practice observations are immutable'); END
                    """
                )
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS card022_practice_observations_no_delete
                    BEFORE DELETE ON {_OBSERVATION_TABLE}
                    BEGIN SELECT RAISE(ABORT, 'Card022 practice observations are immutable'); END
                    """
                )
                connection.execute(
                    f"INSERT INTO {_ACCOUNT_TABLE} VALUES (?, ?, ?, 0, ?)",
                    (PRACTICE_ACCOUNT_ID, STARTING_CASH_CENTS, STARTING_CASH_CENTS, opened_at.isoformat()),
                )
                connection.execute(
                    f"INSERT INTO {_CASH_TABLE} VALUES (?, ?, 'initialization', NULL, ?, ?, ?, 0, ?)",
                    (
                        f"init_{uuid.uuid4().hex}",
                        PRACTICE_ACCOUNT_ID,
                        opened_at.date().isoformat(),
                        STARTING_CASH_CENTS,
                        STARTING_CASH_CENTS,
                        opened_at.isoformat(),
                    ),
                )
        except (sqlite3.Error, OSError) as exc:
            raise PracticeAccountConflictError("模拟练习账户初始化失败；现有文件未覆盖。") from exc
        return {
            "status": "initialized",
            "account_id": PRACTICE_ACCOUNT_ID,
            "cash_cents": STARTING_CASH_CENTS,
            "revision": 0,
            "opened_at": opened_at.isoformat(),
        }

    def account_snapshot(self, *, as_of_date: date, signal_date: date) -> dict:
        status = self._validate_existing()
        if status["status"] == "not_initialized":
            return {"status": "not_initialized"}
        with _read_only_connection(self.db_path) as connection:
            account = connection.execute(
                f"SELECT * FROM {_ACCOUNT_TABLE} WHERE account_id = ?",
                (PRACTICE_ACCOUNT_ID,),
            ).fetchone()
            if account is None:
                return {"status": "practice_account_conflict"}
            opened_at = _parse_recorded_at(account["opened_at"])
            cutoff = datetime.combine(signal_date, time(15, 0), tzinfo=SHANGHAI)
            if opened_at > cutoff:
                signal_state = None
            else:
                manual_rows = connection.execute(
                    """
                    SELECT confirmed_action, confirmed_quantity, execution_date, confirmed_at, voided_at
                    FROM execution_observation_logs
                    WHERE symbol = '510880.SH' AND trade_type = 'simulated'
                      AND record_source = 'autonomous_manual'
                      AND confirmed_execution_status IN ('executed_full', 'executed_partial')
                      AND execution_date <= ?
                    ORDER BY execution_date, confirmed_at, log_id
                    """,
                    (signal_date.isoformat(),),
                ).fetchall()
                recorded_late = [
                    row for row in manual_rows
                    if _parse_recorded_at(row["confirmed_at"]) > cutoff
                    or (row["voided_at"] and _parse_recorded_at(row["voided_at"]) > cutoff)
                ]
                if recorded_late:
                    signal_state = None
                else:
                    signal_shares = sum(
                        int(row["confirmed_quantity"] or 0)
                        * (1 if row["confirmed_action"] == "buy" else -1)
                        for row in manual_rows
                        if not row["voided_at"]
                    )
                    cash_events = connection.execute(
                        f"SELECT * FROM {_CASH_TABLE} WHERE account_id = ? AND execution_date <= ? ORDER BY revision",
                        (PRACTICE_ACCOUNT_ID, signal_date.isoformat()),
                    ).fetchall()
                    late_cash_event = any(
                        _parse_recorded_at(row["created_at"]) > cutoff for row in cash_events
                    )
                    if late_cash_event:
                        signal_state = None
                    else:
                        signal_cash_cents = sum(int(row["cash_delta_cents"]) for row in cash_events)
                        signal_state = (signal_shares, signal_cash_cents)

        ledger = LiveTradeDB(self.db_path, read_only=True)
        query = {
            "symbol": "510880.SH",
            "trade_type": TradeType.simulated,
            "record_source": "autonomous_manual",
        }
        shares = ledger.get_position_quantity(**query, execution_date=as_of_date)
        sellable = ledger.get_sellable_quantity(**query, execution_date=as_of_date)
        snapshot = {
            "status": "simulated_practice_account",
            "record_source": "autonomous_manual",
            "confirmed_by_user": True,
            "broker_verified": False,
            "trade_type": "simulated",
            "practice_account_id": PRACTICE_ACCOUNT_ID,
            "actual_shares": shares,
            "sellable_shares": sellable,
            "account_cash_cny": format(Decimal(int(account["cash_cents"])) / Decimal(100), ".2f"),
            "account_as_of_date": as_of_date.isoformat(),
            "account_opened_at": account["opened_at"],
            "account_revision": int(account["revision"]),
        }
        if signal_state is not None:
            signal_shares, signal_cash_cents = signal_state
            snapshot.update({
                "shares_at_signal": signal_shares,
                "account_cash_at_signal_cny": format(Decimal(signal_cash_cents) / Decimal(100), ".2f"),
                "dividend_receivable_at_signal_cny": "0.00",
            })
        return snapshot

    def record_observation(self, result: dict) -> dict | None:
        account_revision = result.get("account_revision")
        if type(account_revision) is not int or not result.get("snapshot_id"):
            return None
        stored_result = dict(result)
        stored_result["snapshot_mode_at_save"] = result.get("snapshot_mode")
        serialized, digest = _json_sha256(stored_result)
        observation_id = f"card022_obs_{uuid.uuid4().hex}"
        created_at = datetime.now(SHANGHAI).isoformat(timespec="microseconds")
        with _write_connection(self.db_path) as connection:
            connection.execute(
                f"""
                INSERT INTO {_OBSERVATION_TABLE} (
                    observation_id, market_snapshot_id, account_revision,
                    result_json, result_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (observation_id, result["snapshot_id"], account_revision, serialized, digest, created_at),
            )
        return {
            "practice_observation_id": observation_id,
            "practice_observation_sha256": digest,
            "practice_observation_created_at": created_at,
        }

    def get_observation(self, observation_id: str) -> dict | None:
        if (
            not self.db_path.exists()
            or not isinstance(observation_id, str)
            or not observation_id.startswith("card022_obs_")
        ):
            return None
        try:
            with _read_only_connection(self.db_path) as connection:
                if _OBSERVATION_TABLE not in self._tables(connection):
                    return None
                row = connection.execute(
                    f"SELECT * FROM {_OBSERVATION_TABLE} WHERE observation_id = ?",
                    (observation_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PracticeAccountConflictError("已保存的模拟账户观察无法安全读取。") from exc
        if row is None:
            return None
        try:
            result = json.loads(row["result_json"])
            _serialized, digest = _json_sha256(result)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise PracticeAccountConflictError("已保存的模拟账户观察格式无法核验。") from exc
        if digest != row["result_sha256"]:
            raise PracticeAccountConflictError("已保存的模拟账户观察哈希无法核验。")
        if result.get("account_revision") != int(row["account_revision"]):
            raise PracticeAccountConflictError("已保存的模拟账户观察版本无法核验。")
        result.update({
            "practice_observation_id": row["observation_id"],
            "practice_observation_sha256": row["result_sha256"],
            "practice_observation_created_at": row["created_at"],
            "snapshot_mode": "saved_practice_observation",
            "snapshot_historical": True,
        })
        return result

    def list_cash_events(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        with _read_only_connection(self.db_path) as connection:
            if _CASH_TABLE not in self._tables(connection):
                return []
            rows = connection.execute(
                f"SELECT * FROM {_CASH_TABLE} WHERE account_id = ? ORDER BY revision DESC",
                (PRACTICE_ACCOUNT_ID,),
            ).fetchall()
        return [dict(row) for row in rows]
