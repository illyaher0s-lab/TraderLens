"""Deterministic current-market research candidate scanner."""
from __future__ import annotations

import hashlib
import math
import json
from datetime import date
from pathlib import Path

import pandas as pd


FORMAL_ROOT = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal")
B3_CALENDAR = Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet")
SZSE_CALENDAR = Path("data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1/szse_trade_cal.parquet")
CURRENT_ROOT = Path("data/current_market_snapshots")
FORMAL_END = date(2026, 7, 10)
WEIGHTS = {"medium_relative_strength": 0.40, "short_trend": 0.25, "liquidity": 0.20, "volatility": 0.15}


class _DataStale(Exception):
    pass


class _DataIncomplete(Exception):
    pass


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_day(value: object) -> date:
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise _DataIncomplete("invalid date")
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError as exc:
        raise _DataIncomplete("invalid date") from exc


def _rank(values: list[tuple[str, float]], descending: bool) -> dict[str, int]:
    """Exact cross_section_rank semantics: value first, symbol ascending tie-break."""
    ordered = sorted(values, key=lambda item: ((-item[1]) if descending else item[1], item[0]))
    return {symbol: rank for rank, (symbol, _) in enumerate(ordered, start=1)}


def _percentile(rank: int, count: int) -> float:
    return 1.0 if count <= 1 else (count - rank) / (count - 1)


class DailyMarketScout:
    """Read formal/current data and return research candidates, never signals."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.formal_root = self.repo_root / FORMAL_ROOT
        self.current_root = self.repo_root / CURRENT_ROOT

    def _read_verified(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            raise _DataIncomplete(f"missing:{path}")
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not sidecar.exists() or sidecar.read_text(encoding="ascii").strip() != _hash(path):
            raise _DataIncomplete(f"hash:{path}")
        return pd.read_parquet(path, engine="pyarrow")

    def _load_manifest(self) -> tuple[Path, dict, str, dict[str, Path]]:
        manifests = sorted(self.current_root.glob("as_of_date=*/manifest.json"))
        if not manifests:
            raise _DataStale("no current manifest")
        manifest_path = manifests[-1]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise _DataIncomplete("manifest parse") from exc
        if manifest.get("quality_status") != "ok" or manifest.get("gaps") != []:
            raise _DataStale("manifest quality")
        try:
            as_of = date.fromisoformat(manifest["as_of_date"])
            current_dates = [_parse_day(item) for item in manifest["common_trading_dates"]]
        except Exception as exc:
            raise _DataIncomplete("manifest dates") from exc
        if not current_dates or current_dates[-1] != as_of:
            raise _DataStale("manifest as_of")
        files: dict[str, Path] = {}
        for item in manifest.get("files", []):
            rel = item.get("path")
            if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts or ".partial" in rel:
                raise _DataIncomplete("manifest path")
            if not rel.startswith(CURRENT_ROOT.as_posix() + "/"):
                raise _DataIncomplete("manifest namespace")
            path = self.repo_root / rel
            if not path.exists() or path.stat().st_size != item.get("size") or _hash(path) != item.get("sha256"):
                raise _DataIncomplete("manifest file binding")
            files[rel] = path
        if any(path.name.endswith(".partial") for path in self.current_root.rglob("*")):
            raise _DataIncomplete("partial current file")
        return manifest_path, manifest, _hash(manifest_path), files

    def _calendar_dates(self, current_dates: list[date]) -> list[date]:
        sse = self._read_verified(self.repo_root / B3_CALENDAR)
        szse = self._read_verified(self.repo_root / SZSE_CALENDAR)
        required = {"exchange", "cal_date", "is_open"}
        if not required <= set(sse.columns) or not required <= set(szse.columns):
            raise _DataIncomplete("calendar schema")
        sse_dates = {_parse_day(row.cal_date) for row in sse.itertuples(index=False) if row.exchange == "SSE" and row.is_open == 1}
        szse_dates = {_parse_day(row.cal_date) for row in szse.itertuples(index=False) if row.exchange == "SZSE" and row.is_open == 1}
        historical = sorted(day for day in sse_dates & szse_dates if day <= FORMAL_END)
        if any(day <= FORMAL_END for day in current_dates):
            raise _DataIncomplete("current overlaps formal")
        return historical + sorted(current_dates)

    def _formal_path(self, dataset: str, day: date) -> Path:
        return self.formal_root / dataset / f"trade_date={day.strftime('%Y%m%d')}" / "part.parquet"

    def _day_frame(self, dataset: str, day: date, current_files: dict[str, Path]) -> pd.DataFrame:
        if day <= FORMAL_END:
            return self._read_verified(self._formal_path(dataset, day))
        rel = (CURRENT_ROOT / dataset / f"trade_date={day.strftime('%Y%m%d')}" / "part.parquet").as_posix()
        path = current_files.get(rel)
        if path is None:
            raise _DataIncomplete(f"current partition:{rel}")
        return pd.read_parquet(path, engine="pyarrow")

    @staticmethod
    def _index(frame: pd.DataFrame, dataset: str) -> dict[str, dict]:
        if "ts_code" not in frame.columns:
            raise _DataIncomplete(f"{dataset} schema")
        if frame["ts_code"].duplicated().any():
            if dataset != "suspend_d":
                raise _DataIncomplete(f"{dataset} duplicate")
            frame = frame.drop_duplicates("ts_code", keep="first")
        return {row["ts_code"]: row for row in frame.to_dict("records")}

    def _stock_basic(self) -> dict[str, tuple[date, date | None]]:
        records: dict[str, tuple[date, date | None]] = {}
        for status in ("L", "D", "P"):
            frame = self._read_verified(self.formal_root / f"stock_basic/list_status={status}/part.parquet")
            required = {"ts_code", "list_date", "delist_date"}
            if not required <= set(frame.columns):
                raise _DataIncomplete("stock_basic schema")
            for row in frame.to_dict("records"):
                symbol = row.get("ts_code")
                if not isinstance(symbol, str) or not symbol or symbol in records:
                    raise _DataIncomplete("stock_basic identity")
                listed = _parse_day(row.get("list_date"))
                raw_delisted = row.get("delist_date")
                delisted = None if raw_delisted in (None, "") else _parse_day(raw_delisted)
                if delisted is not None and delisted < listed:
                    raise _DataIncomplete("stock_basic dates")
                records[symbol] = (listed, delisted)
        return records

    def _hard_block(self, reason: str, snapshot_path: str | None = None, snapshot_hash: str | None = None) -> dict:
        return {
            "status": "hard_block",
            "reason": reason,
            "as_of_date": None,
            "snapshot_path": snapshot_path,
            "snapshot_hash": snapshot_hash,
            "candidate_count": 0,
            "candidates": [],
            "excluded_counts": {},
            "industry_breadth_status": "unknown",
            "candidate_is_signal": False,
        }

    def scan(self) -> dict:
        manifest_path = None
        manifest_hash = None
        try:
            manifest_path, manifest, manifest_hash, current_files = self._load_manifest()
            as_of = date.fromisoformat(manifest["as_of_date"])
            dates = self._calendar_dates([_parse_day(item) for item in manifest["common_trading_dates"]])
            if as_of not in dates or dates[-1] != as_of or len(dates) < 61:
                raise _DataStale("insufficient common history")
            d = self._day_frame("daily", as_of, current_files)
            adj = self._day_frame("adj_factor", as_of, current_files)
            suspend = self._day_frame("suspend_d", as_of, current_files)
            limits = self._day_frame("stk_limit", as_of, current_files)
            stock_st_rel = next((rel for rel in current_files if rel.endswith("/state/stock_st.parquet")), None)
            if stock_st_rel is None:
                raise _DataIncomplete("current stock_st")
            stock_st = pd.read_parquet(current_files[stock_st_rel], engine="pyarrow")
            stock_basic = self._stock_basic()
            d_index = self._index(d, "daily")
            adj_index = self._index(adj, "adj_factor")
            suspend_index = self._index(suspend, "suspend_d")
            limit_index = self._index(limits, "stk_limit")
            st_index = self._index(stock_st, "stock_st") if not stock_st.empty else {}
        except _DataStale:
            return self._hard_block("hard_block:data_stale", str(manifest_path) if manifest_path else None, manifest_hash)
        except (_DataIncomplete, OSError, ValueError, KeyError):
            return self._hard_block("hard_block:data_incomplete", str(manifest_path) if manifest_path else None, manifest_hash)

        excluded: dict[str, int] = {}
        eligible: list[str] = []
        soft_risks: dict[str, list[str]] = {}
        for symbol, row in d_index.items():
            if not isinstance(symbol, str) or not symbol.endswith((".SH", ".SZ")):
                excluded["unknown_symbol"] = excluded.get("unknown_symbol", 0) + 1
                continue
            lifecycle = stock_basic.get(symbol)
            if lifecycle is None or lifecycle[0] > as_of or (lifecycle[1] is not None and as_of >= lifecycle[1]):
                excluded["listing_ineligible"] = excluded.get("listing_ineligible", 0) + 1
                continue
            if symbol in st_index:
                excluded["stock_st"] = excluded.get("stock_st", 0) + 1
                continue
            if symbol in suspend_index:
                excluded["suspended"] = excluded.get("suspended", 0) + 1
                continue
            if symbol not in adj_index or symbol not in limit_index:
                excluded["missing_required_data"] = excluded.get("missing_required_data", 0) + 1
                continue
            required = ("open", "close", "amount")
            if not all(isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool) and math.isfinite(float(row[field])) for field in required):
                excluded["invalid_d_row"] = excluded.get("invalid_d_row", 0) + 1
                continue
            if not isinstance(adj_index[symbol].get("adj_factor"), (int, float)) or not math.isfinite(float(adj_index[symbol]["adj_factor"])):
                excluded["invalid_adj_factor"] = excluded.get("invalid_adj_factor", 0) + 1
                continue
            risks = []
            limit_row = limit_index[symbol]
            if any(abs(float(row["close"]) - float(limit_row.get(field))) <= 1e-9 for field in ("up_limit", "down_limit") if isinstance(limit_row.get(field), (int, float))):
                risks.append("limit_reached")
            soft_risks[symbol] = risks
            eligible.append(symbol)

        feature_dates = dates[-61:]
        data_by_day: dict[date, tuple[dict, dict]] = {}
        amounts_by_day: dict[date, dict] = {}
        for day in feature_dates:
            try:
                daily_index = self._index(self._day_frame("daily", day, current_files), "daily")
                adj_index_day = self._index(self._day_frame("adj_factor", day, current_files), "adj_factor")
                suspend_index_day = self._index(self._day_frame("suspend_d", day, current_files), "suspend_d")
            except (_DataIncomplete, OSError, ValueError, KeyError):
                return self._hard_block("hard_block:data_incomplete", str(manifest_path), manifest_hash)
            data_by_day[day] = (daily_index, adj_index_day)
            amounts_by_day[day] = suspend_index_day

        raw: dict[str, dict[str, float]] = {}
        for symbol in eligible:
            try:
                closes = []
                amounts = []
                for day in feature_dates:
                    daily_index, adj_index_day = data_by_day[day]
                    row = daily_index[symbol]
                    factor = adj_index_day[symbol].get("adj_factor")
                    close = row.get("close")
                    amount = row.get("amount")
                    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in (close, factor, amount)) or float(amount) < 0:
                        raise ValueError("bad symbol history")
                    closes.append(float(close) * float(factor))
                    amounts.append(0.0 if symbol in amounts_by_day[day] else float(amount) * 1000.0)
                returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
                if any(not math.isfinite(value) for value in returns):
                    raise ValueError("bad returns")
                raw[symbol] = {
                    "medium_relative_strength": closes[-1] / closes[0] - 1.0,
                    "short_trend": closes[-1] / closes[-6] - 1.0,
                    "liquidity": sum(amounts[-20:]) / 20.0,
                    "volatility": float(pd.Series(returns[-20:]).std(ddof=0)),
                }
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                excluded["insufficient_history"] = excluded.get("insufficient_history", 0) + 1

        symbols = sorted(raw)
        ranks = {
            "medium_relative_strength": _rank([(s, raw[s]["medium_relative_strength"]) for s in symbols], True),
            "short_trend": _rank([(s, raw[s]["short_trend"]) for s in symbols], True),
            "liquidity": _rank([(s, raw[s]["liquidity"]) for s in symbols], True),
            "volatility": _rank([(s, raw[s]["volatility"]) for s in symbols], False),
        }
        candidates = []
        for symbol in symbols:
            features = {name: {"raw": raw[symbol][name], "rank": ranks[name][symbol]} for name in WEIGHTS}
            score = sum(WEIGHTS[name] * _percentile(features[name]["rank"], len(symbols)) for name in WEIGHTS)
            candidates.append({
                "symbol": symbol,
                "score": score,
                "features": features,
                "status": "watch" if soft_risks[symbol] else "research_candidate",
                "reasons": ["fixed_daily_market_scout_rank"],
                "soft_risks": soft_risks[symbol],
            })
        candidates.sort(key=lambda item: (-item["score"], item["symbol"]))
        candidates = candidates[:20]
        return {
            "status": "ok",
            "reason": None,
            "as_of_date": as_of.isoformat(),
            "snapshot_path": str(manifest_path),
            "snapshot_hash": manifest_hash,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "excluded_counts": excluded,
            "industry_breadth_status": "unknown",
            "candidate_is_signal": False,
        }
