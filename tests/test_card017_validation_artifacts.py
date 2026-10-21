import csv
import hashlib
import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import strategy_validations
from backend.services.card017_validation_artifacts import (
    ARTIFACT_FILENAMES,
    load_card017_artifacts,
)


_BATCH_ID = "card017-510880-2018-2020-v1-001"
_CLASSIFICATION = "风险改善伴收益让步"
_REPORT_CONCLUSION = "存在收益让步与风险改善的取舍，待 Illya 权衡。"
_WINDOWS = ("full", "2018-2019", "2020")
_SCENARIOS = ("基础 5bp", "压力 10bp")
_ACCOUNTS = ("候选", "买入持有")


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def _csv_bytes(fieldnames, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _fixture_files(tmp_path, *, path_token_artifact=None):
    protocol = b"# V2 fixture protocol\n"
    ledger = json.dumps({"batch_id": _BATCH_ID}, separators=(",", ":")).encode()
    files = {
        "protocol_v2": protocol,
        "batch_ledger_json": ledger,
        "daily_ledger": b"batch_id,date,nav\nfixture,2020-01-01,5000.00\n",
        "attempt_ledger": b"batch_id,intent_id,status\nfixture,intent-1,filled\n",
        "dividend_ledger": b"batch_id,event_index,div_cash\nfixture,1,0.00\n",
        "review_report": ("卡017报告：" + _REPORT_CONCLUSION + "\n").encode("utf-8"),
    }
    if path_token_artifact is not None:
        files[path_token_artifact] = b"D:\\private\\server\\source.csv\n"

    window_fields = [
        "batch_id",
        "protocol_sha256",
        "result_sha256",
        "window",
        "cost_scenario",
        "account",
        "start_date",
        "end_date",
        "start_nav_actual_cny",
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
    ]
    window_rows = []
    for window in _WINDOWS:
        for scenario in _SCENARIOS:
            for account in _ACCOUNTS:
                window_rows.append(
                    {
                        "batch_id": _BATCH_ID,
                        "protocol_sha256": _sha256(protocol),
                        "result_sha256": _sha256(ledger),
                        "window": window,
                        "cost_scenario": scenario,
                        "account": account,
                        "start_date": {
                            "full": "2018-01-02",
                            "2018-2019": "2018-01-02",
                            "2020": "2019-12-31",
                        }[window],
                        "end_date": {
                            "full": "2020-12-31",
                            "2018-2019": "2019-12-31",
                            "2020": "2020-12-31",
                        }[window],
                        "start_nav_actual_cny": "5300.00" if window == "2020" else "5000.00",
                        "net_gain_actual_cny": "-10.00" if account == "候选" else "-2.00",
                        "net_gain_5000_equiv_cny": (
                            "-12.00" if window == "2020" and account == "候选" else "-10.00"
                        ) if account == "候选" else ("-3.00" if window == "2020" else "-2.00"),
                        "estimated_exit_cost_actual_cny": "1.00",
                        "estimated_exit_cost_5000_equiv_cny": "1.00",
                        "max_drawdown_amount_protocol_cny": "100.00",
                        "max_drawdown_ratio": "0.1000000000",
                        "commission_actual_cny": "2.00",
                        "commission_5000_equiv_cny": "2.00",
                        "slippage_cost_actual_cny": "1.00",
                        "slippage_cost_5000_equiv_cny": "1.00",
                        "average_exposure_ratio": "0.5000000000",
                    }
                )
    files["window_summary"] = _csv_bytes(window_fields, window_rows)

    comparison_fields = [
        "batch_id",
        "protocol_sha256",
        "result_sha256",
        "window",
        "cost_scenario",
        "delta_wealth_cny",
        "delta_drawdown_cny",
        "classification_v2_section8",
    ]
    comparison_rows = [
        {
            "batch_id": _BATCH_ID,
            "protocol_sha256": _sha256(protocol),
            "result_sha256": _sha256(ledger),
            "window": window,
            "cost_scenario": scenario,
            "delta_wealth_cny": "-8.00",
            "delta_drawdown_cny": "20.00",
            "classification_v2_section8": _CLASSIFICATION,
        }
        for window in _WINDOWS
        for scenario in _SCENARIOS
    ]
    files["comparison"] = _csv_bytes(comparison_fields, comparison_rows)

    output_ids = (
        "review_report",
        "window_summary",
        "comparison",
        "daily_ledger",
        "attempt_ledger",
        "dividend_ledger",
    )
    outputs = {
        ARTIFACT_FILENAMES[artifact_id]: {
            "sha256": _sha256(files[artifact_id]),
            "rows": {"window_summary": 12, "comparison": 6}.get(artifact_id),
            "path": r"C:\private\server\source",
        }
        for artifact_id in output_ids
    }
    provenance = {
        "batch_id": _BATCH_ID,
        "result_sha256": _sha256(ledger),
        "protocol_sha256": _sha256(protocol),
        "code_sha256": "A" * 64,
        "generated_at_utc": "2026-10-20T03:46:17.258489+00:00",
        "market_status": "downloaded_unverified_for_research_use",
        "dividend_raw_status": "raw_unverified (preserved from the existing adapter)",
        "reconciliation_status": "RECONCILED",
        "historical_runs": 1,
        "section8_classifications": [_CLASSIFICATION] * 6,
        "research_conclusion": _REPORT_CONCLUSION,
        "outputs": outputs,
        "result_path": r"C:\private\server\result.json",
        "summary_builder": r"C:\private\server\build_summary.py",
    }
    files["summary_provenance"] = json.dumps(
        provenance, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    paths = {}
    for artifact_id, filename in ARTIFACT_FILENAMES.items():
        path = tmp_path / filename
        path.write_bytes(files[artifact_id])
        paths[artifact_id] = path
    expected = {artifact_id: _sha256(raw) for artifact_id, raw in files.items()}
    return {"files": files, "paths": paths, "expected": expected}


def _client(monkeypatch, fixture):
    def load_fixture():
        return load_card017_artifacts(
            path_overrides=fixture["paths"],
            expected_sha256=fixture["expected"],
        )

    monkeypatch.setattr(strategy_validations, "load_card017_artifacts", load_fixture)
    monkeypatch.setattr(
        strategy_validations,
        "load_strategy_validation_status",
        lambda: {"status": "unavailable", "actionable": False},
    )
    app = FastAPI()
    app.include_router(strategy_validations.router)
    return TestClient(app)


def test_card017_history_is_separate_from_qualified_validation_cases(tmp_path, monkeypatch):
    fixture = _fixture_files(tmp_path)
    response = _client(monkeypatch, fixture).get("/api/strategy-validations").json()

    assert response["validations"] == []
    assert response["count"] == 0
    history = response["historical_results"]
    assert history["status"] == "available"
    assert len(history["items"]) == 1

    card = history["items"][0]
    assert card["case_id"] == _BATCH_ID
    assert card["program_classification"] == _CLASSIFICATION
    assert card["arden_recommendation"]["value"] == "暂不采用"
    assert card["arden_recommendation"]["is_illya_formal_decision"] is False
    assert card["acceptance_status"] == "待确认"
    assert card["formal_qualification"] == "未授予"
    assert card["actionable"] is False
    assert card["period_start_date"] == "2018-01-02"
    assert card["period_end_date"] == "2020-12-31"
    assert card["starting_capital_cny"] == "5000.00"
    assert card["commission_basis"] == (
        "买卖两侧佣金=max(成交金额×0.0003,5元/笔)；无其他手续费，"
        "印花税和过户费设为0。"
    )
    assert len(card["comparisons"]) == 6
    window_2020 = next(row for row in card["comparisons"] if row["window"] == "2020")
    assert window_2020["candidate"]["net_gain_actual_cny"] == "-10.00"
    assert window_2020["candidate"]["net_gain_5000_equiv_cny"] == "-12.00"
    assert window_2020["start_date"] == "2019-12-31"
    assert window_2020["end_date"] == "2020-12-31"
    assert window_2020["candidate"]["max_drawdown_ratio_percent"] == "10.00000000"


@pytest.mark.parametrize("artifact_id", tuple(ARTIFACT_FILENAMES))
@pytest.mark.parametrize("damage", ("missing", "tampered"))
def test_any_missing_or_hash_mismatched_source_fails_closed(
    tmp_path, monkeypatch, artifact_id, damage
):
    fixture = _fixture_files(tmp_path)
    source = fixture["paths"][artifact_id]
    if damage == "missing":
        source.unlink()
    else:
        source.write_bytes(b"tampered after the pinned digest")

    response = _client(monkeypatch, fixture).get("/api/strategy-validations")
    body = response.json()
    assert body["historical_results"]["status"] == "unavailable"
    assert body["historical_results"]["items"] == []
    assert "C:\\private\\server" not in response.text
    assert source.name not in response.text


def test_provenance_projection_and_fixed_download_route_hide_paths(
    tmp_path, monkeypatch
):
    fixture = _fixture_files(tmp_path)
    client = _client(monkeypatch, fixture)

    listing = client.get("/api/strategy-validations")
    assert "C:\\private\\server" not in listing.text
    assert "result_path" not in listing.text
    assert "summary_builder" not in listing.text

    projection = client.get(
        "/api/strategy-validations/historical/card017/artifacts/summary_provenance"
    )
    assert projection.status_code == 200
    assert "C:\\private\\server" not in projection.text
    assert "result_path" not in projection.text
    assert "summary_builder" not in projection.text

    unknown = client.get(
        "/api/strategy-validations/historical/card017/artifacts/anything"
    )
    traversal = client.get(
        "/api/strategy-validations/historical/card017/artifacts/../../private"
    )
    assert unknown.status_code == 404
    assert traversal.status_code == 404
    assert client.post(
        "/api/strategy-validations/historical/card017/artifacts/batch_ledger_json"
    ).status_code == 405


def test_download_returns_the_same_bytes_that_were_hash_verified(
    tmp_path, monkeypatch
):
    fixture = _fixture_files(tmp_path)
    original = fixture["files"]["batch_ledger_json"]

    def load_then_change_source():
        verified = load_card017_artifacts(
            path_overrides=fixture["paths"],
            expected_sha256=fixture["expected"],
        )
        fixture["paths"]["batch_ledger_json"].write_bytes(b"changed after verification")
        return verified

    monkeypatch.setattr(strategy_validations, "load_card017_artifacts", load_then_change_source)
    app = FastAPI()
    app.include_router(strategy_validations.router)
    response = TestClient(app).get(
        "/api/strategy-validations/historical/card017/artifacts/batch_ledger_json"
    )

    assert response.status_code == 200
    assert response.content == original
    assert "batch-001-ledger.json" in response.headers["content-disposition"]


def test_path_containing_source_is_not_downloaded(tmp_path, monkeypatch):
    fixture = _fixture_files(tmp_path, path_token_artifact="daily_ledger")
    client = _client(monkeypatch, fixture)

    listing = client.get("/api/strategy-validations")
    assert listing.json()["historical_results"]["status"] == "available"
    artifact_ids = {
        artifact["artifact_id"]
        for artifact in listing.json()["historical_results"]["items"][0]["artifacts"]
    }
    assert "daily_ledger" not in artifact_ids
    download = client.get(
        "/api/strategy-validations/historical/card017/artifacts/daily_ledger"
    )
    assert download.status_code == 503
    assert "D:\\private\\server" not in download.text
