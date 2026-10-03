"""Explicit-task B6 claim and second-preflight owner."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
import json

from backend.db.strategy import StrategyDB
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.b5_oos_types import B6SameDrawOOSResult
from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.b6_same_draw_executor import PreparedSupplementToken
from backend.services.b6_validation_flow import B6ValidationFlow
from backend.services.v3_b5_bundle import (
    FORMAL_B6_PREFLIGHT_SCOPE,
    V3_B5_BUNDLE_ROOT,
    independent_verifier_identity,
)
from backend.services.v3_b5_types import canonical_json, sha256_bytes
from contracts.b6_task import (
    build_b6_successor_task_key,
    build_b6_task_id,
    build_b6_task_key,
)
from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics


EXPECTED_B5_AUTHORIZATION_SCOPE = FORMAL_B6_PREFLIGHT_SCOPE
EXPECTED_B5_NOT_AUTHORIZED = "not_authorized_for_b6_oos_gate_promotion_signal"


@dataclass(frozen=True)
class B6WorkerResult:
    """Durable state and boundary evidence returned by one explicit-task call."""

    task_id: str
    task_key: str | None
    task_status: str
    status: str
    reason: str
    ready_for_reservation: bool = False
    b4_artifact: dict[str, Any] | None = None
    b5_bundle: dict[str, Any] | None = None
    reservation_id: str | None = None
    report_id: str | None = None
    gate_result_id: str | None = None
    explanation_id: str | None = None
    oos_authorized: bool = False
    oos_consumed: bool = False
    promotion_id: str | None = None


class _PreflightBlocked(ValueError):
    def __init__(self, reason_code: str, detail: str | None = None):
        self.reason_code = reason_code
        self.detail = detail or reason_code
        super().__init__(self.detail)


class _PreflightInvariant(ValueError):
    pass


class B6ValidationWorker:
    """Run only the explicit-task claim and second-preflight boundary."""

    def __init__(
        self,
        db: StrategyDB,
        *,
        repo_root: Path,
        b4_results_root: Path | None = None,
        b5_bundle_root: Path | None = None,
        ledger: Any | None = None,
        b4_result_loader=None,
    ) -> None:
        self.db = db
        self.repo_root = Path(repo_root)
        self.b4_results_root = Path(b4_results_root) if b4_results_root is not None else None
        self.b5_bundle_root = (
            Path(b5_bundle_root)
            if b5_bundle_root is not None
            else self.repo_root / V3_B5_BUNDLE_ROOT
        )
        self.ledger = ledger
        self.b4_result_loader = b4_result_loader

    def run_task(self, task_id: str, *, execute_same_draw=None) -> B6WorkerResult:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("B6 worker requires one explicit task_id")

        task = self.db.get_b6_task_by_id(task_id)
        if task is None:
            return B6WorkerResult(
                task_id=task_id,
                task_key=None,
                task_status="missing",
                status="not_found",
                reason="b6_task_not_found",
            )

        if task.status != "queued":
            if task.status == "running":
                if execute_same_draw is not None:
                    return self._recover_running(task, execute_same_draw)
                return self._result(task, "recovery_required", "recovery_required")
            return self._terminal_result_or_not_executable(task)

        claimed = self.db.claim_b6_task(task_id)
        if claimed is None:
            current = self.db.get_b6_task_by_id(task_id)
            if current is None:
                return B6WorkerResult(
                    task_id=task_id,
                    task_key=None,
                    task_status="missing",
                    status="not_claimed",
                    reason="claim_lost_task_missing",
                )
            return self._result(current, "not_claimed", "claim_lost")

        try:
            b4_artifact, b5_bundle, protocol, prepared_supplement = self._second_preflight(claimed)
        except _PreflightBlocked as exc:
            return self._transition_result(
                claimed,
                status="blocked",
                reason_code=exc.reason_code,
                reason_detail=exc.detail,
            )
        except _PreflightInvariant as exc:
            return self._transition_result(
                claimed,
                status="failed",
                reason_code="invariant_error",
                reason_detail=str(exc),
            )

        ledger = self.ledger if self.ledger is not None else OOSBudgetLedger(self.db)
        try:
            state = ledger.get_ledger_state(
                protocol.theme_id,
                protocol.hypothesis_source_snapshot_id,
            )
        except (OSError, TypeError, ValueError) as exc:
            return self._transition_result(
                claimed,
                status="blocked",
                reason_code="b6_ledger_unavailable",
                reason_detail=str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        if state.get("budget_status") != "available" or state.get("active_reservation_id") is not None:
            return self._transition_result(
                claimed,
                status="blocked",
                reason_code="b6_oos_budget_unavailable",
                reason_detail="OOS budget is not available for this task",
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        current = self.db.get_b6_task_by_id(claimed.task_id)
        if current is None:
            raise RuntimeError("B6 task disappeared after preflight")
        if execute_same_draw is None:
            return self._result(
                current,
                status="ready_for_reservation",
                reason="ready_for_reservation",
                ready_for_reservation=True,
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        return self._execute_reserved(
            current,
            protocol,
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
                prepared_supplement=prepared_supplement,
                ledger=ledger,
                execute_same_draw=execute_same_draw,
            )

    def _second_preflight(self, task):
        if task.task_contract_version == "v3":
            try:
                expected_key = build_b6_successor_task_key(
                    predecessor_task_id=task.predecessor_task_id,
                    predecessor_task_key=task.predecessor_task_key,
                    strategy_revision_id=task.strategy_revision_id,
                    protocol_snapshot_id=task.protocol_snapshot_id,
                    b5_bundle_id=task.b5_bundle_id,
                    b5_bundle_manifest_sha256=task.b5_bundle_manifest_sha256,
                    attempt_number=task.successor_attempt_number,
                )
            except (TypeError, ValueError) as exc:
                raise _PreflightInvariant(
                    "B6 v3 successor identity is invalid: " + str(exc)
                ) from exc
            if task.task_key != expected_key:
                raise _PreflightInvariant(
                    "B6 v3 successor task key does not match persisted identity"
                )
            if task.task_id != build_b6_task_id(task.task_key):
                raise _PreflightInvariant(
                    "B6 v3 successor task ID does not match canonical task key"
                )
            predecessor = self.db.get_b6_task_by_id(task.predecessor_task_id)
            if predecessor is None:
                raise _PreflightInvariant("B6 v3 predecessor task is missing")
            if predecessor.task_contract_version != "v2":
                raise _PreflightInvariant("B6 v3 predecessor is not v2")
            if predecessor.status != "failed" or predecessor.claimed_at is None:
                raise _PreflightInvariant("B6 v3 predecessor is not a claimed failed task")
            try:
                expected_predecessor_key = build_b6_task_key(
                    strategy_revision_id=predecessor.strategy_revision_id,
                    protocol_snapshot_id=predecessor.protocol_snapshot_id,
                    task_contract_version="v2",
                    b5_bundle_id=predecessor.b5_bundle_id,
                    b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
                )
            except (TypeError, ValueError) as exc:
                raise _PreflightInvariant(
                    "B6 v3 predecessor identity is invalid: " + str(exc)
                ) from exc
            if (
                predecessor.task_key != expected_predecessor_key
                or predecessor.task_id != build_b6_task_id(predecessor.task_key)
                or predecessor.strategy_revision_id != task.strategy_revision_id
                or predecessor.protocol_snapshot_id != task.protocol_snapshot_id
                or predecessor.b5_bundle_id != task.b5_bundle_id
                or predecessor.b5_bundle_manifest_sha256 != task.b5_bundle_manifest_sha256
                or task.predecessor_task_key != predecessor.task_key
            ):
                raise _PreflightInvariant("B6 v3 predecessor binding does not match")
            direct_binding = self.db.conn.execute(
                "SELECT task_id FROM b6_validation_tasks WHERE predecessor_task_id = ?",
                (predecessor.task_id,),
            ).fetchone()
            if direct_binding is None or direct_binding[0] != task.task_id:
                raise _PreflightInvariant("B6 v3 direct predecessor binding is invalid")
        else:
            expected_key = build_b6_task_key(
                strategy_revision_id=task.strategy_revision_id,
                protocol_snapshot_id=task.protocol_snapshot_id,
                task_contract_version=task.task_contract_version,
                b5_bundle_id=task.b5_bundle_id,
                b5_bundle_manifest_sha256=task.b5_bundle_manifest_sha256,
            )
            if task.task_contract_version != "v2" or task.task_key != expected_key:
                raise _PreflightInvariant("B6 task key/version does not match persisted identity")
        if task.task_id != build_b6_task_id(task.task_key):
            raise _PreflightInvariant("B6 task ID does not match canonical task key")
        if task.status != "running":
            raise _PreflightInvariant("B6 task was not claimed as running")

        b5_bundle = self._discover_b5(task)
        if b5_bundle.get("status") != "verified":
            reason = str(b5_bundle.get("reason", "B5 bundle is unavailable"))
            if any(token in reason.lower() for token in ("missing", "not found", "unavailable")):
                raise _PreflightBlocked("b6_b5_validation_inputs_missing", reason)
            raise _PreflightInvariant("B5 bundle verification failed: " + reason)
        if b5_bundle.get("bundle_id") != task.b5_bundle_id:
            raise _PreflightInvariant("B5 bundle ID does not match task")
        if b5_bundle.get("manifest_sha256") != task.b5_bundle_manifest_sha256:
            raise _PreflightInvariant("B5 manifest hash does not match task")
        if b5_bundle.get("authorization_scope") != EXPECTED_B5_AUTHORIZATION_SCOPE:
            raise _PreflightInvariant("B5 authorization scope changed")
        if b5_bundle.get(EXPECTED_B5_NOT_AUTHORIZED) is not False:
            raise _PreflightInvariant("B5 not-authorized disclosure changed")
        expected_verifier = independent_verifier_identity()
        if b5_bundle.get("verifier_identity") != expected_verifier:
            raise _PreflightInvariant("B5 independent verifier identity changed")

        b4_artifact = self._discover_b4(b5_bundle)
        b4_lineage = {
            "artifact_id": b4_artifact.get("artifact_id"),
            "manifest_sha256": b4_artifact.get("manifest_sha256"),
            "event_sha256": b4_artifact.get("event_result_sha256"),
        }
        if b5_bundle.get("lineage", {}).get("b4") != b4_lineage:
            raise _PreflightInvariant("B4/B5 lineage mismatch")

        protocol = self.db.get_protocol_snapshot(task.protocol_snapshot_id)
        if protocol is None:
            raise _PreflightBlocked("b6_protocol_missing")
        if protocol.protocol_snapshot_id != task.protocol_snapshot_id:
            raise _PreflightInvariant("protocol ID does not match task")
        if protocol.strategy_revision_id != task.strategy_revision_id:
            raise _PreflightInvariant("protocol revision does not match task")
        if protocol.protocol_profile != "b6_coverage_bound":
            raise _PreflightInvariant("protocol is not b6_coverage_bound")
        if protocol.oos_window_start > protocol.oos_window_end or not protocol.shared_oos_window_id:
            raise _PreflightInvariant("protocol OOS window is invalid")

        lineage = b5_bundle.get("lineage", {})
        if lineage.get("protocol_snapshot_id") != protocol.protocol_snapshot_id:
            raise _PreflightInvariant("B5 protocol binding mismatch")
        if lineage.get("strategy_revision_id") != protocol.strategy_revision_id:
            raise _PreflightInvariant("B5 revision binding mismatch")
        formal = lineage.get("formal_snapshot", {})
        if formal.get("id") != protocol.data_snapshot_id or formal.get("semantic_hash") != protocol.data_snapshot_hash:
            raise _PreflightInvariant("formal snapshot binding mismatch")
        universe = self.db.get_backtest_universe(protocol.backtest_universe_spec_id)
        if universe is None:
            raise _PreflightBlocked("b6_membership_universe_missing")
        membership = lineage.get("membership", {})
        if membership.get("id") not in universe.membership_snapshot_ids:
            raise _PreflightInvariant("PIT membership binding mismatch")
        prepared_supplement = self._prepare_verified_supplement(b5_bundle, protocol)
        self._validate_formal_executable_scope(protocol, b5_bundle)
        return b4_artifact, b5_bundle, protocol, prepared_supplement

    def _validate_formal_executable_scope(self, protocol, b5_bundle) -> None:
        """Require exact B5-bound PIT lifecycle and execution inputs before OOS."""
        try:
            lineage = b5_bundle.get("lineage", {})
            formal_input_binding = {
                "formal_snapshot": lineage.get("formal_snapshot"),
                "b3_execution_input": lineage.get("b3_execution_input"),
                "stock_basic_lifecycle": lineage.get("stock_basic_lifecycle"),
                "membership": lineage.get("membership"),
            }
            if any(not isinstance(value, dict) for value in formal_input_binding.values()):
                raise _PreflightInvariant("B5 formal input binding is incomplete")
            adapter = FormalPITPartitionAdapter(
                self.repo_root,
                formal_input_binding=formal_input_binding,
            )
            if adapter.formal_binding_verified is not True:
                raise _PreflightInvariant("B6 formal preflight received an unbound fixture adapter")
            trading_dates = adapter.common_trading_dates(
                protocol.oos_window_start,
                protocol.oos_window_end,
            )
            if (
                not trading_dates
                or trading_dates[0] != protocol.oos_window_start
                or trading_dates[-1] != protocol.oos_window_end
            ):
                raise _PreflightBlocked(
                    "b6_formal_scope_unavailable",
                    "verified formal calendar does not exactly cover the OOS window",
                )

            symbols_by_date: dict[date, tuple[str, ...]] = {}
            missing_lifecycle: set[str] = set()
            ineligible_membership: set[str] = set()
            unsupported_symbols: set[str] = set()
            for as_of_date in trading_dates:
                symbols = tuple(adapter.symbols_as_of(as_of_date))
                if not symbols:
                    raise _PreflightBlocked(
                        "b6_formal_scope_unavailable",
                        f"execution universe is empty on {as_of_date.isoformat()}",
                    )
                symbols_by_date[as_of_date] = symbols
                for symbol in symbols:
                    if not isinstance(symbol, str) or not symbol.endswith((".SH", ".SZ")):
                        unsupported_symbols.add(str(symbol))
                    try:
                        eligible = adapter.is_eligible(symbol, as_of_date)
                    except KeyError:
                        missing_lifecycle.add(symbol)
                        continue
                    if eligible is not True:
                        ineligible_membership.add(symbol)

            scope_issues: list[str] = []

            def summarize_symbols(label: str, symbols: set[str]) -> str:
                ordered = sorted(symbols)
                preview = ", ".join(ordered[:20])
                omitted = len(ordered) - min(len(ordered), 20)
                suffix = f", … (+{omitted} more)" if omitted else ""
                return f"{label} ({len(ordered)}): {preview}{suffix}"

            if missing_lifecycle:
                scope_issues.append(summarize_symbols(
                    "membership symbols are absent from formal stock_basic lifecycle",
                    missing_lifecycle,
                ))
            if ineligible_membership:
                scope_issues.append(summarize_symbols(
                    "membership symbols are outside stock_basic lifecycle dates",
                    ineligible_membership,
                ))
            if unsupported_symbols:
                scope_issues.append(summarize_symbols(
                    "unsupported execution-universe symbols",
                    unsupported_symbols,
                ))
            if scope_issues:
                raise _PreflightBlocked(
                    "b6_formal_scope_unavailable",
                    "; ".join(scope_issues),
                )

            for as_of_date in trading_dates:
                for symbol in symbols_by_date[as_of_date]:
                    try:
                        status = adapter.get_daily_status(symbol, as_of_date)
                        if not isinstance(status.is_suspended, bool):
                            raise ValueError("daily suspension status is not deterministic")
                        if not status.is_suspended:
                            adapter.get_daily_bar(symbol, as_of_date)
                    except (OSError, TypeError, ValueError, KeyError, AttributeError) as exc:
                        raise _PreflightBlocked(
                            "b6_formal_scope_unavailable",
                            f"required formal execution inputs missing for {symbol}/{as_of_date.isoformat()}: {exc}",
                        ) from exc
        except _PreflightBlocked:
            raise
        except _PreflightInvariant:
            raise
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise _PreflightBlocked(
                "b6_formal_scope_unavailable",
                "formal PIT execution inputs are unavailable: " + str(exc),
            ) from exc

    def _prepare_verified_supplement(self, b5_bundle, protocol) -> PreparedSupplementToken:
        lineage = b5_bundle.get("lineage", {})
        binding = lineage.get("execution_supplement", {})
        supplement_id = binding.get("id")
        manifest_sha256 = binding.get("manifest_sha256")
        if not supplement_id or not manifest_sha256:
            raise _PreflightBlocked("b6_supplement_validation_inputs_missing")
        criteria_envelope_hash = lineage.get("gate_criteria_envelope_hash")
        if (
            not isinstance(criteria_envelope_hash, str)
            or not criteria_envelope_hash
            or criteria_envelope_hash != protocol.gate_criteria_hash
        ):
            raise _PreflightInvariant("B5/protocol criteria envelope mismatch")
        supplement_dir = (
            self.repo_root / "data" / "pit" / "v3_execution_semantics_supplements" / str(supplement_id)
        ).resolve()
        try:
            verified = verify_v3_execution_semantics(supplement_dir, repo_root=self.repo_root)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise _PreflightBlocked("b6_supplement_validation_inputs_missing", str(exc)) from exc
        if verified.get("status") != "verified":
            raise _PreflightInvariant("supplement verification failed: " + str(verified.get("reason", verified)))
        if (
            verified.get("supplement_id") != supplement_id
            or verified.get("manifest_sha256") != manifest_sha256
            or verified.get("strategy_revision_id") != protocol.strategy_revision_id
            or verified.get("protocol_snapshot_id") != protocol.protocol_snapshot_id
            or verified.get("data_snapshot_hash") != protocol.data_snapshot_hash
            or verified.get("criteria_envelope_hash") != criteria_envelope_hash
        ):
            raise _PreflightInvariant("supplement binding does not match protocol/B5 lineage")
        try:
            return PreparedSupplementToken.from_verified(
                supplement_dir,
                verified,
                repo_root=self.repo_root,
                b5_bundle_id=b5_bundle["bundle_id"],
                b5_bundle_manifest_sha256=b5_bundle["manifest_sha256"],
                criteria_envelope_hash=criteria_envelope_hash,
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise _PreflightInvariant("prepared supplement token is invalid: " + str(exc)) from exc

    def _discover_b4(self, b5_bundle):
        lineage = b5_bundle.get("lineage", {})
        b4_binding = lineage.get("b4") if isinstance(lineage, dict) else None
        if not isinstance(b4_binding, dict):
            raise _PreflightInvariant("verified B5 bundle has no B4 lineage")
        artifact_id = b4_binding.get("artifact_id")
        expected_manifest_sha256 = b4_binding.get("manifest_sha256")
        expected_event_sha256 = b4_binding.get("event_sha256")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (artifact_id, expected_manifest_sha256, expected_event_sha256)
        ):
            raise _PreflightInvariant("verified B5 B4 lineage identity is incomplete")
        if Path(artifact_id).name != artifact_id or "/" in artifact_id or "\\" in artifact_id:
            raise _PreflightInvariant("verified B5 B4 artifact ID is not a path component")

        result_root = (
            self.b4_results_root
            if self.b4_results_root is not None
            else self.repo_root / "data/pit/v3_b4_is_results"
        ).resolve()
        artifact_dir = (result_root / artifact_id).resolve()
        try:
            artifact_dir.relative_to(result_root)
        except ValueError as exc:
            raise _PreflightInvariant("verified B5 B4 artifact path escapes its result root") from exc
        if not artifact_dir.is_dir():
            raise _PreflightBlocked("b6_b4_artifact_missing", f"B4 artifact directory missing: {artifact_id}")

        try:
            from scripts.run_v3_b4_is_once import verify_v3_b4_is_result

            verified = verify_v3_b4_is_result(artifact_dir, repo_root=self.repo_root)
            if verified.get("status") != "verified":
                raise _PreflightInvariant(
                    "B4 artifact verification failed: " + str(verified.get("reason", "unknown"))
                )
            if (
                verified.get("artifact_id") != artifact_id
                or verified.get("manifest_sha256") != expected_manifest_sha256
                or verified.get("event_result_sha256") != expected_event_sha256
            ):
                raise _PreflightInvariant("B4 verifier identity does not match B5 lineage")
            manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("artifact_id") != artifact_id:
                raise _PreflightInvariant("B4 manifest path/identity mismatch")
            if (
                manifest.get("strategy_revision_id") != lineage.get("strategy_revision_id")
                or manifest.get("protocol_snapshot_id") != lineage.get("protocol_snapshot_id")
            ):
                raise _PreflightInvariant("B4 manifest revision/protocol does not match B5 lineage")
            return {
                "artifact_id": artifact_id,
                "path": str(artifact_dir),
                "manifest_sha256": verified["manifest_sha256"],
                "event_result_sha256": verified["event_result_sha256"],
                "strategy_revision_id": manifest["strategy_revision_id"],
                "protocol_snapshot_id": manifest["protocol_snapshot_id"],
                "is_range": manifest.get("is_range"),
            }
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            if isinstance(exc, (_PreflightBlocked, _PreflightInvariant)):
                raise
            raise _PreflightInvariant("B4 artifact verification failed: " + str(exc)) from exc

    def _discover_b5(self, task):
        bundle_dir = self.b5_bundle_root / str(task.b5_bundle_id)
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        verified = verify_verified_b5_bundle(self.repo_root, bundle_dir)
        return {**verified, "path": str(bundle_dir.resolve())}

    def _load_b4_result(self, b4_artifact: dict[str, Any]) -> EventBacktestResult:
        if self.b4_result_loader is not None:
            result = self.b4_result_loader(b4_artifact)
        else:
            result = EventBacktestResult.model_validate_json(
                (Path(b4_artifact["path"]) / "event_result.json").read_text(encoding="utf-8")
            )
        if result.strategy_revision_id != b4_artifact["strategy_revision_id"]:
            raise ValueError("B4 event strategy revision mismatch")
        if result.protocol_snapshot_id != b4_artifact["protocol_snapshot_id"]:
            raise ValueError("B4 event protocol mismatch")
        return result

    def _execute_reserved(
        self,
        task,
        protocol,
        *,
        b4_artifact: dict[str, Any],
        b5_bundle: dict[str, Any],
        prepared_supplement: PreparedSupplementToken,
        ledger,
        execute_same_draw,
    ) -> B6WorkerResult:
        if not callable(execute_same_draw):
            raise TypeError("execute_same_draw must be callable")
        try:
            b4_result = self._load_b4_result(b4_artifact)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._transition_result(
                task,
                status="failed",
                reason_code="invariant_error",
                reason_detail="B4 event result invalid: " + str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        verified_is_range = b4_artifact.get("is_range")
        if not isinstance(verified_is_range, dict):
            return self._transition_result(
                task,
                status="failed",
                reason_code="invariant_error",
                reason_detail="verified B4 IS window is missing",
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        try:
            verified_is_start = date.fromisoformat(verified_is_range["start"])
            verified_is_end = date.fromisoformat(verified_is_range["end"])
        except (KeyError, TypeError, ValueError) as exc:
            return self._transition_result(
                task,
                status="failed",
                reason_code="invariant_error",
                reason_detail="verified B4 IS window is invalid: " + str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        if (
            verified_is_start > verified_is_end
            or b4_result.backtest_start != verified_is_start
            or b4_result.backtest_end != verified_is_end
        ):
            return self._transition_result(
                task,
                status="failed",
                reason_code="invariant_error",
                reason_detail="B4 event result window does not match verified B4 IS window",
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        existing = self._reservation_for_task(task.task_key)
        if existing is not None:
            return self._recover_reservation(
                task,
                existing,
                ledger=ledger,
                execute_same_draw=execute_same_draw,
            )

        try:
            prepared_supplement.assert_current()
        except (OSError, TypeError, ValueError) as exc:
            return self._transition_result(
                task,
                status="blocked",
                reason_code="b6_prepared_supplement_changed",
                reason_detail=str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        try:
            reservation = ledger.reserve_oos_draw(
                theme_id=protocol.theme_id,
                hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
                strategy_config_hash=protocol.strategy_config_hash,
                data_snapshot_hash=protocol.data_snapshot_hash,
                gate_criteria_hash=protocol.gate_criteria_hash,
                shared_oos_window_id=protocol.shared_oos_window_id,
                idempotency_key=task.task_key,
                task_key=task.task_key,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
            )
        except ValueError as exc:
            return self._transition_result(
                task,
                status="blocked",
                reason_code="b6_oos_budget_unavailable",
                reason_detail=str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        except (OSError, TypeError, RuntimeError) as exc:
            return self._transition_result(
                task,
                status="failed",
                reason_code="invariant_error",
                reason_detail="OOS reservation invariant failed: " + str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        if reservation.status != "reserved":
            return self._recover_reservation(
                task,
                {
                    "reservation_id": reservation.reservation_id,
                    "status": reservation.status,
                    "task_key": task.task_key,
                    "protocol_snapshot_id": protocol.protocol_snapshot_id,
                    "report_id": None,
                },
                ledger=ledger,
                execute_same_draw=execute_same_draw,
            )

        try:
            prepared_supplement.assert_current()
        except (OSError, TypeError, ValueError) as exc:
            ledger.release_pre_execution(reservation.reservation_id, "prepared_supplement_changed: " + str(exc))
            return self._transition_result(
                task,
                status="blocked",
                reason_code="b6_prepared_supplement_changed",
                reason_detail=str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        try:
            ledger.start_execution(reservation.reservation_id)
        except Exception as exc:
            status = self._reservation_status(reservation.reservation_id)
            if status == "started":
                return self._fail_after_start(
                    task,
                    reservation.reservation_id,
                    ledger,
                    "start_visibility_unknown: " + str(exc),
                    b4_artifact=b4_artifact,
                    b5_bundle=b5_bundle,
                )
            ledger.release_pre_execution(reservation.reservation_id, "start_failed: " + str(exc))
            return self._transition_result(
                task,
                status="blocked",
                reason_code="b6_start_failed",
                reason_detail=str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        try:
            prepared_supplement.assert_current()
        except (OSError, TypeError, ValueError) as exc:
            return self._fail_after_start(
                task,
                reservation.reservation_id,
                ledger,
                "prepared_supplement_changed: " + str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )

        envelope = self._build_envelope(
            task,
            protocol,
            b4_artifact,
            b5_bundle,
            reservation,
            prepared_supplement,
        )
        try:
            raw_result = execute_same_draw(envelope)
            result = raw_result if isinstance(raw_result, B6SameDrawOOSResult) else B6SameDrawOOSResult.model_validate(raw_result)
            if result.identity.model_dump(mode="json") != envelope["identity"]:
                raise ValueError("same-draw result identity mismatch")
            flow_result = B6ValidationFlow(strategy_db=self.db, oos_budget_ledger=ledger).complete_same_draw_validation(
                task=task,
                protocol=protocol,
                reservation=reservation,
                b4_result=b4_result,
                same_draw_result=result,
                b5_bundle=b5_bundle,
            )
        except Exception as exc:
            return self._fail_after_start(
                task,
                reservation.reservation_id,
                ledger,
                "execution_or_terminal_failed: " + str(exc),
                b4_artifact=b4_artifact,
                b5_bundle=b5_bundle,
            )
        return self._result(
            self.db.get_b6_task_by_id(task.task_id),
            status="completed",
            reason="completed",
            b4_artifact=b4_artifact,
            b5_bundle=b5_bundle,
            reservation_id=reservation.reservation_id,
            report_id=flow_result.report_id,
            gate_result_id=flow_result.gate_result_id,
            explanation_id=flow_result.explanation_id,
            oos_authorized=True,
            oos_consumed=True,
        )

    def _build_envelope(
        self,
        task,
        protocol,
        b4_artifact,
        b5_bundle,
        reservation,
        prepared_supplement: PreparedSupplementToken,
    ) -> dict[str, Any]:
        lineage = b5_bundle["lineage"]
        formal = lineage["formal_snapshot"]
        membership = lineage["membership"]
        calendar = lineage["calendar"]
        return {
            "task_id": task.task_id,
            "task_key": task.task_key,
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "strategy_revision_id": protocol.strategy_revision_id,
            "reservation_id": reservation.reservation_id,
            "oos_draw_index": reservation.oos_draw_index,
            "prepared_supplement": prepared_supplement,
            "formal_input_binding": {
                "formal_snapshot": lineage["formal_snapshot"],
                "b3_execution_input": lineage["b3_execution_input"],
                "stock_basic_lifecycle": lineage["stock_basic_lifecycle"],
                "membership": lineage["membership"],
            },
            "authorization_binding": {
                "authorization_scope": b5_bundle["authorization_scope"],
                "not_authorized_for_b6_oos_gate_promotion_signal": b5_bundle[
                    EXPECTED_B5_NOT_AUTHORIZED
                ],
                "strategy_revision_id": task.strategy_revision_id,
                "protocol_snapshot_id": task.protocol_snapshot_id,
                "b5_bundle_id": b5_bundle["bundle_id"],
                "b5_bundle_manifest_sha256": b5_bundle["manifest_sha256"],
                "verifier_identity": b5_bundle["verifier_identity"],
                "lineage": lineage,
                "lineage_sha256": sha256_bytes(canonical_json(lineage)),
            },
            "identity": {
                "task_id": task.task_id,
                "task_key": task.task_key,
                "strategy_revision_id": task.strategy_revision_id,
                "protocol_snapshot_id": task.protocol_snapshot_id,
                "b5_bundle_id": task.b5_bundle_id,
                "b5_bundle_manifest_sha256": task.b5_bundle_manifest_sha256,
                "b4_artifact_id": b4_artifact["artifact_id"],
                "b4_manifest_sha256": b4_artifact["manifest_sha256"],
                "b4_event_result_sha256": b4_artifact["event_result_sha256"],
                "formal_snapshot_id": formal["id"],
                "formal_snapshot_manifest_sha256": formal["manifest_sha256"],
                "membership_snapshot_id": membership["id"],
                "membership_manifest_sha256": membership["manifest_sha256"],
                "calendar_id": calendar["id"],
                "calendar_manifest_sha256": calendar["manifest_sha256"],
                "data_snapshot_hash": protocol.data_snapshot_hash,
                "execution_input_hash": lineage["execution_supplement"]["manifest_sha256"],
                "shared_oos_window_id": protocol.shared_oos_window_id,
                "oos_start": protocol.oos_window_start.isoformat(),
                "oos_end": protocol.oos_window_end.isoformat(),
                "result_schema_version": "b6_same_draw_oos_result.v2",
            },
        }

    def _reservation_for_task(self, task_key: str):
        row = self.db.conn.execute(
            "SELECT reservation_id, status, task_key, protocol_snapshot_id, report_id FROM oos_budget_reservations WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _reservation_status(self, reservation_id: str) -> str | None:
        row = self.db.conn.execute(
            "SELECT status FROM oos_budget_reservations WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        return row[0] if row is not None else None

    def _recover_running(self, task, execute_same_draw):
        reservation = self._reservation_for_task(task.task_key)
        if reservation is None:
            return self._transition_result(
                task,
                status="queued",
                reason_code="requeued_without_reservation",
                reason_detail="running task had no task-key-bound reservation",
            )
        ledger = self.ledger if self.ledger is not None else OOSBudgetLedger(self.db)
        return self._recover_reservation(task, reservation, ledger=ledger, execute_same_draw=execute_same_draw)

    def _recover_reservation(self, task, reservation, *, ledger, execute_same_draw):
        status = reservation["status"]
        if status == "started":
            return self._fail_after_start(task, reservation["reservation_id"], ledger, "recovery_after_started")
        if status == "reserved":
            ledger.release_pre_execution(reservation["reservation_id"], "recovery_before_execution")
            return self._transition_result(
                task,
                status="queued",
                reason_code="requeued_after_release",
                reason_detail="reserved draw released before execution",
            )
        if status == "completed":
            return self._completed_from_durable_chain(task, reservation)
        if status in {"failed", "released"}:
            return self._result(
                task,
                status="failed" if status == "failed" else "blocked",
                reason="task_not_executable",
                reservation_id=reservation["reservation_id"],
                oos_authorized=True,
                oos_consumed=status == "failed",
            )
        raise RuntimeError("unknown B6 reservation status")

    def _completed_from_durable_chain(self, task, reservation):
        if reservation.get("report_id") is None:
            raise RuntimeError("completed reservation missing report")
        gate = self.db.conn.execute(
            "SELECT gate_result_id FROM prototype_gate_results_v2 WHERE report_id = ?",
            (reservation["report_id"],),
        ).fetchone()
        if gate is None:
            raise RuntimeError("completed reservation missing Gate")
        return self._result(
            task,
            status="completed",
            reason="completed",
            reservation_id=reservation["reservation_id"],
            report_id=reservation["report_id"],
            gate_result_id=gate[0],
            oos_authorized=True,
            oos_consumed=True,
        )

    def _fail_after_start(self, task, reservation_id, ledger, reason, *, b4_artifact=None, b5_bundle=None):
        try:
            self.db.conn.execute("BEGIN IMMEDIATE")
            ledger.fail_reservation_within_tx(self.db.conn, reservation_id, reason)
            cursor = self.db.update_b6_task_status(
                task_id=task.task_id,
                status="failed",
                completed_at=datetime.now(),
                blocking_reason_code="b6_fail_after_start",
                blocking_reason_detail=reason,
            )
            if cursor.rowcount != 1:
                raise RuntimeError("B6 failure transition affected an unexpected row count")
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise
        current = self.db.get_b6_task_by_id(task.task_id)
        return self._result(
            current,
            status="failed",
            reason="b6_fail_after_start",
            b4_artifact=b4_artifact,
            b5_bundle=b5_bundle,
            reservation_id=reservation_id,
            oos_authorized=True,
            oos_consumed=True,
        )

    def _terminal_result_or_not_executable(self, task):
        if task.status == "completed":
            reservation = self._reservation_for_task(task.task_key)
            if reservation is None:
                raise RuntimeError("completed B6 task has no reservation")
            return self._completed_from_durable_chain(task, reservation)
        reservation = self._reservation_for_task(task.task_key)
        return self._result(
            task,
            task.status,
            "task_not_executable",
            reservation_id=reservation["reservation_id"] if reservation else None,
            oos_authorized=reservation is not None,
            oos_consumed=bool(reservation and reservation["status"] == "failed"),
        )

    def _transition_result(
        self,
        task,
        *,
        status: str,
        reason_code: str,
        reason_detail: str,
        b4_artifact: dict[str, Any] | None = None,
        b5_bundle: dict[str, Any] | None = None,
    ) -> B6WorkerResult:
        try:
            self.db.conn.execute("BEGIN IMMEDIATE")
            cursor = self.db.update_b6_task_status(
                task_id=task.task_id,
                status=status,
                blocking_reason_code=reason_code,
                blocking_reason_detail=reason_detail,
            )
            if cursor.rowcount != 1:
                raise RuntimeError("B6 task transition affected an unexpected row count")
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise
        current = self.db.get_b6_task_by_id(task.task_id)
        if current is None:
            raise RuntimeError("B6 task disappeared after transition")
        return self._result(
            current,
            status=status,
            reason=reason_code,
            b4_artifact=b4_artifact,
            b5_bundle=b5_bundle,
        )

    @staticmethod
    def _result(task, status: str, reason: str, **kwargs) -> B6WorkerResult:
        return B6WorkerResult(
            task_id=task.task_id,
            task_key=task.task_key,
            task_status=task.status,
            status=status,
            reason=reason,
            **kwargs,
        )
