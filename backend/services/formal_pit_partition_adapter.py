"""Formal PIT Partition Adapter - Task 3B Corrective.

从正式 PIT 分区加载 DailyStatus 和 DailyBar。
只读取 execution_date 分区，禁止未来数据泄漏。
"""
from __future__ import annotations

import json
import hashlib
from collections import OrderedDict
from datetime import date
import math
from numbers import Real
from pathlib import Path, PurePosixPath, PureWindowsPath

import pyarrow.parquet as pq
import pyarrow as pa

from contracts.stable import DailyBar, DailyStatus
from backend.services.v3_b5_bundle import resolve_formal_input_bindings
from scripts.verify_shsz_common_trade_calendar import (
    EXPECTED_COMMON_FIRST,
    EXPECTED_COMMON_LAST,
    EXPECTED_COMMON_OPEN_COUNT,
    EXPECTED_COMMON_SHA256,
    FORMAL_REL as COMMON_CALENDAR_REL,
    verify_candidate,
)


COMMON_CALENDAR_ARTIFACT_ID = "shsz_common_trade_calendar_v1"
COMMON_CALENDAR_PARQUET = "szse_trade_cal.parquet"
COMMON_CALENDAR_PARQUET_SHA256 = "8b41168bcd1c39d52ed00f9717ba6fa5330e5b4e15de78068446abe8647f2364"
COMMON_CALENDAR_MANIFEST_SHA256 = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
COMMON_CALENDAR_DATE_SET_SHA256 = EXPECTED_COMMON_SHA256


class FormalPITPartitionAdapter:
    """从正式 PIT 分区加载 DailyStatus/DailyBar。"""
    
    def __init__(
        self,
        repo_root: Path,
        *,
        formal_input_binding: dict | None = None,
        calendar_artifact_dir: Path | None = None,
        _unbound_fixture_roots: tuple[Path, Path] | None = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        if formal_input_binding is not None and _unbound_fixture_roots is not None:
            raise ValueError("formal input binding and unbound fixture roots are mutually exclusive")
        if _unbound_fixture_roots is None:
            expected_binding = resolve_formal_input_bindings(self.repo_root)
            if formal_input_binding is not None and formal_input_binding != expected_binding:
                raise ValueError("formal input binding does not match verified snapshot/B3 artifacts")
            self.formal_input_binding = expected_binding
            self.formal_binding_verified = True
            formal_root_rel = expected_binding["b3_execution_input"]["formal_input_root_repo_relative"]
            self._formal_input_root_repo_relative = formal_root_rel
            self._indexed_input_partition_sha256 = self._load_formal_input_index(
                expected_binding["b3_execution_input"]
            )
            stock_basic_root_rel = expected_binding["stock_basic_lifecycle"]["root_repo_relative"]
            self.formal_root = (self.repo_root / Path(*PurePosixPath(formal_root_rel).parts)).resolve()
            self.stock_basic_root = (
                self.repo_root / Path(*PurePosixPath(stock_basic_root_rel).parts)
            ).resolve()
        else:
            self.formal_input_binding = None
            self.formal_binding_verified = False
            self._formal_input_root_repo_relative = None
            self._indexed_input_partition_sha256 = {}
            self.formal_root = Path(_unbound_fixture_roots[0]).resolve()
            self.stock_basic_root = Path(_unbound_fixture_roots[1]).resolve()
        membership_id = (
            self.formal_input_binding["membership"]["id"]
            if self.formal_input_binding is not None
            else "pims_traderlens_v2_shsz_sw2021_pit_005"
        )
        self.membership_root = self.repo_root / "data/pit/pit_membership_snapshots" / membership_id
        
        # Production uses the independently verified SH/SZ common calendar.  The
        # legacy formal-calendar path remains available only for old temporary
        # fixtures that do not provide a calendar artifact.
        default_calendar_dir = self.repo_root / Path(*COMMON_CALENDAR_REL.split("/"))
        self.calendar_artifact_dir = (
            Path(calendar_artifact_dir) if calendar_artifact_dir is not None else default_calendar_dir
        )
        if calendar_artifact_dir is not None or default_calendar_dir.exists() or self.repo_root.resolve() == Path(__file__).resolve().parents[2]:
            self._load_verified_common_calendar()
        else:
            self._load_trading_calendar()
        self._load_stock_basic()
        self._membership_intervals: dict[str, list[tuple[date, date | None]]] | None = None
        
        # Cache
        self._status_cache: dict[tuple[str, date], DailyStatus] = {}
        self._bar_cache: dict[tuple[str, date], DailyBar] = {}
        self._partition_cache: OrderedDict[tuple[str, date], dict] = OrderedDict()
        self._partition_cache_max_entries = 64
        self._liquidity_cache: OrderedDict[
            date, dict[str, tuple[str, float | None]]
        ] = OrderedDict()
        self._liquidity_cache_max_entries = 64

    @classmethod
    def for_test_fixture(
        cls,
        repo_root: Path,
        *,
        formal_input_root: Path,
        stock_basic_root: Path | None = None,
        calendar_artifact_dir: Path | None = None,
    ) -> "FormalPITPartitionAdapter":
        """Open synthetic partitions for tests; such an adapter is never formal-bound."""
        input_root = Path(formal_input_root)
        lifecycle_root = Path(stock_basic_root) if stock_basic_root is not None else input_root / "stock_basic"
        return cls(
            repo_root,
            calendar_artifact_dir=calendar_artifact_dir,
            _unbound_fixture_roots=(input_root, lifecycle_root),
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _sha256_bytes(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    def _repo_relative_path(self, raw_path: object, *, label: str) -> tuple[Path, str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{label} path is missing")
        normalized = raw_path.replace("\\", "/")
        posix = PurePosixPath(normalized)
        windows = PureWindowsPath(raw_path)
        if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or ":" in normalized:
            raise ValueError(f"{label} path is not repository-relative")
        candidate = self.repo_root.joinpath(*posix.parts)
        current = self.repo_root
        for part in posix.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"{label} path contains a symbolic link")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError(f"{label} path escapes the repository") from exc
        return resolved, posix.as_posix()

    def _load_formal_input_index(self, b3_binding: dict) -> dict[str, str]:
        formal_root_rel = b3_binding.get("formal_input_root_repo_relative")
        root_path = PurePosixPath(formal_root_rel) if isinstance(formal_root_rel, str) else None
        expected_index_rel = (
            (root_path.parent / "input_index.json").as_posix()
            if root_path is not None
            else None
        )
        index_rel = b3_binding.get("input_index_repo_relative_path")
        if not expected_index_rel or index_rel != expected_index_rel:
            raise ValueError("B3 input-index path does not match the bound formal input root")
        index_path, _ = self._repo_relative_path(index_rel, label="B3 input index")
        expected_index_sha256 = b3_binding.get("input_index_sha256")
        if not isinstance(expected_index_sha256, str) or len(expected_index_sha256) != 64:
            raise ValueError("B3 input-index hash binding is invalid")
        actual_index_sha256 = self._sha256_file(index_path)
        sidecar = index_path.with_name(index_path.name + ".sha256")
        sidecar_fields = sidecar.read_text(encoding="utf-8").split()
        if actual_index_sha256 != expected_index_sha256 or not sidecar_fields or sidecar_fields[0] != expected_index_sha256:
            raise ValueError("B3 frozen input-index hash mismatch")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("formal_input_root_repo_relative") != formal_root_rel:
            raise ValueError("B3 input-index formal root mismatch")
        interfaces = index.get("interfaces")
        required_interfaces = {"adj_factor", "daily", "stk_limit", "stock_st", "suspend_d"}
        if not isinstance(interfaces, dict) or not required_interfaces.issubset(interfaces):
            raise ValueError("B3 input index is missing required execution interfaces")

        indexed_partitions: dict[str, str] = {}
        root_parts = PurePosixPath(formal_root_rel).parts
        for interface_name in required_interfaces:
            interface = interfaces[interface_name]
            entries = interface.get("entries") if isinstance(interface, dict) else None
            if not isinstance(entries, list):
                raise ValueError(f"B3 input-index entries are invalid: {interface_name}")
            part_count = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"B3 input-index entry is invalid: {interface_name}")
                raw_path = entry.get("path")
                normalized = raw_path.replace("\\", "/") if isinstance(raw_path, str) else ""
                parts = PurePosixPath(normalized)
                windows = PureWindowsPath(raw_path) if isinstance(raw_path, str) else PureWindowsPath()
                if (
                    not normalized
                    or parts.is_absolute()
                    or windows.is_absolute()
                    or ".." in parts.parts
                    or ":" in normalized
                    or parts.parts[: len(root_parts)] != root_parts
                    or len(parts.parts) <= len(root_parts)
                    or parts.parts[len(root_parts)] != interface_name
                ):
                    raise ValueError(f"B3 input-index path is outside its interface: {raw_path!r}")
                sha256 = entry.get("sha256")
                byte_size = entry.get("byte_size")
                if (
                    not isinstance(sha256, str)
                    or len(sha256) != 64
                    or any(character not in "0123456789abcdef" for character in sha256)
                    or isinstance(byte_size, bool)
                    or not isinstance(byte_size, int)
                    or byte_size < 0
                ):
                    raise ValueError(f"B3 input-index hash/size is invalid: {raw_path!r}")
                if parts.name != "part.parquet":
                    continue
                if len(parts.parts) != len(root_parts) + 3 or not parts.parts[-2].startswith("trade_date="):
                    raise ValueError(f"B3 execution partition path is invalid: {raw_path!r}")
                if normalized in indexed_partitions:
                    raise ValueError(f"B3 input-index partition is duplicated: {raw_path}")
                indexed_partitions[normalized] = sha256
                part_count += 1
            if part_count == 0:
                raise ValueError(f"B3 input index has no data partitions: {interface_name}")
        return indexed_partitions

    def _read_formal_partition_bytes(
        self,
        partition_name: str,
        execution_date: date,
        partition_path: Path,
    ) -> bytes | None:
        if not self.formal_binding_verified:
            return None
        date_str = execution_date.strftime("%Y%m%d")
        expected_rel = (
            f"{self._formal_input_root_repo_relative}/{partition_name}"
            f"/trade_date={date_str}/part.parquet"
        )
        if partition_path.relative_to(self.repo_root).as_posix() != expected_rel:
            raise ValueError("runtime formal partition path does not match B5-bound B3 root")
        current = self.repo_root
        for part in PurePosixPath(expected_rel).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"B3 indexed partition path contains a symbolic link: {expected_rel}")
        expected_sha256 = self._indexed_input_partition_sha256.get(expected_rel)
        if expected_sha256 is None:
            raise ValueError(f"execution partition is absent from B3 input index: {expected_rel}")
        raw = partition_path.read_bytes()
        if self._sha256_bytes(raw) != expected_sha256:
            raise ValueError(f"B3 indexed partition hash mismatch: {expected_rel}")
        return raw

    def _verify_sidecar(self, path: Path) -> None:
        sidecar = path.with_name(path.name + ".sha256")
        if not path.exists() or not sidecar.exists():
            raise FileNotFoundError(f"Membership artifact sidecar missing: {path}")
        fields = sidecar.read_text(encoding="utf-8").split()
        if not fields or fields[0] != self._sha256_file(path):
            raise ValueError(f"Membership artifact sidecar mismatch: {path}")

    def _load_membership(self) -> None:
        """Load the frozen PIT membership intervals used by v3 execution."""
        manifest_path = self.membership_root / "manifest.json"
        records_path = self.membership_root / "records.parquet"
        self._verify_sidecar(manifest_path)
        self._verify_sidecar(records_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_membership = (
            self.formal_input_binding["membership"]
            if self.formal_input_binding is not None
            else {"id": "pims_traderlens_v2_shsz_sw2021_pit_005"}
        )
        if manifest.get("snapshot_id") != expected_membership["id"]:
            raise ValueError("Unexpected PIT membership snapshot")
        records_sha256 = self._sha256_file(records_path)
        if manifest.get("records_parquet_sha256") != records_sha256:
            raise ValueError("PIT membership records hash mismatch")
        if self.formal_input_binding is not None:
            manifest_sha256 = self._sha256_file(manifest_path)
            if (
                manifest_sha256 != expected_membership["manifest_sha256"]
                or records_sha256 != expected_membership["records_sha256"]
            ):
                raise ValueError("PIT membership snapshot is not the B5-bound artifact")

        intervals: dict[str, list[tuple[date, date | None]]] = {}
        for row in pq.read_table(records_path).to_pylist():
            symbol = row.get("symbol")
            effective_from = row.get("effective_from")
            effective_to = row.get("effective_to")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Invalid PIT membership symbol")
            if not isinstance(effective_from, date):
                raise ValueError(f"Invalid PIT membership effective_from: {symbol}")
            if effective_to is not None and not isinstance(effective_to, date):
                raise ValueError(f"Invalid PIT membership effective_to: {symbol}")
            if effective_to is not None and effective_to <= effective_from:
                raise ValueError(f"Invalid PIT membership interval: {symbol}")
            intervals.setdefault(symbol, []).append((effective_from, effective_to))
        for symbol, records in intervals.items():
            records.sort(key=lambda item: item[0])
            for previous, current in zip(records, records[1:]):
                if previous[1] is None or current[0] < previous[1]:
                    raise ValueError(f"Overlapping PIT membership intervals: {symbol}")
        self._membership_intervals = intervals

    def symbols_as_of(self, as_of_date: date) -> tuple[str, ...]:
        """Return only membership symbols active at the supplied PIT date."""
        if not isinstance(as_of_date, date):
            raise TypeError("as_of_date must be a date")
        if self._membership_intervals is None:
            self._load_membership()
        active = []
        for symbol, intervals in self._membership_intervals.items():
            if any(start <= as_of_date and (end is None or as_of_date < end) for start, end in intervals):
                active.append(symbol)
        return tuple(sorted(active))

    def common_trading_dates(self, start: date, end: date) -> tuple[date, ...]:
        """Return SH/SZ common open dates in the inclusive requested range."""
        if not isinstance(start, date) or not isinstance(end, date):
            raise TypeError("start and end must be dates")
        if start > end:
            raise ValueError("start cannot be after end")
        return tuple(day for day in self._common_trading_dates if start <= day <= end)

    def get_daily_bars(self, symbol: str, end: date, n: int) -> tuple[DailyBar, ...]:
        """Read exactly n completed common-day bars ending at or before end."""
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise ValueError("n must be a positive integer")
        if not isinstance(end, date):
            raise TypeError("end must be a date")
        dates = tuple(day for day in self._common_trading_dates if day <= end)
        if len(dates) < n:
            raise ValueError(f"Insufficient completed common-day bars through {end}: requested {n}")
        return tuple(self.get_bar(symbol, day) for day in dates[-n:])

    def get_bar(self, symbol: str, date_: date) -> DailyBar:
        """Read one exact formal daily bar."""
        return self.get_daily_bar(symbol, date_)

    def get_status(self, symbol: str, date_: date) -> DailyStatus:
        """Read one exact formal daily status."""
        return self.get_daily_status(symbol, date_)

    def _load_stock_basic(self):
        """Load immutable listing/delisting dates from all formal status parts."""
        stock_basic_root = self.stock_basic_root
        expected_files = {}
        if self.formal_input_binding is not None:
            expected_files = {
                item["path"]: item["sha256"]
                for item in self.formal_input_binding["stock_basic_lifecycle"]["stock_basic_files"]
            }
        records: dict[str, tuple[date, date | None]] = {}
        for list_status in ("L", "D", "P"):
            relative_name = f"list_status={list_status}/part.parquet"
            partition_path = stock_basic_root / f"list_status={list_status}" / "part.parquet"
            if not partition_path.exists():
                raise FileNotFoundError(f"Stock basic partition not found: {partition_path}")
            expected_sha256 = expected_files.get(relative_name)
            if expected_files and self._sha256_file(partition_path) != expected_sha256:
                raise ValueError(f"Stock basic partition hash mismatch: {relative_name}")
            for row in pq.read_table(partition_path).to_pylist():
                symbol = row.get("ts_code")
                if not isinstance(symbol, str) or not symbol:
                    raise ValueError("Invalid stock basic symbol")
                if symbol in records:
                    raise ValueError(f"Duplicate stock basic symbol: {symbol}")
                list_date = self._parse_stock_date(row.get("list_date"), "list_date", symbol)
                raw_delist_date = row.get("delist_date")
                delist_date = (
                    None
                    if raw_delist_date in (None, "")
                    else self._parse_stock_date(raw_delist_date, "delist_date", symbol)
                )
                if delist_date is not None and delist_date < list_date:
                    raise ValueError(f"Delist date before list date: {symbol}")
                records[symbol] = (list_date, delist_date)
        self._stock_basic = records

    @staticmethod
    def _parse_stock_date(raw_value, field: str, symbol: str) -> date:
        if not isinstance(raw_value, str) or len(raw_value) != 8 or not raw_value.isdigit():
            raise ValueError(f"Invalid {field} for {symbol}")
        try:
            return date(int(raw_value[:4]), int(raw_value[4:6]), int(raw_value[6:8]))
        except ValueError as exc:
            raise ValueError(f"Invalid {field} for {symbol}") from exc

    def is_eligible(self, symbol: str, as_of_date: date) -> bool:
        """Return historical listing eligibility using only effective dates."""
        try:
            list_date, delist_date = self._stock_basic[symbol]
        except KeyError as exc:
            raise KeyError(f"Unknown stock basic symbol: {symbol}") from exc
        if not isinstance(as_of_date, date):
            raise TypeError("as_of_date must be a date")
        return list_date <= as_of_date and (delist_date is None or as_of_date < delist_date)

    def is_symbol_eligible(self, symbol: str, as_of_date: date) -> bool:
        return self.is_eligible(symbol, as_of_date)

    def is_delisting_risk(self, symbol: str, execution_date: date) -> bool:
        """Check daily Stock ST evidence for 2554 formal dates only.

        This is not a complete delisting history, reorganization period, or full-market
        delisting model; it only recognizes a raw ``*ST`` name in the formal Stock ST partition.
        """
        st_data = self._read_partition("stock_st", execution_date)
        if symbol not in st_data:
            return False
        name = st_data[symbol].get("name")
        if type(name) is not str or not name:
            raise ValueError(f"Invalid Stock ST name for {symbol}")
        return name.startswith("*ST")

    def _prepare_liquidity(self, execution_date: date) -> dict[str, tuple[str, float | None]]:
        cached = self._liquidity_cache.get(execution_date)
        if cached is not None:
            self._liquidity_cache.move_to_end(execution_date)
            return cached

        window = [day for day in self._common_trading_dates if day < execution_date][-20:]
        results: dict[str, tuple[str, float | None]] = {}
        if len(window) == 20:
            first_day = window[0]
            candidates = {
                symbol
                for symbol, (list_date, delist_date) in self._stock_basic.items()
                if list_date <= first_day
                and (delist_date is None or execution_date < delist_date)
            }
            totals = {symbol: 0.0 for symbol in candidates}
            faults: set[str] = set()
            for day in window:
                try:
                    suspended = self._read_partition("suspend_d", day)
                except (FileNotFoundError, OSError, KeyError, TypeError, ValueError):
                    faults.update(candidates)
                    break
                active = candidates.difference(faults, suspended)
                if not active:
                    continue
                try:
                    daily = self._read_partition("daily", day)
                except (FileNotFoundError, OSError, KeyError, TypeError, ValueError):
                    faults.update(active)
                    continue
                for symbol in active:
                    try:
                        amount = daily[symbol]["amount"]
                    except (KeyError, TypeError):
                        faults.add(symbol)
                        continue
                    if isinstance(amount, bool) or not isinstance(amount, Real):
                        faults.add(symbol)
                        continue
                    numeric = float(amount)
                    if not math.isfinite(numeric) or numeric < 0:
                        faults.add(symbol)
                        continue
                    totals[symbol] += numeric * 1000
            for symbol in candidates:
                if symbol in faults:
                    results[symbol] = ("data_fault", None)
                    continue
                average = totals[symbol] / 20
                results[symbol] = (
                    "qualified" if average >= 50_000_000 else "ineligible",
                    average,
                )

        if len(self._liquidity_cache) >= self._liquidity_cache_max_entries:
            self._liquidity_cache.popitem(last=False)
        self._liquidity_cache[execution_date] = results
        return results

    def derive_liquidity(self, symbol: str, execution_date: date) -> dict[str, object]:
        """Derive ``avg_amount_20d_shsz_common_v1`` for the V3 candidate only.

        The fixed 20-day, 50,000,000-yuan rule is not bound to an approved template
        or B3 successor. It is unavailable outside the formal source's supported
        history and never represents a complete market-liquidity qualification.
        """
        unavailable = {"status": "unavailable_ineligible", "average_amount_yuan": None}
        fault = {"status": "data_fault", "average_amount_yuan": None}
        try:
            if not self.is_eligible(symbol, execution_date):
                return unavailable
            list_date = self._stock_basic[symbol][0]
        except (KeyError, TypeError, ValueError):
            return unavailable

        window = [
            day for day in self._common_trading_dates
            if list_date <= day < execution_date
        ][-20:]
        if len(window) != 20:
            return unavailable

        cached = self._liquidity_cache.get(execution_date)
        if cached is None:
            cached = self._prepare_liquidity(execution_date)
        else:
            self._liquidity_cache.move_to_end(execution_date)
        status, average = cached.get(symbol, ("data_fault", None))
        return {"status": status, "average_amount_yuan": average}
    
    def _load_trading_calendar(self):
        """Load trade calendar from formal partition."""
        trade_cal_path = self.formal_root / "trade_cal/part.parquet"
        if not trade_cal_path.exists():
            raise FileNotFoundError(f"Trade calendar not found: {trade_cal_path}")
        
        table = pq.read_table(trade_cal_path)
        df = table.to_pandas()
        
        # Filter SSE trading days (is_open=1)
        def open_dates(exchange: str) -> set[date]:
            values = df[(df["exchange"] == exchange) & (df["is_open"] == 1)]["cal_date"]
            return {
                date(int(value[:4]), int(value[4:6]), int(value[6:8]))
                for value in values
            }
        
        # Parse cal_date (YYYYMMDD string → date)
        sse_dates = open_dates("SSE")
        szse_dates = open_dates("SZSE")
        self._trading_dates = tuple(sorted(sse_dates))
        self._common_trading_dates = tuple(sorted(sse_dates & szse_dates))

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _load_verified_common_calendar(self) -> None:
        """Load the frozen common calendar and reject any trust-chain drift."""
        calendar_dir = self.calendar_artifact_dir.resolve()
        manifest_path = calendar_dir / "manifest.json"
        parquet_path = calendar_dir / COMMON_CALENDAR_PARQUET
        manifest_sidecar = manifest_path.with_name(manifest_path.name + ".sha256")
        parquet_sidecar = parquet_path.with_name(parquet_path.name + ".sha256")
        if not calendar_dir.is_dir() or not manifest_path.is_file() or not parquet_path.is_file() or not manifest_sidecar.is_file() or not parquet_sidecar.is_file():
            raise FileNotFoundError(f"calendar artifact or sidecar missing: {calendar_dir}")

        manifest_sha = self._sha256_file(manifest_path)
        parquet_sha = self._sha256_file(parquet_path)
        if manifest_sha != COMMON_CALENDAR_MANIFEST_SHA256 and self.repo_root.resolve() == Path(__file__).resolve().parents[2]:
            raise ValueError("calendar manifest hash mismatch")
        if parquet_sha != COMMON_CALENDAR_PARQUET_SHA256 and self.repo_root.resolve() == Path(__file__).resolve().parents[2]:
            raise ValueError("calendar parquet hash mismatch")
        if manifest_sidecar.read_text(encoding="ascii").split()[0] != manifest_sha:
            raise ValueError("calendar manifest sidecar mismatch")
        if parquet_sidecar.read_text(encoding="ascii").split()[0] != parquet_sha:
            raise ValueError("calendar parquet sidecar mismatch")

        if self.repo_root.resolve() == Path(__file__).resolve().parents[2] and calendar_dir == self.repo_root.resolve() / Path(*COMMON_CALENDAR_REL.split("/")):
            try:
                verify_candidate(self.repo_root.resolve(), COMMON_CALENDAR_REL, formal_mode=True)
            except Exception as exc:
                raise ValueError(f"calendar independent verification failed: {exc}") from exc

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("calendar manifest is invalid") from exc
        if manifest.get("artifact_id") != COMMON_CALENDAR_ARTIFACT_ID or manifest.get("frozen") is not True:
            raise ValueError("calendar artifact identity mismatch")
        parquet_decl = manifest.get("parquet", {})
        if parquet_decl.get("path") != COMMON_CALENDAR_PARQUET or parquet_decl.get("sha256") != parquet_sha:
            raise ValueError("calendar parquet binding mismatch")

        table = pq.read_table(parquet_path)
        expected_schema = pa.schema([
            pa.field("exchange", pa.large_string()),
            pa.field("cal_date", pa.large_string()),
            pa.field("is_open", pa.int64()),
            pa.field("pretrade_date", pa.large_string()),
        ])
        if not table.schema.remove_metadata().equals(expected_schema):
            raise ValueError("calendar parquet schema mismatch")
        rows = table.to_pylist()
        dates = []
        seen = set()
        for row in rows:
            if set(row) != {"exchange", "cal_date", "is_open", "pretrade_date"} or row["exchange"] != "SZSE":
                raise ValueError("calendar parquet row mismatch")
            value = row["cal_date"]
            if not isinstance(value, str) or len(value) != 8 or not value.isdigit() or value in seen:
                raise ValueError("calendar date set mismatch")
            if isinstance(row["is_open"], bool) or type(row["is_open"]) is not int or row["is_open"] not in (0, 1):
                raise ValueError("calendar is_open mismatch")
            seen.add(value)
            if row["is_open"] == 1:
                dates.append(value)
        dates.sort()
        if len(dates) != EXPECTED_COMMON_OPEN_COUNT or dates[0] != EXPECTED_COMMON_FIRST or dates[-1] != EXPECTED_COMMON_LAST or hashlib.sha256(self._canonical(dates)).hexdigest() != COMMON_CALENDAR_DATE_SET_SHA256:
            raise ValueError("calendar common date-set mismatch")
        self._trading_dates = tuple(date(int(value[:4]), int(value[4:6]), int(value[6:8])) for value in dates)
        self._common_trading_dates = self._trading_dates
    
    def get_trading_dates(self) -> tuple[date, ...]:
        """返回交易日历。"""
        return self._trading_dates
    
    def _read_partition(self, partition_name: str, execution_date: date) -> dict:
        """
        读取指定分区的 execution_date 数据。

        Returns:
            For ordinary partitions, ``{ts_code: row_dict}``.  For
            ``suspend_d``, ``{ts_code: [row_dict, ...]}`` preserves all
            same-symbol same-day source rows for deterministic precedence.
        """
        # Format date as YYYYMMDD
        cache_key = (partition_name, execution_date)
        cached = self._partition_cache.get(cache_key)
        if cached is not None:
            self._partition_cache.move_to_end(cache_key)
            return cached
        date_str = execution_date.strftime("%Y%m%d")
        partition_path = self.formal_root / partition_name / f"trade_date={date_str}/part.parquet"
        
        if not partition_path.exists():
            raise FileNotFoundError(
                f"Partition not found: {partition_name}/trade_date={date_str}"
            )
        
        # Formal runtime reads the exact bytes whose hash appears in the frozen
        # B3 input index. Fixtures remain explicit and use their local files.
        indexed_bytes = self._read_formal_partition_bytes(
            partition_name,
            execution_date,
            partition_path,
        )
        pf = (
            pq.ParquetFile(pa.BufferReader(indexed_bytes))
            if indexed_bytes is not None
            else pq.ParquetFile(partition_path)
        )
        table = pf.read()
        df = table.to_pandas()
        
        # Index by ts_code.  suspend_d is the one partition where duplicate
        # same-day rows carry precedence information; never let the final
        # parquet row silently overwrite an earlier source observation.
        result = {}
        for _, row in df.iterrows():
            ts_code = row["ts_code"]
            row_dict = row.to_dict()
            if partition_name == "suspend_d":
                result.setdefault(ts_code, []).append(row_dict)
            else:
                result[ts_code] = row_dict
        if len(self._partition_cache) >= self._partition_cache_max_entries:
            self._partition_cache.popitem(last=False)
        self._partition_cache[cache_key] = result
        return result

    @staticmethod
    def _has_suspend_timing(value: object) -> bool:
        """Return whether the source contains a non-empty timing string."""
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _validate_daily_row(symbol: str, execution_date: date, row: dict) -> None:
        """Reject invalid daily source rows before status precedence applies."""
        values = {}
        for field in ("open", "high", "low", "close", "amount", "vol"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"Invalid daily {field} type: {symbol}/{execution_date}")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric <= 0:
                raise ValueError(f"Invalid daily {field} value: {symbol}/{execution_date}")
            values[field] = numeric

        if (
            values["low"] > values["high"]
            or not values["low"] <= values["open"] <= values["high"]
            or not values["low"] <= values["close"] <= values["high"]
        ):
            raise ValueError(f"Invalid daily OHLC ordering: {symbol}/{execution_date}")

    @staticmethod
    def _suspend_reason(rows: list[dict]) -> str | None:
        """Choose a deterministic source reason with S/P ahead of R."""
        type_priority = ("S", "P", "R")
        values = {row.get("suspend_type") for row in rows}
        for suspend_type in type_priority:
            if suspend_type in values:
                return suspend_type
        unknown = sorted(value for value in values if isinstance(value, str) and value)
        return unknown[0] if unknown else None

    @staticmethod
    def _validate_suspend_types(rows: list[dict]) -> None:
        for row in rows:
            suspend_type = row.get("suspend_type")
            if suspend_type not in ("S", "P", "R"):
                raise ValueError(f"Unsupported or empty suspend_type: {suspend_type!r}")

    @classmethod
    def _resolve_suspend_precedence(
        cls, rows: list[dict], *, has_daily: bool
    ) -> tuple[bool, str | None]:
        """Resolve daily-level suspension precedence without parsing timing.

        ``R`` is a resumption observation.  ``S``/``P`` with a non-empty
        timing and a valid daily row is an intraday/cross-session observation;
        otherwise exact ``S``/``P`` remains a suspension.  Unknown source
        types are formal status faults.
        """
        cls._validate_suspend_types(rows)
        exact_rows = [
            row for row in rows
            if row.get("suspend_type") in ("S", "P")
        ]
        if exact_rows:
            if not has_daily:
                return True, cls._suspend_reason(exact_rows)
            if all(cls._has_suspend_timing(row.get("suspend_timing")) for row in exact_rows):
                return False, cls._suspend_reason(exact_rows)
            return True, cls._suspend_reason(exact_rows)
        return False, cls._suspend_reason(rows)
    
    def get_daily_status(self, symbol: str, execution_date: date) -> DailyStatus:
        """
        获取 execution_date 的 DailyStatus。
        
        Args:
            symbol: 证券代码 (e.g., "000001.SZ")
            execution_date: 执行日期
        
        Returns:
            DailyStatus
        
        Raises:
            FileNotFoundError: 分区不存在
            KeyError: 证券在该日无数据
        """
        # Check cache
        cache_key = (symbol, execution_date)
        if cache_key in self._status_cache:
            return self._status_cache[cache_key]
        
        # All status inputs are required: a missing file is not evidence of a clear status.
        suspend_data = self._read_partition("suspend_d", execution_date)
        st_data = self._read_partition("stock_st", execution_date)
        stk_limit_data = self._read_partition("stk_limit", execution_date)
        daily_data = self._read_partition("daily", execution_date)

        daily_row = daily_data.get(symbol)
        if daily_row is not None:
            self._validate_daily_row(symbol, execution_date, daily_row)
            limit_row = stk_limit_data.get(symbol)
            if limit_row is None:
                raise KeyError(f"Symbol {symbol} not found in stock limit partition for {execution_date}")
            for field in ("up_limit", "down_limit"):
                value = limit_row.get(field)
                if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)) or float(value) <= 0:
                    raise ValueError(f"Invalid stock limit {field}: {symbol}/{execution_date}")
        
        # Resolve suspension from all same-symbol rows, rather than partition
        # row order.  A daily row is considered usable only for the narrow
        # R/non-empty-timing precedence above.
        suspend_rows = suspend_data.get(symbol, [])
        is_suspended, suspend_reason = self._resolve_suspend_precedence(
            suspend_rows, has_daily=symbol in daily_data
        )
        if symbol not in daily_data and not is_suspended:
            if suspend_rows and all(row.get("suspend_type") == "R" for row in suspend_rows):
                raise ValueError(
                    f"Formal status fault: R-only suspend_d without daily: {symbol}/{execution_date}"
                )
            raise KeyError(f"Symbol {symbol} not found in daily partition for {execution_date}")
        
        # Build DailyStatus
        is_st = symbol in st_data
        
        # Limit up/down: 开盘价 == 涨停价/跌停价（日线开盘成交边界）
        is_limit_up = False
        is_limit_down = False
        
        if symbol in stk_limit_data and symbol in daily_data:
            open_price = daily_data[symbol]["open"]
            up_limit = stk_limit_data[symbol]["up_limit"]
            down_limit = stk_limit_data[symbol]["down_limit"]
            
            # 判定：开盘价 == 涨停价 or 跌停价
            # 容忍浮点误差 1e-6
            if abs(open_price - up_limit) < 1e-6:
                is_limit_up = True
            if abs(open_price - down_limit) < 1e-6:
                is_limit_down = True
        
        # suspend_reason, st_type
        st_type = None
        if is_st:
            type_name = st_data[symbol].get("type_name")
            if type_name in ("ST", "*ST"):
                st_type = type_name
        
        status = DailyStatus(
            date=execution_date,
            symbol=symbol,
            is_st=is_st,
            is_suspended=is_suspended,
            is_limit_up=is_limit_up,
            is_limit_down=is_limit_down,
            suspend_reason=suspend_reason,
            st_type=st_type,
        )
        
        self._status_cache[cache_key] = status
        return status
    
    def get_daily_bar(self, symbol: str, execution_date: date) -> DailyBar:
        """
        获取 execution_date 的 DailyBar。
        
        Args:
            symbol: 证券代码
            execution_date: 执行日期
        
        Returns:
            DailyBar
        
        Raises:
            FileNotFoundError: 分区不存在
            KeyError: 证券在该日无数据
        """
        # Check cache
        cache_key = (symbol, execution_date)
        if cache_key in self._bar_cache:
            return self._bar_cache[cache_key]
        
        # Read daily partition
        daily_data = self._read_partition("daily", execution_date)
        
        if symbol not in daily_data:
            raise KeyError(f"Symbol {symbol} not found in daily partition for {execution_date}")
        
        # Read adj_factor partition (required)
        try:
            adj_factor_data = self._read_partition("adj_factor", execution_date)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"adj_factor partition missing for {execution_date}"
            )
        
        if symbol not in adj_factor_data:
            raise KeyError(f"Symbol {symbol} not found in adj_factor partition for {execution_date}")
        
        bar = self._build_daily_bar(symbol, execution_date, daily_data, adj_factor_data)
        self._bar_cache[cache_key] = bar
        return bar

    @staticmethod
    def _build_daily_bar(
        symbol: str,
        execution_date: date,
        daily_data: dict[str, dict],
        adj_factor_data: dict[str, dict],
    ) -> DailyBar:
        row = daily_data[symbol]
        FormalPITPartitionAdapter._validate_daily_row(symbol, execution_date, row)
        adj_factor = adj_factor_data[symbol]["adj_factor"]
        if (
            isinstance(adj_factor, bool)
            or not isinstance(adj_factor, Real)
            or not math.isfinite(float(adj_factor))
            or float(adj_factor) <= 0
        ):
            raise ValueError(f"Invalid adj_factor value: {symbol}/{execution_date}")
        return DailyBar(
            date=execution_date,
            symbol=symbol,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=int(row["vol"]),  # vol 是 float (手数)，转换为 int
            amount=row["amount"],
            adj_factor=adj_factor,
        )

    def get_adjusted_momentum_endpoints(
        self,
        symbols: tuple[str, ...] | list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, tuple[DailyBar, DailyBar]]:
        """Read exact momentum endpoints for many symbols from four partitions."""
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise TypeError("start_date and end_date must be dates")
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        requested = tuple(symbols)
        if any(not isinstance(symbol, str) or not symbol for symbol in requested):
            raise TypeError("symbols must contain non-empty strings")

        start_daily = self._read_partition("daily", start_date)
        start_adj_factor = self._read_partition("adj_factor", start_date)
        end_daily = self._read_partition("daily", end_date)
        end_adj_factor = self._read_partition("adj_factor", end_date)
        endpoints: dict[str, tuple[DailyBar, DailyBar]] = {}
        for symbol in requested:
            try:
                endpoints[symbol] = (
                    self._build_daily_bar(symbol, start_date, start_daily, start_adj_factor),
                    self._build_daily_bar(symbol, end_date, end_daily, end_adj_factor),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return endpoints
    
    def get_price(self, symbol: str, date_: date) -> float:
        """PriceProvider protocol: 返回收盘价。"""
        bar = self.get_daily_bar(symbol, date_)
        return bar.close
    
    def symbols(self) -> list[str]:
        """返回所有证券代码（从 _005 membership 获取更准确）。"""
        # Stub: 返回空列表，实际应从 _005 获取
        return []
