"""Read-only Card020 fixed-input inventory and execution-code fingerprint."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXECUTOR_VERSION = "card020-vol-budget-rev3-v1"
CARD020_PROTOCOL_SHA256 = "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
CARD017_PROTOCOL_SHA256 = "CC1A313AC30A83AEDE8F96DBF5C89D90A2839BC3C647039D6BADE2F9CB29A8DD"
CARD017_PROTOCOL_PATH = PROJECT_ROOT / "docs" / "superpowers" / "protocols" / "2026-10-20-card017-510880-month-end-ma250-v2.md"
CODE_PATHS = (
    "backend/api/card020.py",
    "backend/services/card020_preflight.py",
    "backend/services/card020_store.py",
    "backend/services/card020_vol_budget.py",
    "backend/services/strategy_idea_flow.py",
    "strategy_core/card017_batch_entry.py",  # read-only fixed-input preflight only
    "strategy_core/gate001_market_adapter.py",
    "strategy_core/gate001_dividend_adapter.py",
    "strategy_core/dividend_ledger.py",
    "strategy_core/fill_simulator.py",
    "strategy_core/transaction_costs.py",
    "strategy_core/portfolio.py",
    "strategy_core/trading_calendar.py",
    "contracts/stable.py",
)


class Card020PreflightError(ValueError):
    pass


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _code_fingerprint() -> dict:
    files = {}
    for relative in CODE_PATHS:
        path = (PROJECT_ROOT / relative).resolve()
        if not path.is_relative_to(PROJECT_ROOT) or not path.is_file():
            raise Card020PreflightError("required Card020 execution source is unavailable")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    bundle_hash = hashlib.sha256(
        "\n".join(f"{path}\0{digest}" for path, digest in sorted(files.items())).encode("utf-8")
    ).hexdigest().upper()
    return {
        "executor_version": EXECUTOR_VERSION,
        "bundle_sha256": bundle_hash,
        "files": files,
    }


def _load_existing_fixed_inputs():
    # Existing Card017 input preflight only. This helper returns source objects
    # and metadata; neither historical strategy runner is invoked.
    from strategy_core.card017_batch_entry import _prepare_inputs

    return _prepare_inputs()


def prepare_card020_inputs(*, fixed_input_loader=None) -> dict:
    """Verify the already pinned sources without calculating strategy performance."""
    try:
        card020_raw = (PROJECT_ROOT / "docs" / "510880-vol-budget-v1｜低频波动风险预算策略.md").read_bytes()
        card020_actual = hashlib.sha256(card020_raw).hexdigest().upper()
        card017_raw = CARD017_PROTOCOL_PATH.read_bytes()
        card017_actual = hashlib.sha256(card017_raw).hexdigest().upper()
    except OSError as exc:
        raise Card020PreflightError("a frozen strategy protocol source is unavailable") from exc
    if card020_actual != CARD020_PROTOCOL_SHA256 or card017_actual != CARD017_PROTOCOL_SHA256:
        raise Card020PreflightError("a frozen protocol hash no longer matches its approved revision")

    # This existing Card017 preflight verifies pinned input hashes and exact
    # 2018-2020 dividend coverage. It deliberately does not call either runner.
    try:
        loader = fixed_input_loader or _load_existing_fixed_inputs
        market, calendar, dividend_events, inherited_preflight = loader()
    except Exception as exc:
        raise Card020PreflightError("fixed historical input preflight failed") from exc

    try:
        validation = market.validate()
        validation_status = getattr(validation, "status", "unknown")
        validation_status = getattr(validation_status, "value", validation_status)
        errors = list(getattr(validation, "errors", []))
        warnings = list(getattr(validation, "warnings", []))
        checks_performed = list(getattr(validation, "checks_performed", []))
    except Exception as exc:
        raise Card020PreflightError("fixed market source validation failed") from exc

    market_meta = inherited_preflight["market"]
    dividend_meta = inherited_preflight["dividends"]
    if inherited_preflight.get("historical_strategy_metrics_computed") is not False:
        raise Card020PreflightError("read-only input preflight unexpectedly computed strategy metrics")
    critical_source_gaps = []
    if errors:
        critical_source_gaps.extend(f"Gate001 market validation error: {error}" for error in errors)
    if validation_status == "failed":
        critical_source_gaps.append("Gate001 market validation failed.")
    elif validation_status not in {"pass", "degraded"}:
        critical_source_gaps.append(f"Gate001 market validation status is not recognized: {validation_status}.")

    card017_window_note = dividend_meta.get("card017_window_coverage")
    if not isinstance(card017_window_note, str) or "closed" not in card017_window_note:
        critical_source_gaps.append("The reused Card017 2018-2020 dividend window coverage record is absent.")

    # These are known limits of the already pinned research sources. Keep them
    # visible and lower evidence strength without turning provider-origin
    # authentication into a new prerequisite for this fixed research card.
    data_limitations = [
        "固定行情快照的 manifest 与原始文件哈希可复核，但不认证提供方来源或完整历史覆盖。",
        "开盘可交易状态由固定行情字段推导，未获交易所认证，且不模拟排队优先级和盘中部分停牌。",
        "成交量与成交额单位按随附字段文档解释，但原始快照清单没有把该文档绑定到原始文件。",
        "分红快照仍保留原始适配器的未验证标记；2018–2020 窗口沿用卡017已关闭的覆盖记录与有限官方抽查。",
    ]

    data_inventory = {
        "card020_protocol": {"revision": 3, "sha256": card020_actual},
        "card017_protocol_v2": {"sha256": card017_actual},
        "market": {
            "snapshot_id": market_meta["snapshot_id"],
            "source_status": market_meta["status"],
            "manifest_sha256": market_meta["manifest_sha256"],
            "raw_files": market_meta["raw_file_hashes"],
            "first_date": market_meta["first_date"],
            "last_date": market_meta["last_date"],
            "preheat_end_present": market_meta["preheat_end_present"],
            "preheat_sessions_through_2017_12_29": market_meta["preheat_sessions_through_2017_12_29"],
            "research_window_sessions": market_meta["research_window_sessions"],
            "window_start_present": market_meta["window_start_present"],
            "window_end_present": market_meta["window_end_present"],
            "adapter_validation_status": str(validation_status),
            "validation_errors": errors,
            "validation_warnings": warnings,
            "checks_performed": checks_performed,
            "documented_units": {
                "fund_daily.vol": "the supplied Tushare field documentation defines lots; the existing adapter's ×100 share conversion matches it, but the snapshot manifest does not bind that documentation to the raw files",
                "fund_daily.amount": "the supplied Tushare field documentation defines thousand CNY; the existing adapter's ×1000 conversion matches it, but the snapshot manifest does not bind that documentation to the raw files",
            },
            "provider_origin_authenticated": False,
        },
        "dividends": {
            "snapshot_id": dividend_meta["snapshot_id"],
            "source_status": dividend_meta["raw_snapshot_status"],
            "manifest_sha256": dividend_meta["manifest_sha256"],
            "raw_files": dividend_meta["raw_file_hashes"],
            "window_event_count": len(dividend_events),
            "window_events": dividend_meta["window_events"],
            "official_spotcheck_dates": dividend_meta["official_spotcheck_dates"],
            "coverage_record": card017_window_note,
            "historical_adapter_note": dividend_meta["historical_adapter_note"],
        },
        "historical_metrics_computed": False,
        "evidence_level": "low",
        "data_limitations": data_limitations,
    }
    inventory_sha256 = _sha(data_inventory)
    code_fingerprint = _code_fingerprint()
    preflight = {
        "preflight_id": f"card020_preflight_{uuid.uuid4().hex}",
        "status": "passed_with_disclosed_data_limits" if not critical_source_gaps else "blocked",
        "strategy_id": "510880-vol-budget-v1",
        "protocol_sha256": card020_actual,
        "input_inventory_sha256": inventory_sha256,
        "input_inventory": data_inventory,
        "execution_fingerprint": code_fingerprint,
        "critical_source_gaps": critical_source_gaps,
        "historical_metrics_computed": False,
        "evidence_level": "low",
        "data_limitations": data_limitations,
    }
    preflight["preflight_sha256"] = _sha({key: value for key, value in preflight.items() if key != "preflight_id"})
    return {
        "preflight": preflight,
        "market": market,
        "calendar": calendar,
        "dividend_events": dividend_events,
        "data_provenance": {
            "market": {
                "snapshot_id": market_meta["snapshot_id"],
                "source_status": market_meta["status"],
                "manifest_sha256": market_meta["manifest_sha256"],
                "raw_files": market_meta["raw_file_hashes"],
                "adapter_validation_status": str(validation_status),
                "validation_errors": errors,
                "validation_warnings": warnings,
                "checks_performed": checks_performed,
                "provider_origin_authenticated": False,
                "documented_units": data_inventory["market"]["documented_units"],
            },
            "dividends": {
                "snapshot_id": dividend_meta["snapshot_id"],
                "source_status": dividend_meta["raw_snapshot_status"],
                "manifest_sha256": dividend_meta["manifest_sha256"],
                "raw_files": dividend_meta["raw_file_hashes"],
                "window_event_count": len(dividend_events),
                "coverage_record": card017_window_note,
                "evidence_gap": dividend_meta["historical_adapter_note"],
            },
            "critical_source_gaps": critical_source_gaps,
            "data_limitations": data_limitations,
            "evidence_level": "low",
            "input_inventory_sha256": inventory_sha256,
            "preflight_id": preflight["preflight_id"],
        },
    }
