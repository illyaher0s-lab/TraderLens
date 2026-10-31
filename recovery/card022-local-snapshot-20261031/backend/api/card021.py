"""Card021 read-only live observation routes for 510880.SH."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from backend.api import card020
from backend.services.card021_live_observation import (
    _retrieved_at,
    card021_implementation_fingerprint,
    get_card021_live_observation,
    snapshot_market_inputs,
)
from backend.services.card021_store import Card021SnapshotIntegrityError, Card021SnapshotStore
from backend.services.card022_practice_account import (
    Card022PracticeAccountStore,
    PracticeAccountConflictError,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
_LOGGER = logging.getLogger(__name__)


def create_card021_router(
    market_client_provider: Callable[[], Any],
    *,
    account_provider: Callable[..., dict] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    snapshot_store: Card021SnapshotStore | None = None,
    practice_account_store: Card022PracticeAccountStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/research/card021", tags=["Card021"])

    def save_snapshot(result: dict, *, protocol_sha256: str, protocol_verified: bool) -> dict:
        if snapshot_store is None:
            result.pop("_card021_capture", None)
            return result
        stage = "capture_inputs"
        try:
            capture = result.pop("_card021_capture", None) or {
                "market_inputs": {},
                "source_receipts": [],
                "judgment_at": result.get("judgment_at"),
                "received_at": datetime.now(SHANGHAI).isoformat(timespec="microseconds"),
            }
            stage = "prepare_market_inputs"
            market_inputs = snapshot_market_inputs(capture, result)
            stage = "fingerprint_implementation"
            implementation_sha256 = card021_implementation_fingerprint()
            stage = "record_snapshot"
            market_result = dict(result)
            if market_result.get("account_mode") == "simulated_practice":
                market_result["action_decision"] = "not_decidable"
                market_result["suggested_quantity_shares"] = None
                market_result["suggested_action_date"] = None
            snapshot = snapshot_store.record_snapshot(
                market_inputs=market_inputs,
                source_receipts=capture.get("source_receipts", []),
                market_result=market_result,
                protocol_sha256=protocol_sha256,
                protocol_verified=protocol_verified,
                implementation_sha256=implementation_sha256,
                judgment_at=capture["judgment_at"],
                received_at=capture["received_at"],
            )
        except Exception as exc:
            _LOGGER.error(
                "Card021 snapshot save failed; stage=%s exception_type=%s",
                stage,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="无法保存可核对的行情快照，本次观察不展示为可用。",
            ) from None
        result.update(snapshot)
        result["snapshot_mode"] = "live_observation"
        return result

    @router.get("/510880/live-observation")
    def get_live_observation(account_mode: str = "actual"):
        if account_mode not in {"actual", "simulated_practice"}:
            raise HTTPException(status_code=400, detail="未知账户类型。")
        now = now_provider() if now_provider is not None else datetime.now(SHANGHAI)
        try:
            _, protocol_sha256 = card020._read_protocol()
        except HTTPException:
            result = {
                "status": "unavailable",
                "failure_code": "frozen_protocol_unavailable",
                "failure_message": "Card020 固定协议无法核验；未请求行情或账户数据。",
                "strategy_id": card020.STRATEGY_ID,
                "protocol_revision": 3,
                "protocol_sha256": card020.PROTOCOL_SHA256,
                "protocol_verified": False,
                "symbol": "510880.SH",
                "selected_account_mode": account_mode,
                "evidence_level": "数据不足",
                "provider_call_attempted": False,
                "provider_responses_received": [],
                "retrieved_at": now.isoformat(timespec="seconds") if now else None,
                "source_origin_authenticated": False,
                "sources": [],
                "target_weight": None,
                "model_reference_shares": None,
                "actual_shares": None,
                "actual_delta_shares": None,
                "action_decision": "not_decidable",
                "judgment_at": _retrieved_at(now),
                "received_at": datetime.now(SHANGHAI).isoformat(timespec="microseconds"),
            }
            return save_snapshot(
                result,
                protocol_sha256=card020.PROTOCOL_SHA256,
                protocol_verified=False,
            )
        resolved_account_provider = account_provider if account_mode == "actual" else None
        if account_mode == "simulated_practice" and practice_account_store is not None:
            resolved_account_provider = lambda signal_date, _latest_date: practice_account_store.account_snapshot(
                as_of_date=now.date(),
                signal_date=signal_date,
            )
        result = get_card021_live_observation(
            market_client_provider,
            account_provider=resolved_account_provider,
            now=now,
        )
        result["protocol_sha256"] = protocol_sha256
        result["protocol_verified"] = True
        result["selected_account_mode"] = account_mode
        if account_mode == "actual":
            result["account_mode"] = "actual_records"
        saved_result = save_snapshot(result, protocol_sha256=protocol_sha256, protocol_verified=True)
        if (
            account_mode == "simulated_practice"
            and practice_account_store is not None
            and type(saved_result.get("account_revision")) is int
        ):
            try:
                metadata = practice_account_store.record_observation(saved_result)
            except Exception as exc:
                _LOGGER.error("Card022 practice observation save failed; exception_type=%s", type(exc).__name__)
                raise HTTPException(status_code=503, detail="无法保存可核对的模拟账户观察，本次结果不展示为可用。") from None
            if metadata:
                saved_result.update(metadata)
        return saved_result

    @router.get("/practice-account")
    def get_practice_account_status():
        if practice_account_store is None:
            raise HTTPException(status_code=503, detail="模拟练习账户暂不可用。")
        try:
            return practice_account_store.get_status()
        except PracticeAccountConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/practice-account/initialize")
    def initialize_practice_account():
        if practice_account_store is None:
            raise HTTPException(status_code=503, detail="模拟练习账户暂不可用。")
        try:
            return practice_account_store.initialize()
        except PracticeAccountConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/510880/practice-observations/{observation_id}")
    def get_practice_observation(observation_id: str):
        if practice_account_store is None:
            raise HTTPException(status_code=503, detail="模拟练习账户暂不可用。")
        try:
            result = practice_account_store.get_observation(observation_id)
        except PracticeAccountConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="指定的模拟账户观察不存在。")
        return result

    @router.get("/510880/snapshots/{snapshot_id}")
    def get_saved_market_snapshot(snapshot_id: str):
        if snapshot_store is None:
            raise HTTPException(status_code=503, detail="行情快照存储当前不可用。")
        try:
            snapshot = snapshot_store.get_snapshot(snapshot_id)
        except Card021SnapshotIntegrityError as exc:
            raise HTTPException(status_code=409, detail="保存的行情快照哈希无法核对，未展示。") from exc
        if snapshot is None:
            raise HTTPException(status_code=404, detail="指定的行情快照不存在。")
        result = dict(snapshot["market_result"])
        result.update({
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "market_input_sha256": snapshot["market_input_sha256"],
            "market_result_sha256": snapshot["market_result_sha256"],
            "protocol_sha256": snapshot["protocol_sha256"],
            "protocol_verified": snapshot["protocol_verified"],
            "implementation_sha256": snapshot["implementation_sha256"],
            "judgment_at": snapshot["judgment_at"],
            "received_at": snapshot["received_at"],
            "snapshot_mode": "saved_market_snapshot",
            "snapshot_historical": True,
            "account_data_status": "not_saved_or_read",
        })
        return result

    return router
