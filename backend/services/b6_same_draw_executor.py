"""Narrow production same-draw executor for the B6 validation boundary.

This module owns no budget or terminal transaction.  It binds the already
verified envelope to the concrete v3 event engine, then derives the two
comparison portfolios from the same bounded source and read trace.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyarrow.parquet as pq

from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.b5_oos_types import (
    B6SameDrawOOSResult,
    B6SameDrawReadAudit,
    BaseCostResult,
    SameDrawExecutionIdentity,
    StressCostResult,
)
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_comparison import (
    BASE_COST_BPS,
    INITIAL_NAV,
    STRESS_COST_BPS,
    _FormalComparisonSource,
    build_weekly_schedule,
    control_weights,
    industry_weights,
    rebalance_fractional,
)
from backend.services.v3_b5_costs import COST_ASSUMPTIONS_HASH
from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics
from strategy_core.backtest_engine import run_event_backtest
from strategy_core.transaction_costs import calculate_transaction_costs
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec


_SUPPLEMENT_ROOT = Path("data/pit/v3_execution_semantics_supplements")
_SOURCE_INVENTORY_ID = "2fe8321a5f644b9b"
_SOURCE_INVENTORY_ROOT = Path("data/pit/v3_b5_source_inventories") / _SOURCE_INVENTORY_ID
_SOURCE_INVENTORY_SCOPE = "v3_b5_source_inventory_only"
_B5_AUTHORIZATION_SCOPE = "v3_b5_contract_fixture_only"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


class PreparedSupplementToken:
    """One-time handle for a supplement verified during worker preflight."""

    __slots__ = (
        "_repo_root",
        "_directory",
        "_token_schema_version",
        "_supplement_id",
        "_manifest_sha256",
        "_repo_relative_path",
        "_protocol_snapshot_id",
        "_strategy_revision_id",
        "_b5_bundle_id",
        "_b5_bundle_manifest_sha256",
        "_criteria_envelope_hash",
        "_source_bindings",
        "_verified_manifest_bytes_sha256",
        "_prepared_identity_sha256",
        "_manifest_bytes",
        "_frozen_verified",
        "_consumed",
    )

    def __init__(
        self,
        repo_root: Path,
        directory: Path,
        identity: Mapping[str, Any],
        manifest_bytes: bytes,
        frozen_verified: Mapping[str, Any],
    ) -> None:
        self._repo_root = repo_root
        self._directory = directory
        self._token_schema_version = identity["token_schema_version"]
        self._supplement_id = identity["supplement_id"]
        self._manifest_sha256 = identity["manifest_sha256"]
        self._repo_relative_path = identity["repo_relative_path"]
        self._protocol_snapshot_id = identity["protocol_snapshot_id"]
        self._strategy_revision_id = identity["strategy_revision_id"]
        self._b5_bundle_id = identity["b5_bundle_id"]
        self._b5_bundle_manifest_sha256 = identity["b5_bundle_manifest_sha256"]
        self._criteria_envelope_hash = identity["criteria_envelope_hash"]
        self._source_bindings = _canonical_bytes(identity["source_bindings"])
        self._verified_manifest_bytes_sha256 = identity["verified_manifest_bytes_sha256"]
        self._prepared_identity_sha256 = identity["prepared_identity_sha256"]
        self._manifest_bytes = manifest_bytes
        self._frozen_verified = _canonical_bytes(dict(frozen_verified))
        self._consumed = False

    @classmethod
    def from_verified(
        cls,
        directory: Path,
        verified: Mapping[str, Any],
        *,
        repo_root: Path,
        b5_bundle_id: str,
        b5_bundle_manifest_sha256: str,
        criteria_envelope_hash: str,
    ) -> "PreparedSupplementToken":
        repo_root = Path(repo_root).resolve()
        directory = Path(directory).resolve()
        try:
            repo_relative_path = directory.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise ValueError("prepared supplement path escapes repo root") from exc
        if not isinstance(verified, Mapping) or verified.get("status") != "verified":
            raise ValueError("prepared supplement requires a verified representation")
        manifest_path = directory / "manifest.json"
        sidecar_path = manifest_path.with_name("manifest.json.sha256")
        manifest_bytes = manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if verified.get("manifest_sha256") != manifest_sha256:
            raise ValueError("prepared supplement manifest identity mismatch")
        if not sidecar_path.is_file() or sidecar_path.read_text(encoding="utf-8").split()[0] != manifest_sha256:
            raise ValueError("prepared supplement sidecar mismatch")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        supplement_id = manifest.get("supplement_id")
        if supplement_id != directory.name or verified.get("supplement_id") != supplement_id:
            raise ValueError("prepared supplement ID mismatch")
        if manifest.get("schema_version") != "v3_execution_semantics_supplement.v2":
            raise ValueError("prepared supplement schema mismatch")
        if manifest.get("status") != "published":
            raise ValueError("prepared supplement is not published")
        protocol_snapshot_id = manifest.get("protocol", {}).get("protocol_snapshot_id")
        strategy_revision_id = manifest.get("strategy", {}).get("strategy_revision_id")
        formal_snapshot = manifest.get("data_chain", {}).get("formal_snapshot", {})
        data_snapshot_hash = formal_snapshot.get("semantic_hash")
        manifest_criteria_hash = manifest.get("criteria", {}).get("envelope_hash")
        if not all(isinstance(value, str) and value for value in (
            protocol_snapshot_id,
            strategy_revision_id,
            data_snapshot_hash,
            b5_bundle_id,
            b5_bundle_manifest_sha256,
            criteria_envelope_hash,
        )):
            raise ValueError("prepared supplement identity fields are incomplete")
        if manifest_criteria_hash != criteria_envelope_hash:
            raise ValueError("prepared supplement criteria envelope mismatch")
        for key, expected in (
            ("protocol_snapshot_id", protocol_snapshot_id),
            ("strategy_revision_id", strategy_revision_id),
            ("data_snapshot_hash", data_snapshot_hash),
        ):
            if verified.get(key) != expected:
                raise ValueError(f"prepared supplement verified {key} mismatch")
        raw_bindings = manifest.get("source_bindings")
        if not isinstance(raw_bindings, Mapping) or not raw_bindings:
            raise ValueError("prepared supplement source bindings are missing")
        source_bindings: dict[str, dict[str, str]] = {}
        for name in sorted(raw_bindings):
            binding = raw_bindings[name]
            if not isinstance(name, str) or not name or not isinstance(binding, Mapping):
                raise ValueError("prepared supplement source binding is invalid")
            if set(binding) != {"path", "sha256"}:
                raise ValueError("prepared supplement source binding contract mismatch")
            relative = binding.get("path")
            expected_sha = binding.get("sha256")
            if not isinstance(relative, str) or not relative or not isinstance(expected_sha, str):
                raise ValueError("prepared supplement source binding identity is invalid")
            source_path = (repo_root / relative).resolve()
            try:
                canonical_relative = source_path.relative_to(repo_root).as_posix()
            except ValueError as exc:
                raise ValueError("prepared supplement source binding path escapes repo root") from exc
            if canonical_relative != Path(relative).as_posix() or not source_path.is_file():
                raise ValueError("prepared supplement source binding path is invalid")
            if _sha256(source_path) != expected_sha:
                raise ValueError("prepared supplement source binding hash mismatch")
            source_bindings[name] = {"path": canonical_relative, "sha256": expected_sha}
        identity = {
            "token_schema_version": "prepared_supplement_token.v1",
            "supplement_id": supplement_id,
            "manifest_sha256": manifest_sha256,
            "repo_relative_path": repo_relative_path,
            "protocol_snapshot_id": protocol_snapshot_id,
            "strategy_revision_id": strategy_revision_id,
            "b5_bundle_id": b5_bundle_id,
            "b5_bundle_manifest_sha256": b5_bundle_manifest_sha256,
            "criteria_envelope_hash": criteria_envelope_hash,
            "source_bindings": source_bindings,
            "verified_manifest_bytes_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }
        identity["prepared_identity_sha256"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        frozen_verified = {
            "status": "verified",
            "supplement_id": supplement_id,
            "manifest_sha256": manifest_sha256,
            "protocol_snapshot_id": protocol_snapshot_id,
            "strategy_revision_id": strategy_revision_id,
            "data_snapshot_hash": data_snapshot_hash,
        }
        return cls(
            repo_root,
            directory,
            identity,
            manifest_bytes,
            frozen_verified,
        )

    @property
    def supplement_id(self) -> str:
        return self._supplement_id

    @property
    def manifest_sha256(self) -> str:
        return self._manifest_sha256

    @property
    def verified_representation(self) -> Mapping[str, Any]:
        return MappingProxyType(json.loads(self._frozen_verified.decode("utf-8")))

    @property
    def consumed(self) -> bool:
        return self._consumed

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_schema_version": self._token_schema_version,
            "supplement_id": self._supplement_id,
            "manifest_sha256": self._manifest_sha256,
            "repo_relative_path": self._repo_relative_path,
            "protocol_snapshot_id": self._protocol_snapshot_id,
            "strategy_revision_id": self._strategy_revision_id,
            "b5_bundle_id": self._b5_bundle_id,
            "b5_bundle_manifest_sha256": self._b5_bundle_manifest_sha256,
            "criteria_envelope_hash": self._criteria_envelope_hash,
            "source_bindings": json.loads(self._source_bindings.decode("utf-8")),
            "verified_manifest_bytes_sha256": self._verified_manifest_bytes_sha256,
            "prepared_identity_sha256": self._prepared_identity_sha256,
        }

    def assert_current(self) -> None:
        identity = self.to_dict()
        expected_prepared_identity = hashlib.sha256(
            _canonical_bytes({key: value for key, value in identity.items() if key != "prepared_identity_sha256"})
        ).hexdigest()
        if self._prepared_identity_sha256 != expected_prepared_identity:
            raise ValueError("prepared identity mismatch")
        current_directory = (self._repo_root / self._repo_relative_path).resolve()
        try:
            current_relative = current_directory.relative_to(self._repo_root).as_posix()
        except ValueError as exc:
            raise ValueError("prepared supplement path escapes repo root") from exc
        if current_relative != self._repo_relative_path or current_directory != self._directory:
            raise ValueError("prepared supplement path identity changed")
        manifest_path = self._directory / "manifest.json"
        sidecar_path = manifest_path.with_name("manifest.json.sha256")
        current_bytes = manifest_path.read_bytes()
        current_hash = hashlib.sha256(current_bytes).hexdigest()
        if current_hash != self._manifest_sha256 or current_bytes != self._manifest_bytes:
            raise ValueError("prepared supplement identity changed")
        if not sidecar_path.is_file() or sidecar_path.read_text(encoding="utf-8").split()[0] != self._manifest_sha256:
            raise ValueError("prepared supplement sidecar changed")
        if hashlib.sha256(current_bytes).hexdigest() != self._verified_manifest_bytes_sha256:
            raise ValueError("prepared supplement verified manifest bytes changed")
        manifest = json.loads(current_bytes.decode("utf-8"))
        if (
            manifest.get("supplement_id") != self._supplement_id
            or manifest.get("protocol", {}).get("protocol_snapshot_id") != self._protocol_snapshot_id
            or manifest.get("strategy", {}).get("strategy_revision_id") != self._strategy_revision_id
            or manifest.get("criteria", {}).get("envelope_hash") != self._criteria_envelope_hash
            or manifest.get("source_bindings") != identity["source_bindings"]
        ):
            raise ValueError("prepared supplement manifest binding changed")
        for binding in identity["source_bindings"].values():
            source_path = (self._repo_root / binding["path"]).resolve()
            try:
                relative = source_path.relative_to(self._repo_root).as_posix()
            except ValueError as exc:
                raise ValueError("prepared supplement source binding path escapes repo root") from exc
            if relative != binding["path"] or not source_path.is_file() or _sha256(source_path) != binding["sha256"]:
                raise ValueError("prepared supplement source binding changed")

    def consume(self, identity: Mapping[str, Any] | SameDrawExecutionIdentity) -> Mapping[str, Any]:
        if self._consumed:
            raise ValueError("prepared supplement token already consumed")
        if isinstance(identity, Mapping):
            identity = SameDrawExecutionIdentity.model_validate(dict(identity))
        if not isinstance(identity, SameDrawExecutionIdentity):
            raise TypeError("prepared supplement token requires same-draw identity")
        self.assert_current()
        frozen = self.verified_representation
        if (
            identity.strategy_revision_id != self._strategy_revision_id
            or identity.protocol_snapshot_id != self._protocol_snapshot_id
            or identity.b5_bundle_id != self._b5_bundle_id
            or identity.b5_bundle_manifest_sha256 != self._b5_bundle_manifest_sha256
            or identity.data_snapshot_hash != frozen["data_snapshot_hash"]
            or identity.execution_input_hash != self._manifest_sha256
        ):
            if (
                identity.b5_bundle_id != self._b5_bundle_id
                or identity.b5_bundle_manifest_sha256 != self._b5_bundle_manifest_sha256
            ):
                raise ValueError("prepared supplement B5 identity does not match envelope")
            raise ValueError("prepared supplement identity does not match envelope")
        self._consumed = True
        return frozen


class _SharedReadBoundOwner:
    """One server-owned raw adapter boundary and ordered in-memory trace."""

    def __init__(self, raw: Any, allowed_end: date) -> None:
        self._raw = raw
        self._allowed_end = allowed_end
        self._trace: list[dict[str, str]] = []
        self._max_requested_date: date | None = None
        self._future_violation_count = 0

    def _record(self, operation: str, *requested_dates: date) -> None:
        for requested_date in requested_dates:
            if not isinstance(requested_date, date):
                raise TypeError(f"{operation} requested date must be a date")
            if self._max_requested_date is None or requested_date > self._max_requested_date:
                self._max_requested_date = requested_date
            if requested_date > self._allowed_end:
                self._future_violation_count += 1
                raise ValueError(f"same-draw future read: {operation}/{requested_date}")
            self._trace.append({"operation": operation, "requested_date": requested_date.isoformat()})

    def symbols_as_of(self, as_of: date):
        self._record("membership", as_of)
        return self._raw.symbols_as_of(as_of)

    def common_trading_dates(self, start: date, end: date):
        self._record("calendar", end)
        return self._raw.common_trading_dates(start, end)

    def get_daily_bars(self, symbol: str, end: date, n: int):
        self._record("daily_bars_end", end)
        bars = tuple(self._raw.get_daily_bars(symbol, end, n))
        for bar in bars:
            self._record("daily_bar", bar.date)
        return bars

    def get_bar(self, symbol: str, day: date):
        self._record("bar", day)
        return self._raw.get_bar(symbol, day)

    def get_daily_bar(self, symbol: str, day: date):
        return self.get_bar(symbol, day)

    def get_adjusted_momentum_endpoints(self, symbols, start_day: date, end_day: date):
        self._record("momentum_start", start_day)
        self._record("momentum_end", end_day)
        reader = getattr(self._raw, "get_adjusted_momentum_endpoints", None)
        return None if reader is None else reader(tuple(symbols), start_day, end_day)

    def get_status(self, symbol: str, day: date):
        self._record("status", day)
        return self._raw.get_status(symbol, day)

    def get_daily_status(self, symbol: str, day: date):
        return self.get_status(symbol, day)

    def is_eligible(self, symbol: str, day: date):
        self._record("lifecycle", day)
        return self._raw.is_eligible(symbol, day)

    def derive_liquidity(self, symbol: str, day: date):
        self._record("liquidity", day)
        return self._raw.derive_liquidity(symbol, day)

    def market_regime_blocked(self, day: date) -> bool:
        self._record("market_regime", day)
        checker = getattr(self._raw, "market_regime_blocked", None)
        return bool(checker(day)) if checker is not None else False

    def audit(self) -> B6SameDrawReadAudit:
        return B6SameDrawReadAudit.from_trace(
            allowed_end=self._allowed_end,
            trace=self._trace,
        )


def _validate_envelope(envelope: Mapping[str, Any]) -> tuple[SameDrawExecutionIdentity, int]:
    if not isinstance(envelope, Mapping):
        raise TypeError("same-draw envelope must be a mapping")
    allowed_keys = {
        "task_id", "task_key", "protocol_snapshot_id", "strategy_revision_id",
        "reservation_id", "oos_draw_index", "identity", "prepared_supplement",
        "formal_input_binding", "authorization_binding",
    }
    unexpected = set(envelope) - allowed_keys
    if unexpected:
        raise ValueError(f"same-draw envelope contains caller-controlled fields: {sorted(unexpected)}")
    raw_identity = envelope.get("identity")
    if not isinstance(raw_identity, Mapping):
        raise ValueError("same-draw envelope identity is required")
    identity = SameDrawExecutionIdentity.model_validate(dict(raw_identity))
    if identity.result_schema_version != "b6_same_draw_oos_result.v2":
        raise ValueError("production same-draw executor requires result schema v2")
    if any(envelope.get(field) != getattr(identity, field) for field in (
        "task_id", "task_key", "protocol_snapshot_id", "strategy_revision_id"
    )):
        raise ValueError("same-draw envelope top-level identity mismatch")
    prepared_supplement = envelope.get("prepared_supplement")
    if not isinstance(prepared_supplement, PreparedSupplementToken):
        raise ValueError("same-draw envelope requires a prepared supplement token")
    if prepared_supplement.consumed:
        raise ValueError("same-draw envelope prepared supplement token is already consumed")
    from backend.services.v3_b5_bundle import (
        FORMAL_B6_PREFLIGHT_SCOPE,
        independent_verifier_identity,
    )
    from backend.services.v3_b5_types import canonical_json, sha256_bytes

    authorization = envelope.get("authorization_binding")
    if not isinstance(authorization, Mapping):
        raise ValueError("same-draw envelope B5 authorization binding is required")
    lineage = authorization.get("lineage")
    if not isinstance(lineage, Mapping):
        raise ValueError("same-draw envelope B5 lineage is required")
    expected_binding = {
        "formal_snapshot": lineage.get("formal_snapshot"),
        "b3_execution_input": lineage.get("b3_execution_input"),
        "stock_basic_lifecycle": lineage.get("stock_basic_lifecycle"),
        "membership": lineage.get("membership"),
    }
    if envelope.get("formal_input_binding") != expected_binding:
        raise ValueError("same-draw formal input binding does not match B5 lineage")
    if (
        authorization.get("authorization_scope") != FORMAL_B6_PREFLIGHT_SCOPE
        or authorization.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False
        or authorization.get("strategy_revision_id") != identity.strategy_revision_id
        or authorization.get("protocol_snapshot_id") != identity.protocol_snapshot_id
        or authorization.get("b5_bundle_id") != identity.b5_bundle_id
        or authorization.get("b5_bundle_manifest_sha256") != identity.b5_bundle_manifest_sha256
        or authorization.get("verifier_identity") != independent_verifier_identity()
        or authorization.get("lineage_sha256") != sha256_bytes(canonical_json(lineage))
    ):
        raise ValueError("same-draw B5 authorization identity mismatch")
    if (
        lineage.get("strategy_revision_id") != identity.strategy_revision_id
        or lineage.get("protocol_snapshot_id") != identity.protocol_snapshot_id
        or lineage.get("formal_snapshot", {}).get("id") != identity.formal_snapshot_id
        or lineage.get("formal_snapshot", {}).get("manifest_sha256")
        != identity.formal_snapshot_manifest_sha256
    ):
        raise ValueError("same-draw B5 lineage/snapshot identity mismatch")
    draw_index = envelope.get("oos_draw_index")
    if isinstance(draw_index, bool) or not isinstance(draw_index, int) or not 1 <= draw_index <= 3:
        raise ValueError("same-draw envelope requires one valid OOS draw index")
    return identity, draw_index


def _find_verified_supplement(repo_root: Path, manifest_sha256: str) -> tuple[Path, dict[str, Any]]:
    root = (repo_root / _SUPPLEMENT_ROOT).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"same-draw supplement root missing: {root}")
    matches: list[tuple[Path, dict[str, Any]]] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = directory / "manifest.json"
        sidecar = manifest_path.with_name("manifest.json.sha256")
        if not manifest_path.is_file() or not sidecar.is_file():
            continue
        actual = _sha256(manifest_path)
        if sidecar.read_text(encoding="utf-8").split()[0] != actual:
            raise ValueError(f"same-draw supplement sidecar mismatch: {manifest_path}")
        if actual != manifest_sha256:
            continue
        verified = verify_v3_execution_semantics(directory)
        if verified.get("status") != "verified":
            raise ValueError(f"same-draw supplement verification failed: {verified}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        matches.append((directory, manifest))
    if len(matches) != 1:
        raise ValueError("same-draw execution supplement identity is not unique")
    return matches[0]


def _load_industry_index(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    inventory_root = (repo_root / _SOURCE_INVENTORY_ROOT).resolve()
    manifest_path = inventory_root / "manifest.json"
    sidecar = manifest_path.with_name("manifest.json.sha256")
    if not manifest_path.is_file() or not sidecar.is_file():
        raise FileNotFoundError("same-draw source inventory manifest is missing")
    actual_manifest_sha = _sha256(manifest_path)
    if sidecar.read_text(encoding="utf-8").split()[0] != actual_manifest_sha:
        raise ValueError("same-draw source inventory manifest sidecar mismatch")
    inventory = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        inventory.get("artifact_id") != _SOURCE_INVENTORY_ID
        or inventory.get("status") != "published"
        or inventory.get("authorization_scope") != _SOURCE_INVENTORY_SCOPE
        or inventory.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True
    ):
        raise ValueError("same-draw source inventory identity/authorization mismatch")
    source_manifest_path = (repo_root / inventory["source_manifest_path"]).resolve()
    if not source_manifest_path.is_file():
        raise FileNotFoundError("same-draw industry source manifest is missing")
    if _sha256(source_manifest_path) != inventory.get("source_manifest_sha256"):
        raise ValueError("same-draw industry source manifest hash mismatch")
    source_root = source_manifest_path.parent
    result: dict[str, list[dict[str, Any]]] = {}
    for partition in inventory.get("partitions", ()):
        path = source_root / partition["name"]
        if _sha256(path) != partition["sha256"]:
            raise ValueError(f"same-draw industry partition hash mismatch: {path.name}")
        for row in pq.read_table(path).to_pylist():
            try:
                start = date.fromisoformat(row["in_date"]) if isinstance(row["in_date"], str) and "-" in row["in_date"] else date(int(row["in_date"][:4]), int(row["in_date"][4:6]), int(row["in_date"][6:8]))
                raw_end = row.get("out_date")
                end = None if raw_end in (None, "") else (date.fromisoformat(raw_end) if isinstance(raw_end, str) and "-" in raw_end else date(int(raw_end[:4]), int(raw_end[4:6]), int(raw_end[6:8])))
                symbol = row["ts_code"]
                code = row["l1_code"]
                name = row["l1_name"]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid same-draw industry source row: {path.name}") from exc
            result.setdefault(symbol, []).append({"l1_code": code, "l1_name": name, "in_date": start, "out_date": end})
    if not result:
        raise ValueError("same-draw industry source is empty")
    return result


def _strategy_costs(event: EventBacktestResult) -> tuple[dict[str, float], dict[str, float], float]:
    intents = {item.order_id: item for item in event.order_intents}
    if len(intents) != len(event.order_intents):
        raise ValueError("same-draw order-intent identity is duplicated")
    base = {"commission": 0.0, "stamp": 0.0, "transfer": 0.0, "total": 0.0}
    stress = {"commission": 0.0, "stamp": 0.0, "transfer": 0.0, "slippage": 0.0, "total": 0.0}
    if not event.fills:
        return base, stress, 0.0
    denominator = 0.0
    seen_fill_ids: set[str] = set()
    for fill in event.fills:
        if fill.fill_id in seen_fill_ids:
            raise ValueError("same-draw fill identity is duplicated")
        seen_fill_ids.add(fill.fill_id)
        intent = intents.get(fill.order_id)
        if intent is None or intent.symbol != fill.symbol or intent.intent not in {"buy", "sell"} or intent.quantity < fill.fill_quantity:
            raise ValueError(f"same-draw fill/intents mismatch: {fill.fill_id}")
        direction = intent.intent
        quantity = int(fill.fill_quantity)
        base_price = float(fill.fill_price)
        stress_price = base_price * (1.001 if direction == "buy" else 0.999)
        base_gross, base_commission, base_stamp, base_transfer, base_total, _ = calculate_transaction_costs(
            direction, quantity, base_price, 0.0003, 5.0, 0.001, 0.0
        )
        _, stress_commission, stress_stamp, stress_transfer, stress_total, _ = calculate_transaction_costs(
            direction, quantity, stress_price, 0.0006, 5.0, 0.001, 0.0
        )
        denominator += float(base_gross)
        base["commission"] += float(base_commission)
        base["stamp"] += float(base_stamp)
        base["transfer"] += float(base_transfer)
        base["total"] += float(base_total)
        stress["commission"] += float(stress_commission)
        stress["stamp"] += float(stress_stamp)
        stress["transfer"] += float(stress_transfer)
        stress["slippage"] += abs(stress_price - base_price) * quantity
        stress["total"] += float(stress_total) + abs(stress_price - base_price) * quantity
    if not _finite(denominator) or denominator <= 0 or stress["total"] <= base["total"]:
        raise ValueError("same-draw cost denominator or stress ordering is invalid")
    return base, stress, denominator


def _run_comparator(
    *,
    kind: str,
    source: _FormalComparisonSource,
    dates: tuple[date, ...],
    schedule: list[dict[str, str]],
) -> float:
    schedule_by_day = {date.fromisoformat(item["execution_date"]): item for item in schedule}
    positions: dict[str, float] = {}
    cash = INITIAL_NAV
    base_cost_total = 0.0
    stress_cost_total = 0.0
    for day in dates:
        if day in schedule_by_day:
            item = schedule_by_day[day]
            members = source.members_for(date.fromisoformat(item["as_of_date"]), day)
            targets = industry_weights(members) if kind == "benchmark" else control_weights(members)
            execution_prices: dict[str, float] = {}
            tradable: dict[str, bool] = {}
            for symbol in sorted(set(positions) | set(targets)):
                price, can_trade, _ = source.execution(symbol, day, held=symbol in positions)
                if price is None:
                    price = source._last_prices.get(symbol)
                if price is not None:
                    execution_prices[symbol] = float(price)
                tradable[symbol] = can_trade
            pre_values = {symbol: units * execution_prices[symbol] for symbol, units in positions.items() if symbol in execution_prices}
            pre_nav = cash + sum(pre_values.values())
            if not _finite(pre_nav) or pre_nav <= 0:
                raise ValueError(f"same-draw comparator invalid pre-trade NAV: {day}")
            rebalanced = rebalance_fractional(
                positions=positions,
                cash=cash,
                target_weights=targets,
                execution_prices=execution_prices,
                tradable=tradable,
                nav=pre_nav,
            )
            positions = rebalanced.positions
            cash = rebalanced.cash
            base_cost_total += rebalanced.base_cost
            stress_cost_total += rebalanced.stress_cost
        position_values: dict[str, float] = {}
        for symbol in list(positions):
            price, reason = source.mark(symbol, day)
            if reason == "force_liquidation_last_tradable_with_penalty":
                cash += positions[symbol] * price
                del positions[symbol]
            else:
                position_values[symbol] = positions[symbol] * price
        gross_nav = cash + sum(position_values.values())
        base_nav = gross_nav - base_cost_total
        stress_nav = gross_nav - stress_cost_total
        if any(not _finite(value) or value <= 0 for value in (gross_nav, base_nav, stress_nav)):
            raise ValueError(f"same-draw comparator invalid NAV: {day}")
    if not dates:
        raise ValueError("same-draw comparator has no dates")
    return base_nav / INITIAL_NAV - 1.0, stress_nav / INITIAL_NAV - 1.0


def execute_production_same_draw(envelope: Mapping[str, Any], *, repo_root: Path) -> B6SameDrawOOSResult:
    """Run one real v3 strategy and same-envelope benchmark/control calculation."""
    identity, _draw_index = _validate_envelope(envelope)
    root = Path(repo_root).resolve()
    prepared_supplement = envelope["prepared_supplement"]
    verified_supplement = prepared_supplement.consume(identity)
    raw_source = FormalPITPartitionAdapter(
        root,
        formal_input_binding=envelope["formal_input_binding"],
    )
    owner = _SharedReadBoundOwner(raw_source, identity.oos_end)
    all_common_dates = tuple(owner.common_trading_dates(date(1900, 1, 1), identity.oos_end))
    dates = tuple(day for day in all_common_dates if identity.oos_start <= day <= identity.oos_end)
    if not dates or dates[0] != identity.oos_start or dates[-1] != identity.oos_end:
        raise ValueError("same-draw common calendar does not exactly cover the OOS window")
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=identity.strategy_revision_id,
        protocol_snapshot_id=identity.protocol_snapshot_id,
        data_snapshot_hash=identity.data_snapshot_hash,
        supplement_id=str(verified_supplement["supplement_id"]),
        backtest_start=identity.oos_start,
        backtest_end=identity.oos_end,
    )
    observations: list[Any] = []
    event = run_event_backtest(
        spec,
        owner,
        None,
        identity.protocol_snapshot_id,
        identity.data_snapshot_hash,
        initial_capital=spec.initial_capital,
        verified_supplement=verified_supplement,
        observation_sink=observations.append,
    )
    if not isinstance(event, EventBacktestResult) or event.backtest_start != identity.oos_start or event.backtest_end != identity.oos_end:
        raise ValueError("same-draw strategy result window/type mismatch")
    expected_observation_dates = list(dates)
    if [item.date for item in observations] != expected_observation_dates:
        raise ValueError("same-draw strategy observation dates are incomplete or duplicated")
    if not observations or observations[-1].portfolio_value != event.final_portfolio.portfolio_value or observations[-1].date != event.final_portfolio.snapshot_date:
        raise ValueError("same-draw strategy sidecar final portfolio mismatch")
    base_cost, stress_cost, denominator = _strategy_costs(event)
    strategy_base_nav = float(observations[-1].portfolio_value)
    stress_nav = strategy_base_nav - (stress_cost["total"] - base_cost["total"])
    if any(not _finite(value) or value <= 0 for value in (spec.initial_capital, strategy_base_nav, stress_nav)):
        raise ValueError("same-draw strategy NAV is invalid")
    industry_index = _load_industry_index(root)
    schedule = build_weekly_schedule(all_common_dates, identity.oos_start, identity.oos_end)
    benchmark_source = _FormalComparisonSource(owner, industry_index)
    control_source = _FormalComparisonSource(owner, industry_index)
    benchmark_base, benchmark_stress = _run_comparator(kind="benchmark", source=benchmark_source, dates=dates, schedule=schedule)
    control_base, control_stress = _run_comparator(kind="control", source=control_source, dates=dates, schedule=schedule)
    if denominator == 0.0:
        base_total_bps = stress_total_bps = 0.0
        base_commission_bps = stress_commission_bps = stress_slippage_bps = 0.0
    else:
        base_total_bps = base_cost["total"] / denominator * 10000.0
        stress_total_bps = stress_cost["total"] / denominator * 10000.0
        base_commission_bps = (base_cost["commission"] / denominator) * 10000.0
        stress_commission_bps = (stress_cost["commission"] / denominator) * 10000.0
        stress_slippage_bps = (stress_cost["slippage"] / denominator) * 10000.0
    base_result = BaseCostResult(
        result_id=f"b6-base-cost-{identity.execution_input_hash[:16]}",
        slippage_bps=0.0,
        commission_bps=base_commission_bps,
        impact_bps=0.0,
        total_cost_bps=base_total_bps,
        assumptions_hash=COST_ASSUMPTIONS_HASH,
    )
    stress_result = StressCostResult(
        result_id=f"b6-stress-cost-{identity.execution_input_hash[:16]}",
        slippage_bps=stress_slippage_bps,
        commission_bps=stress_commission_bps,
        impact_bps=0.0,
        total_cost_bps=stress_total_bps,
        stress_multiplier=2.0,
        assumptions_hash=COST_ASSUMPTIONS_HASH,
    )
    result = B6SameDrawOOSResult(
        identity=identity,
        starting_nav=spec.initial_capital,
        ending_nav_base=strategy_base_nav,
        ending_nav_stress=stress_nav,
        strategy_net_return_base=strategy_base_nav / spec.initial_capital - 1.0,
        strategy_net_return_stress=stress_nav / spec.initial_capital - 1.0,
        benchmark_net_return_base=benchmark_base,
        benchmark_net_return_stress=benchmark_stress,
        same_universe_control_return_base=control_base,
        same_universe_control_return_stress=control_stress,
        base_cost_result=base_result,
        stress_cost_result=stress_result,
        read_audit=owner.audit(),
    )
    return result.assert_production_terminal_eligible()
