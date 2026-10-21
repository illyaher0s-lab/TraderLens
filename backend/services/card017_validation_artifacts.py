"""Read-only, hash-bound projection of the frozen Card 017 research artifacts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping


_EXTERNAL_ROOT = Path(r"D:\TraderLens_validation\card017-20261020")
ARTIFACT_FILENAMES = {
    "protocol_v2": "2026-10-20-card017-510880-month-end-ma250-v2.md",
    "batch_ledger_json": "batch-001-ledger.json",
    "summary_provenance": "card017-summary-provenance.json",
    "window_summary": "card017-window-summary.csv",
    "comparison": "card017-v2-comparison.csv",
    "daily_ledger": "card017-daily-ledger.csv",
    "attempt_ledger": "card017-attempt-ledger.csv",
    "dividend_ledger": "card017-dividend-ledger.csv",
    "review_report": "card017-illya-review.md",
}
DEFAULT_ARTIFACT_PATHS = {
    "protocol_v2": (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "superpowers"
        / "protocols"
        / ARTIFACT_FILENAMES["protocol_v2"]
    ),
    **{
        artifact_id: _EXTERNAL_ROOT / filename
        for artifact_id, filename in ARTIFACT_FILENAMES.items()
        if artifact_id != "protocol_v2"
    },
}
EXPECTED_SHA256 = {
    "protocol_v2": "CC1A313AC30A83AEDE8F96DBF5C89D90A2839BC3C647039D6BADE2F9CB29A8DD",
    "batch_ledger_json": "04A6CDF8D65FF16D580A23FD69868BB9491146BE5854DFF07DD3AFC0155939E3",
    "summary_provenance": "A92279959ACFD54A025CE86455C64B571C6EC194E1A0EA4A4103FD455C3D6DBD",
    "window_summary": "FC4D5191A78FC4E61F17F312FF4263FAF8C3B66CE886BC99B51CE0848A0168AA",
    "comparison": "FC241D008D051B8CA3155FA097C5F1BB0E42C8F515A7CE75453DC23B11B111E7",
    "daily_ledger": "756ED96A342C2C646DFEE9BCB745BDE943764233CE16CE5F0F7041DA016911F5",
    "attempt_ledger": "AF5CC86546EC841C6159BC7DC4BA6CBB3B4AF063E223E501F35566BB85C9CC6E",
    "dividend_ledger": "7284B8A54895BB124D236E21B5E8FA33ECC77ED91C30F2F97505FFFBFB339081",
    "review_report": "6297B28DB2C7DFA6FC7B25D243B8C8F9AC571D0E8F861DCA9CFA98B6CFC8BA34",
}

_BATCH_ID = "card017-510880-2018-2020-v1-001"
_CLASSIFICATION = "风险改善伴收益让步"
_REPORT_CONCLUSION = "存在收益让步与风险改善的取舍，待 Illya 权衡。"
_MARKET_STATUS = "downloaded_unverified_for_research_use"
_DIVIDEND_STATUS = "raw_unverified (preserved from the existing adapter)"
_WINDOWS = ("full", "2018-2019", "2020")
_COST_SCENARIOS = ("基础 5bp", "压力 10bp")
_ACCOUNTS = ("候选", "买入持有")
_CLASSIFICATIONS = {
    "收益改善伴风险代价",
    "风险改善伴收益让步",
    "无增益",
    "不支持额外交易/暂不采用",
    "结果不稳定/证据有限",
    "证据不足",
}
_SUMMARY_FIELDS = (
    "net_gain_actual_cny",
    "net_gain_5000_equiv_cny",
    "estimated_exit_cost_actual_cny",
    "estimated_exit_cost_5000_equiv_cny",
    "max_drawdown_amount_protocol_cny",
    "max_drawdown_ratio",
    "commission_actual_cny",
    "commission_5000_equiv_cny",
    "slippage_cost_actual_cny",
    "slippage_cost_5000_equiv_cny",
    "average_exposure_ratio",
)
_WINDOW_METADATA_FIELDS = ("start_date", "end_date", "start_nav_actual_cny")
_COMPARISON_FIELDS = (
    "delta_wealth_cny",
    "delta_drawdown_cny",
    "classification_v2_section8",
)
_OUTPUT_ARTIFACTS = (
    "review_report",
    "window_summary",
    "comparison",
    "daily_ledger",
    "attempt_ledger",
    "dividend_ledger",
)
_LOCAL_PATH_PATTERN = re.compile(
    rb"(?<![a-z0-9])[a-z]:[\\/]|^\s*\\\\[^\\/\r\n]+[\\/]|^\s*/(?:home|users|private)/",
    re.IGNORECASE | re.MULTILINE,
)


class Card017ArtifactsUnavailable(Exception):
    """Raised when any fixed Card 017 source cannot be verified."""


@dataclass(frozen=True)
class VerifiedCard017Artifacts:
    historical_results: dict
    bytes_by_id: dict[str, bytes]
    safe_download_ids: frozenset[str]


def _read_verified_bytes(
    *,
    path_overrides: Mapping[str, str | Path] | None = None,
    expected_sha256: Mapping[str, str] | None = None,
) -> dict[str, bytes]:
    paths = dict(DEFAULT_ARTIFACT_PATHS)
    if path_overrides is not None:
        if set(path_overrides) != set(ARTIFACT_FILENAMES):
            raise Card017ArtifactsUnavailable
        paths = {key: Path(value) for key, value in path_overrides.items()}

    expected = EXPECTED_SHA256 if expected_sha256 is None else expected_sha256
    if set(expected) != set(ARTIFACT_FILENAMES):
        raise Card017ArtifactsUnavailable

    verified: dict[str, bytes] = {}
    try:
        for artifact_id in ARTIFACT_FILENAMES:
            resolved = paths[artifact_id].resolve(strict=True)
            if not resolved.is_file():
                raise Card017ArtifactsUnavailable
            raw = resolved.read_bytes()
            actual = hashlib.sha256(raw).hexdigest().upper()
            if actual != expected[artifact_id].upper():
                raise Card017ArtifactsUnavailable
            verified[artifact_id] = raw
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise Card017ArtifactsUnavailable from exc

    return verified


def _decode_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Card017ArtifactsUnavailable from exc
    if not isinstance(value, dict):
        raise Card017ArtifactsUnavailable
    return value


def _read_csv(raw: bytes) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
    except (UnicodeDecodeError, csv.Error, TypeError) as exc:
        raise Card017ArtifactsUnavailable from exc
    if not rows:
        raise Card017ArtifactsUnavailable
    return rows


def _verify_provenance(provenance: dict, expected_sha256: Mapping[str, str]) -> None:
    if (
        provenance.get("batch_id") != _BATCH_ID
        or provenance.get("result_sha256") != expected_sha256["batch_ledger_json"]
        or provenance.get("protocol_sha256") != expected_sha256["protocol_v2"]
        or provenance.get("reconciliation_status") != "RECONCILED"
        or provenance.get("historical_runs") != 1
        or provenance.get("market_status") != _MARKET_STATUS
        or provenance.get("dividend_raw_status") != _DIVIDEND_STATUS
        or provenance.get("research_conclusion") != _REPORT_CONCLUSION
    ):
        raise Card017ArtifactsUnavailable

    classifications = provenance.get("section8_classifications")
    if classifications != [_CLASSIFICATION] * 6:
        raise Card017ArtifactsUnavailable

    outputs = provenance.get("outputs")
    if not isinstance(outputs, dict):
        raise Card017ArtifactsUnavailable
    for artifact_id in _OUTPUT_ARTIFACTS:
        filename = ARTIFACT_FILENAMES[artifact_id]
        output = outputs.get(filename)
        if not isinstance(output, dict) or output.get("sha256") != expected_sha256[artifact_id]:
            raise Card017ArtifactsUnavailable


def _ratio_as_percent(value: str) -> str:
    try:
        ratio = Decimal(value)
        if not ratio.is_finite():
            raise InvalidOperation
        return format((ratio * Decimal("100")).quantize(Decimal("0.00000001")), "f")
    except (InvalidOperation, ValueError) as exc:
        raise Card017ArtifactsUnavailable from exc


def _validate_rows(
    window_rows: list[dict[str, str]], comparison_rows: list[dict[str, str]], expected_sha256: Mapping[str, str]
) -> list[dict]:
    expected_pairs = {
        (window, scenario) for window in _WINDOWS for scenario in _COST_SCENARIOS
    }
    windows: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in window_rows:
        key = (row.get("window", ""), row.get("cost_scenario", ""), row.get("account", ""))
        if (
            key[:2] not in expected_pairs
            or key[2] not in _ACCOUNTS
            or key in windows
            or row.get("batch_id") != _BATCH_ID
            or row.get("protocol_sha256") != expected_sha256["protocol_v2"]
            or row.get("result_sha256") != expected_sha256["batch_ledger_json"]
            or any(not row.get(field) for field in _WINDOW_METADATA_FIELDS)
            or any(not row.get(field) for field in _SUMMARY_FIELDS)
        ):
            raise Card017ArtifactsUnavailable
        windows[key] = row

    if set(windows) != {
        (window, scenario, account)
        for window, scenario in expected_pairs
        for account in _ACCOUNTS
    }:
        raise Card017ArtifactsUnavailable

    full_start = windows[("full", "基础 5bp", "候选")]
    if (
        full_start["start_date"] != "2018-01-02"
        or full_start["end_date"] != "2020-12-31"
        or full_start["start_nav_actual_cny"] != "5000.00"
    ):
        raise Card017ArtifactsUnavailable

    comparisons: dict[tuple[str, str], dict[str, str]] = {}
    for row in comparison_rows:
        key = (row.get("window", ""), row.get("cost_scenario", ""))
        if (
            key not in expected_pairs
            or key in comparisons
            or row.get("batch_id") != _BATCH_ID
            or row.get("protocol_sha256") != expected_sha256["protocol_v2"]
            or row.get("result_sha256") != expected_sha256["batch_ledger_json"]
            or row.get("classification_v2_section8") != _CLASSIFICATION
            or any(not row.get(field) for field in _COMPARISON_FIELDS)
        ):
            raise Card017ArtifactsUnavailable
        comparisons[key] = row

    if set(comparisons) != expected_pairs:
        raise Card017ArtifactsUnavailable

    result = []
    for window in _WINDOWS:
        for scenario in _COST_SCENARIOS:
            key = (window, scenario)
            accounts = {}
            for account in _ACCOUNTS:
                row = windows[(window, scenario, account)]
                metrics = {field: row[field] for field in _SUMMARY_FIELDS}
                metrics["max_drawdown_ratio_percent"] = _ratio_as_percent(
                    row["max_drawdown_ratio"]
                )
                metrics["average_exposure_percent"] = _ratio_as_percent(
                    row["average_exposure_ratio"]
                )
                accounts[account] = metrics
            comparison = comparisons[key]
            result.append(
                {
                    "window": window,
                    "cost_scenario": scenario,
                    "start_date": windows[(window, scenario, "候选")]["start_date"],
                    "end_date": windows[(window, scenario, "候选")]["end_date"],
                    "candidate": accounts["候选"],
                    "buy_and_hold": accounts["买入持有"],
                    "comparison": {
                        "delta_wealth_cny": comparison["delta_wealth_cny"],
                        "delta_drawdown_cny": comparison["delta_drawdown_cny"],
                        "classification": comparison["classification_v2_section8"],
                    },
                }
            )
    return result


def _safe_provenance_projection(provenance: dict) -> dict:
    outputs = []
    for artifact_id in _OUTPUT_ARTIFACTS:
        filename = ARTIFACT_FILENAMES[artifact_id]
        output = provenance["outputs"][filename]
        outputs.append(
            {
                "artifact_id": artifact_id,
                "filename": filename,
                "sha256": output["sha256"],
                "rows": output.get("rows"),
            }
        )
    return {
        "batch_id": provenance["batch_id"],
        "result_sha256": provenance["result_sha256"],
        "protocol_sha256": provenance["protocol_sha256"],
        "historical_execution_code_sha256": provenance["code_sha256"],
        "generated_at_utc": provenance["generated_at_utc"],
        "market_status": provenance["market_status"],
        "dividend_raw_status": provenance["dividend_raw_status"],
        "reconciliation_status": provenance["reconciliation_status"],
        "historical_runs": provenance["historical_runs"],
        "section8_classifications": provenance["section8_classifications"],
        "research_conclusion": provenance["research_conclusion"],
        "outputs": outputs,
    }


def _artifact_links(safe_download_ids: frozenset[str]) -> list[dict[str, str]]:
    labels = {
        "protocol_v2": "冻结协议 V2",
        "batch_ledger_json": "模拟账单 JSON",
        "summary_provenance": "核账来源摘要（安全投影）",
        "window_summary": "窗口汇总 CSV",
        "comparison": "六格比较 CSV",
        "daily_ledger": "日账 CSV（模拟）",
        "attempt_ledger": "订单尝试 CSV（模拟）",
        "dividend_ledger": "分红账 CSV（模拟）",
        "review_report": "卡017原报告",
    }
    result = [
        {
            "artifact_id": "summary_provenance",
            "label": labels["summary_provenance"],
            "url": "/api/strategy-validations/historical/card017/artifacts/summary_provenance",
        }
    ]
    for artifact_id in ARTIFACT_FILENAMES:
        if artifact_id == "summary_provenance" or artifact_id not in safe_download_ids:
            continue
        result.append(
            {
                "artifact_id": artifact_id,
                "label": labels[artifact_id],
                "url": f"/api/strategy-validations/historical/card017/artifacts/{artifact_id}",
            }
        )
    return result


def load_card017_artifacts(
    *,
    path_overrides: Mapping[str, str | Path] | None = None,
    expected_sha256: Mapping[str, str] | None = None,
) -> VerifiedCard017Artifacts:
    """Read each fixed source once, verify its hash, then parse/serve those bytes."""
    expected = EXPECTED_SHA256 if expected_sha256 is None else expected_sha256
    try:
        raw_by_id = _read_verified_bytes(
            path_overrides=path_overrides,
            expected_sha256=expected,
        )
        provenance = _decode_json(raw_by_id["summary_provenance"])
        _verify_provenance(provenance, expected)
        report = raw_by_id["review_report"].decode("utf-8")
        if _REPORT_CONCLUSION not in report:
            raise Card017ArtifactsUnavailable

        window_rows = _read_csv(raw_by_id["window_summary"])
        comparison_rows = _read_csv(raw_by_id["comparison"])
        comparisons = _validate_rows(window_rows, comparison_rows, expected)
        full_start = next(
            row
            for row in window_rows
            if row["window"] == "full"
            and row["cost_scenario"] == "基础 5bp"
            and row["account"] == "候选"
        )
        safe_download_ids = frozenset(
            artifact_id
            for artifact_id in ARTIFACT_FILENAMES
            if artifact_id != "summary_provenance"
            and not _LOCAL_PATH_PATTERN.search(raw_by_id[artifact_id])
        )
        safe_provenance = _safe_provenance_projection(provenance)
        result = {
            "status": "available",
            "items": [
                {
                    "case_id": _BATCH_ID,
                    "symbol": "510880",
                    "strategy_name": "月末 MA250",
                    "benchmark_name": "买入持有",
                    "period_start_date": full_start["start_date"],
                    "period_end_date": full_start["end_date"],
                    "starting_capital_cny": full_start["start_nav_actual_cny"],
                    "commission_basis": (
                        "买卖两侧佣金=max(成交金额×0.0003,5元/笔)；无其他手续费，"
                        "印花税和过户费设为0。"
                    ),
                    "run_status": "COMPLETED",
                    "reconciliation_status": "RECONCILED",
                    "protocol_version": "V2",
                    "protocol_sha256": expected["protocol_v2"],
                    "result_sha256": expected["batch_ledger_json"],
                    "historical_execution_code_sha256": provenance["code_sha256"],
                    "program_classification": _CLASSIFICATION,
                    "original_report_conclusion": provenance["research_conclusion"],
                    "report_generated_at_utc": provenance["generated_at_utc"],
                    "arden_recommendation": {
                        "advisor": "Arden（独立顾问）",
                        "value": "暂不采用",
                        "source": "Illya 在卡018启动指令中记录的独立顾问建议",
                        "is_illya_formal_decision": False,
                    },
                    "acceptance_status": "待确认",
                    "formal_qualification": "未授予",
                    "evidence_level": "仅研究参考",
                    "actionable": False,
                    "market_status": provenance["market_status"],
                    "dividend_raw_status": provenance["dividend_raw_status"],
                    "research_assumptions": [
                        "日线开盘成交与前日成交量10%容量为模拟假设",
                        "基础5bp与压力10bp滑点为模拟假设",
                        "2020为时间留出段，但不是独立OOS",
                    ],
                    "metric_semantics": {
                        "net_gain": "净收益已扣除假设期末退出成本",
                        "drawdown_amount": "协议口径的5000元等值账面NAV回撤",
                        "2020": "实际账户值与5000元等值比较值分列",
                    },
                    "comparisons": comparisons,
                    "provenance": safe_provenance,
                    "artifacts": _artifact_links(safe_download_ids),
                }
            ],
        }
    except Card017ArtifactsUnavailable:
        raise
    except (KeyError, TypeError, ValueError, InvalidOperation, csv.Error) as exc:
        raise Card017ArtifactsUnavailable from exc

    return VerifiedCard017Artifacts(
        historical_results=result,
        bytes_by_id=raw_by_id,
        safe_download_ids=safe_download_ids,
    )


def unavailable_card017_historical_results() -> dict:
    return {
        "status": "unavailable",
        "reason_code": "card017_source_unavailable",
        "message": "卡017历史研究结果的来源暂不可验证，当前不展示数据。",
        "items": [],
    }
