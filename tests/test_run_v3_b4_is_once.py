import json
import os
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from contracts.stable import DailyBar
import scripts.run_v3_b4_is_once as b4_runner
from scripts.run_v3_b4_is_once import (
    _ReadBoundDataSource,
    run_v3_b4_is_once,
    verify_v3_b4_is_result,
)
from strategy_core.v3_relative_strength_executor import _rank_snapshot
from tests.test_v3_relative_strength_executor import FakeV3Data


ROOT = Path(__file__).resolve().parents[1]


def _prepare_temp_b4_fixture(tmp_path: Path, monkeypatch):
    import scripts.publish_v3_execution_semantics as publisher_module
    from scripts.verify_v3_execution_semantics import (
        verify_v3_execution_semantics as official_verify,
    )
    from tests.test_v3_execution_semantics import _copy_fixture_repo

    repo_root = _copy_fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(
        publisher_module,
        "OWNER_APPROVAL_DIR",
        repo_root / "data/pit/market_regime_owner_approvals/6170c11c8068f407",
    )
    supplement = publisher_module.publish_v3_execution_semantics(
        output_root=tmp_path / "supplements",
        repo_root=repo_root,
    )
    published_supplement_dir = Path(supplement["path"])
    supplement_dir = repo_root / "data/pit/v3_execution_semantics_supplements" / supplement["supplement_id"]
    supplement_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(published_supplement_dir, supplement_dir)
    monkeypatch.setattr(b4_runner, "SUPPLEMENT_DIR", supplement_dir)
    monkeypatch.setattr(b4_runner, "SUPPLEMENT_ID", supplement["supplement_id"])
    monkeypatch.setattr(
        b4_runner,
        "SUPPLEMENT_MANIFEST_SHA256",
        supplement["manifest_sha256"],
    )

    def verify_temp(path, **kwargs):
        return official_verify(path, repo_root=kwargs.get("repo_root", repo_root))

    monkeypatch.setattr(b4_runner, "verify_v3_execution_semantics", verify_temp)

    real_connect = sqlite3.connect
    connection_targets = []
    production_db = str((ROOT / "data/strategy.db").resolve()).replace("\\", "/").lower()
    temp_db = str((repo_root / "data/strategy.db").resolve()).replace("\\", "/").lower()

    def guarded_connect(database, *args, **kwargs):
        target = str(database)
        normalized = target.replace("\\", "/").lower()
        connection_targets.append(target)
        if production_db in normalized:
            raise AssertionError(f"production SQLite opened: {target}")
        if temp_db not in normalized:
            raise AssertionError(f"non-fixture SQLite opened: {target}")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    return repo_root, supplement_dir, supplement, connection_targets


def _run_temp_b4(fixture, tmp_path: Path, audit_name: str) -> dict:
    repo_root, supplement_dir, _supplement, connection_targets = fixture
    result = b4_runner.run_v3_b4_is_once(
        repo_root=repo_root,
        output_root=tmp_path / "b4-results",
        audit_path=tmp_path / audit_name,
        data_source=_fixture_data(),
        supplement_dir=supplement_dir,
    )
    expected_db = str((repo_root / "data/strategy.db").resolve()).replace("\\", "/").lower()
    assert connection_targets
    assert all(expected_db in target.replace("\\", "/").lower() for target in connection_targets)
    return result


def test_v3_b4_runner_binds_the_new_supplement_and_protocol(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    repo_root, supplement_dir, supplement, _connection_targets = fixture

    assert b4_runner.PROTOCOL_ID == (
        "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
    )
    assert b4_runner.SUPPLEMENT_ID == supplement["supplement_id"]
    assert b4_runner.SUPPLEMENT_MANIFEST_SHA256 == supplement["manifest_sha256"]

    result = _run_temp_b4(fixture, tmp_path, "audit.json")
    manifest = json.loads(
        (Path(result["path"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["protocol_snapshot_id"] == b4_runner.PROTOCOL_ID
    assert manifest["supplement"] == {
        "supplement_id": supplement["supplement_id"],
        "manifest_sha256": supplement["manifest_sha256"],
    }
    assert manifest["protocol_snapshot_id"] != (
        "6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111"
    )
    assert result["read_audit"]["oos_read_count"] == 0
    assert result["read_audit"]["max_requested_date"] == "2026-03-19"
    assert b4_runner.verify_v3_b4_is_result(Path(result["path"]), repo_root=repo_root)["status"] == "verified"


def test_v3_b4_runner_accepts_the_source_current_successor_lineage(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.publish_v3_execution_semantics as publisher_module
    from scripts.verify_v3_execution_semantics import (
        verify_v3_execution_semantics as official_verify,
    )
    from tests.test_v3_execution_semantics import _copy_fixture_repo

    repo_root = _copy_fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(
        publisher_module,
        "OWNER_APPROVAL_DIR",
        repo_root / "data/pit/market_regime_owner_approvals/6170c11c8068f407",
    )
    supplement = publisher_module.publish_v3_execution_semantics(
        output_root=tmp_path / "supplements",
        repo_root=repo_root,
    )
    supplement_dir = Path(supplement["path"])
    verified = official_verify(supplement_dir, repo_root=repo_root)
    assert verified["status"] == "verified"

    output_root = tmp_path / "b4-results"
    audit_path = tmp_path / "audit.json"
    try:
        result = b4_runner.run_v3_b4_is_once(
            repo_root=repo_root,
            output_root=output_root,
            audit_path=audit_path,
            data_source=_fixture_data(),
            supplement_dir=supplement_dir,
        )
    except ValueError as error:
        assert str(error) == "v3 execution supplement exact lineage mismatch"
        assert not output_root.exists()
        assert not audit_path.exists()
        pytest.fail("source-current successor must pass the runner lineage guard")

    manifest = json.loads(
        (Path(result["path"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "published"
    assert manifest["supplement"] == {
        "supplement_id": "185a6b8f03915dca",
        "manifest_sha256": "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895",
    }
    assert result["future_violations"] == 0
    assert result["read_audit"]["oos_read_count"] == 0


def test_v3_b4_runner_projects_one_temp_verified_supplement_into_engine(tmp_path: Path, monkeypatch) -> None:
    from scripts.verify_v3_execution_semantics import (
        verify_v3_execution_semantics as official_verify,
    )

    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    repo_root, supplement_dir, supplement, _connection_targets = fixture

    verifier_calls = []
    engine_calls = []
    verified_results = []

    def verify_spy(path, **kwargs):
        verifier_calls.append((Path(path), dict(kwargs)))
        verified = official_verify(path, repo_root=kwargs.get("repo_root", repo_root))
        verified_results.append(verified)
        return verified

    real_run_event_backtest = b4_runner.run_event_backtest

    def engine_spy(*args, **kwargs):
        engine_calls.append(dict(kwargs))
        return real_run_event_backtest(*args, **kwargs)

    monkeypatch.setattr(b4_runner, "verify_v3_execution_semantics", verify_spy)
    monkeypatch.setattr(b4_runner, "run_event_backtest", engine_spy)
    result = _run_temp_b4(fixture, tmp_path, "audit.json")

    expected_fields = {
        "status",
        "supplement_id",
        "manifest_sha256",
        "strategy_revision_id",
        "protocol_snapshot_id",
        "data_snapshot_hash",
    }
    assert len(verifier_calls) == 1
    assert verifier_calls[0] == (supplement_dir, {"repo_root": repo_root})
    assert len(engine_calls) == 1
    assert engine_calls[0].get("supplement_path") is None
    assert engine_calls[0]["verified_supplement"] == {
        key: verified_results[0][key] for key in expected_fields
    }
    assert result["status"] == "published"
    assert result["future_violations"] == 0


def test_v3_b4_verifier_rejects_missing_new_supplement(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    result = _run_temp_b4(fixture, tmp_path, "audit.json")

    monkeypatch.setattr(b4_runner, "SUPPLEMENT_DIR", tmp_path / "missing-supplement")
    verified = b4_runner.verify_v3_b4_is_result(Path(result["path"]), repo_root=tmp_path / "missing-root")
    assert verified["status"] == "invalid"
    assert "supplement" in verified["reason"]


def test_v3_b4_verifier_accepts_explicit_repo_root_for_supplement_path(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    repo_root, supplement_dir, supplement, _connection_targets = fixture
    result = _run_temp_b4(fixture, tmp_path, "audit-explicit-root.json")
    derived = repo_root / "data/pit/v3_execution_semantics_supplements" / supplement["supplement_id"]
    assert supplement_dir == derived

    verified = b4_runner.verify_v3_b4_is_result(Path(result["path"]), repo_root=repo_root)

    assert verified["status"] == "verified"


def test_v3_b4_verifier_rejects_mixed_old_new_lineage(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    result = _run_temp_b4(fixture, tmp_path, "audit.json")
    manifest_path = Path(result["path"]) / "manifest.json"
    sidecar_path = manifest_path.with_name("manifest.json.sha256")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["supplement"] = {
        "supplement_id": "680cd55c91254667",
        "manifest_sha256": "c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39",
    }
    raw = b4_runner._canonical(manifest)
    manifest_path.write_bytes(raw)
    sidecar_path.write_text(
        f"{b4_runner._sha_bytes(raw)}  manifest.json\n", encoding="utf-8"
    )

    verified = b4_runner.verify_v3_b4_is_result(Path(result["path"]), repo_root=fixture[0])
    assert verified["status"] == "invalid"
    assert "supplement lineage" in verified["reason"]


def test_v3_b4_verifier_rejects_tampered_new_supplement(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    _repo_root, supplement_dir, _supplement, _connection_targets = fixture
    result = _run_temp_b4(fixture, tmp_path, "audit.json")
    supplement_manifest = supplement_dir / "manifest.json"
    supplement_sidecar = supplement_manifest.with_name("manifest.json.sha256")
    tampered = json.loads(supplement_manifest.read_text(encoding="utf-8"))
    tampered["criteria"]["envelope_hash"] = "0" * 64
    raw = b4_runner._canonical(tampered)
    supplement_manifest.write_bytes(raw)
    supplement_sidecar.write_text(
        f"{b4_runner._sha_bytes(raw)}  manifest.json\n", encoding="utf-8"
    )
    monkeypatch.setattr(b4_runner, "SUPPLEMENT_DIR", supplement_dir)

    verified = b4_runner.verify_v3_b4_is_result(Path(result["path"]), repo_root=fixture[0])
    assert verified["status"] == "invalid"
    assert "supplement" in verified["reason"]


def test_v3_b4_artifact_is_deterministic_write_once_and_conflict_safe(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    repo_root, supplement_dir, _supplement, _connection_targets = fixture
    output_root = tmp_path / "b4-results"
    first = _run_temp_b4(fixture, tmp_path, "audit-first.json")
    manifest_path = Path(first["path"]) / "manifest.json"
    event_path = Path(first["path"]) / "event_result.json"
    before_manifest = manifest_path.read_bytes()
    before_event = event_path.read_bytes()
    second = _run_temp_b4(fixture, tmp_path, "audit-second.json")
    assert first["artifact_id"] == second["artifact_id"] != "20960e9fd15cdb44"
    assert second["status"] == "already_published"
    assert manifest_path.read_bytes() == before_manifest
    assert event_path.read_bytes() == before_event

    event_json = json.loads(event_path.read_text(encoding="utf-8"))
    event_json["future_violations"] = ["tampered"]
    with pytest.raises(ValueError, match="write-once conflict"):
        b4_runner._write_once(
            output_root,
            {
                key: value
                for key, value in json.loads(manifest_path.read_text(encoding="utf-8")).items()
                if key != "artifact_id"
            },
            event_json,
        )
    assert manifest_path.read_bytes() == before_manifest
    assert event_path.read_bytes() == before_event


def test_v3_b4_default_audit_is_artifact_keyed_and_preserves_generic_audit(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    repo_root, supplement_dir, _supplement, _connection_targets = fixture
    generic_audit = repo_root / "docs/verification/task4_v3_b4_is_audit.json"
    generic_audit.parent.mkdir(parents=True, exist_ok=True)
    generic_bytes = b'{"immutable":"generic-audit"}\n'
    generic_audit.write_bytes(generic_bytes)
    monkeypatch.setattr(b4_runner, "DEFAULT_AUDIT_PATH", generic_audit)

    result = b4_runner.run_v3_b4_is_once(
        repo_root=repo_root,
        output_root=tmp_path / "b4-results",
        data_source=_fixture_data(),
        supplement_dir=supplement_dir,
    )

    expected_audit = repo_root / "docs/verification" / (
        f"task4_v3_b4_is_audit_{result['artifact_id']}.json"
    )
    assert result["artifact_id"] == "ef2084e797384a23"
    assert expected_audit.is_file()
    assert json.loads(expected_audit.read_text(encoding="utf-8"))["artifact_id"] == result["artifact_id"]
    assert generic_audit.read_bytes() == generic_bytes

    manifest_path = Path(result["path"]) / "manifest.json"
    event_path = Path(result["path"]) / "event_result.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert result["manifest_sha256"] == (
        "6271d37ad6ac9aab64cd55b11c6586387ade6b351c7e576e07e1c0181c9e07c7"
    )
    assert result["manifest_sha256"] == b4_runner._sha(manifest_path)
    assert b4_runner._sha(event_path) == (
        "c737e8fe19602dc32b66a9a30a0184aadeb5dff3ac5efe9d7bbe5676cd27d844"
    )
    assert manifest["event_result"]["sha256"] == b4_runner._sha(event_path)
    assert event["strategy_revision_id"] == b4_runner.REVISION_ID
    assert event["protocol_snapshot_id"] == b4_runner.PROTOCOL_ID


def test_v3_b4_audit_write_once_rejects_conflict_without_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    path.write_bytes(b'{"artifact_id":"different"}\n')
    before_bytes = path.read_bytes()
    before_mtime_ns = path.stat().st_mtime_ns

    with pytest.raises(ValueError, match="audit write-once conflict"):
        b4_runner._save_audit(
            path,
            {"artifact_id": "ef2084e797384a23", "status": "published"},
        )

    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime_ns


def test_v3_b4_audit_write_once_is_idempotent_for_same_canonical_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.json"
    payload = {"artifact_id": "ef2084e797384a23", "status": "published"}
    b4_runner._save_audit(path, payload)
    expected_bytes = b4_runner._canonical(payload)
    assert path.read_bytes() == expected_bytes

    stable_mtime_ns = 1_600_000_000_000_000_000
    os.utime(path, ns=(stable_mtime_ns, stable_mtime_ns))
    before_bytes = path.read_bytes()
    before_mtime_ns = path.stat().st_mtime_ns
    b4_runner._save_audit(path, payload)

    assert path.read_bytes() == before_bytes == expected_bytes
    assert path.stat().st_mtime_ns == before_mtime_ns


def _fixture_data() -> FakeV3Data:
    dates = tuple(date(2024, 1, 1) + timedelta(days=i) for i in range(820))
    bars = {}
    for index, symbol in enumerate(("000001.SZ", "000002.SZ", "000003.SZ")):
        bars[symbol] = {
            day: DailyBar(
                date=day, symbol=symbol, open=100 + index + offset * (index + 1),
                high=101 + index + offset * (index + 1),
                low=99 + index + offset * (index + 1),
                close=100 + index + offset * (index + 1), volume=1_000_000,
                amount=100_000.0, adj_factor=1.0,
            )
            for offset, day in enumerate(dates)
        }
    return FakeV3Data(dates=dates, bars=bars, blocked_dates=set())


def test_v3_b4_runner_is_bound_to_the_exact_is_window_and_writes_verifiable_result(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_temp_b4_fixture(tmp_path, monkeypatch)
    result = _run_temp_b4(fixture, tmp_path, "audit.json")
    assert result["status"] == "published"
    assert result["is_range"] == {"start": "2025-06-27", "end": "2026-03-19"}
    assert result["canary"]["qualification_status"] == "pass"
    assert result["future_violations"] == 0
    assert verify_v3_b4_is_result(Path(result["path"]), repo_root=fixture[0])["status"] == "verified"


def test_v3_b4_runner_rejects_a_production_audit_path_in_focused_tests(
    tmp_path: Path, monkeypatch
) -> None:
    connection_targets = []

    def forbidden_connect(database, *args, **kwargs):
        connection_targets.append(str(database))
        raise AssertionError(f"audit guard opened SQLite: {database}")

    monkeypatch.setattr(sqlite3, "connect", forbidden_connect)
    with pytest.raises(ValueError, match="audit"):
        run_v3_b4_is_once(
            repo_root=ROOT,
            output_root=tmp_path / "b4-results",
            audit_path=ROOT / "docs/verification/task4_v3_b4_is_audit.json",
        )
    assert connection_targets == []


def test_read_bound_wrapper_delegates_exact_batch_endpoints_and_audits_dates() -> None:
    start = date(2025, 6, 26)
    end = date(2025, 6, 27)

    class BatchSource:
        def __init__(self) -> None:
            self.calls = []
            self.mapping = {"000001.SZ": ("start-bar", "end-bar")}

        def get_adjusted_momentum_endpoints(self, symbols, start_date, end_date):
            self.calls.append((tuple(symbols), start_date, end_date))
            return self.mapping

    source = BatchSource()
    wrapper = _ReadBoundDataSource(source, end, enable_batch_endpoints=True)

    assert wrapper.get_adjusted_momentum_endpoints(("000001.SZ",), start, end) == source.mapping
    assert source.calls == [(("000001.SZ",), start, end)]
    assert wrapper.audit()["operation_counts"] == {"bar": 2}
    assert wrapper.audit()["max_requested_date"] == end.isoformat()


def test_read_bound_wrapper_defaults_to_legacy_fallback_even_when_batch_exists() -> None:
    class BatchSource:
        def __init__(self) -> None:
            self.calls = 0

        def get_adjusted_momentum_endpoints(self, *args):
            self.calls += 1
            return {"000001.SZ": ("start-bar", "end-bar")}

    source = BatchSource()
    wrapper = _ReadBoundDataSource(source, date(2025, 6, 27))

    assert wrapper.get_adjusted_momentum_endpoints(
        ("000001.SZ",), date(2025, 6, 26), date(2025, 6, 27)
    ) is None
    assert source.calls == 0


def test_read_bound_wrapper_rejects_future_batch_start_and_end_separately() -> None:
    class NoCallSource:
        def get_adjusted_momentum_endpoints(self, *args):
            raise AssertionError("future batch request must be rejected by wrapper")

    wrapper = _ReadBoundDataSource(
        NoCallSource(), date(2026, 3, 19), enable_batch_endpoints=True
    )
    with pytest.raises(ValueError, match="OOS/future read"):
        wrapper.get_adjusted_momentum_endpoints(
            ("000001.SZ",), date(2026, 3, 20), date(2026, 3, 19)
        )
    with pytest.raises(ValueError, match="OOS/future read"):
        wrapper.get_adjusted_momentum_endpoints(
            ("000001.SZ",), date(2026, 3, 19), date(2026, 3, 20)
        )


def test_read_bound_wrapper_returns_none_for_no_batch_source() -> None:
    class NoBatchSource:
        pass

    wrapper = _ReadBoundDataSource(
        NoBatchSource(), date(2025, 6, 27), enable_batch_endpoints=True
    )
    assert wrapper.get_adjusted_momentum_endpoints(
        ("000001.SZ",), date(2025, 6, 26), date(2025, 6, 27)
    ) is None


def test_read_bound_batch_rank_matches_legacy_fallback_rank() -> None:
    data = _fixture_data()
    as_of = data.dates[-60]
    fallback = _ReadBoundDataSource(data, as_of)
    fallback_rank = _rank_snapshot(fallback, as_of)

    class BatchProxy:
        def __init__(self, source) -> None:
            self.source = source
            self.batch_calls = 0

        def symbols_as_of(self, day):
            return self.source.symbols_as_of(day)

        def common_trading_dates(self, start_date, end_date):
            return self.source.common_trading_dates(start_date, end_date)

        def get_adjusted_momentum_endpoints(self, symbols, start_date, end_date):
            self.batch_calls += 1
            return {
                symbol: (self.source.get_bar(symbol, start_date), self.source.get_bar(symbol, end_date))
                for symbol in symbols
            }

        def get_bar(self, symbol, day):
            raise AssertionError("batch rank path must not use per-symbol get_bar")

    batch = BatchProxy(data)
    batch_rank = _rank_snapshot(batch, as_of)

    assert batch_rank == fallback_rank
    assert batch.batch_calls == 1
