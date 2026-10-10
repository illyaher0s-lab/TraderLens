"""Small, shared source-precedence contract for v3 liquidity qualification."""
from __future__ import annotations

import hashlib
import json
import math


SOURCE_ADAPTER_ID = "v3_historical_liquidity_suspension_source_adapter_v1"
SOURCE_ADAPTER_CONTRACT = {
    "daily_row_precedence": "valid_daily_amount_before_suspension_evidence",
    "valid_daily_amount": "finite_nonnegative",
    "invalid_daily_amount": "data_fault",
    "missing_daily_exact_suspend_types": ["S", "P"],
    "missing_daily_interval_evidence": "qualified_active_S_to_later_R",
    "missing_daily_interval_amount_yuan": 0.0,
    "r_only": "data_fault",
    "other_missing": "data_fault",
}
SOURCE_ADAPTER_CONTRACT_HASH = hashlib.sha256(
    json.dumps(SOURCE_ADAPTER_CONTRACT, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


def _valid_amount(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) >= 0


def resolve_source_amount(*, daily_row: dict | None, suspend_rows: list[dict], interval_evidence: dict | None = None) -> dict:
    """Resolve one completed source day without letting suspension mask bad daily data."""
    if daily_row is not None:
        amount = daily_row.get("amount")
        if not _valid_amount(amount):
            return {"status": "data_fault", "reason": "daily_amount_invalid"}
        return {"status": "daily", "amount_yuan": float(amount) * 1000.0}

    suspend_types = {row.get("suspend_type") for row in suspend_rows}
    if suspend_types.intersection({"S", "P"}):
        return {"status": "suspended", "amount_yuan": 0.0}
    if interval_evidence and interval_evidence.get("qualified") is True:
        return {"status": "suspended", "amount_yuan": 0.0}
    return {"status": "data_fault", "reason": "daily_missing_without_suspension_evidence"}
