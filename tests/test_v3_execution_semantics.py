import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

import scripts.publish_v3_execution_semantics as publisher_module
from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics
from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics
from strategy_core.backtest_engine import run_event_backtest
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec
from tests.test_v3_relative_strength_executor import _data


ROOT = Path(__file__).resolve().parents[1]
CURRENT_EXECUTOR_SHA256 = "13c4e0839d20a0891b62344189de8627817647a8d56bd09a7013fea7eea86192"


def test_publish_v3_direct_script_bootstraps_package_import(tmp_path: Path) -> None:
    script = ROOT / "scripts/publish_v3_execution_semantics.py"
    smoke_code = f"""
from pathlib import Path
import runpy
import sys

script = Path(r"{script}")
project_root = script.parents[1].resolve()
sys.path[:] = [str(script.parent)] + [
    entry for entry in sys.path
    if Path(entry or '.').resolve() != project_root
]
runpy.run_path(str(script), run_name="__publish_import_smoke__")
"""
    environment = {**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-c", smoke_code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _copy_fixture_repo(root: Path, *, db_source: Path | None = None) -> Path:
    root = Path(root)
    (root / "data").mkdir(parents=True)
    shutil.copy2(db_source or ROOT / "data/strategy.db", root / "data/strategy.db")
    directories = (
        "data/pit/historical_scope_freezes/acbc49159d989a46",
        "data/pit/v3_historical_coverage_packages/1e79d26460c0c109",
        "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a",
        "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4",
        "data/pit/b3_execution_input_packages/05f38a2884dc7e47",
        "data/pit/qualification_successors/49b09326f35936c6",
        "data/pit/liquidity_qualification_successors/7c05ece4d3f01086",
        "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005",
        "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1",
        "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003",
        "data/pit/prototype_gate_v2_criteria",
        "data/pit/market_regime_owner_approvals/6170c11c8068f407",
        "data/pit/v3_execution_semantics_supplements/680cd55c91254667",
        "data/pit/v3_execution_semantics_supplements/708dbfa1c5601113",
        "data/pit/v3_execution_semantics_supplements/dc6ba0ca0df66624",
        "data/pit/v3_execution_semantics_supplements/1aed70f1af38a191",
    )
    for relative in directories:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / relative, target)
    b3_trust_files = (
        "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
        "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
        "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet",
        "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256",
    )
    for relative in b3_trust_files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    source_files = (
        "backend/services/prototype_gate_criteria_surface.py",
        "backend/services/formal_pit_partition_adapter.py",
        "strategy_core/v3_relative_strength_executor.py",
        "strategy_core/backtest_engine.py",
        "strategy_core/fill_simulator.py",
        "strategy_core/orders.py",
        "strategy_core/transaction_costs.py",
        "strategy_core/portfolio.py",
    )
    for relative in source_files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return root


def _publish(tmp_path: Path) -> tuple[Path, dict]:
    repo_root = _copy_fixture_repo(tmp_path / "repo")
    result = publish_v3_execution_semantics(
        output_root=tmp_path / "supplements",
        repo_root=repo_root,
    )
    return Path(result["path"]), result


def test_protocol_binding_closes_real_file_backed_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = _copy_fixture_repo(tmp_path / "repo")
    real_connect = publisher_module.sqlite3.connect
    closed: list[bool] = []
    connections = []

    class TrackedConnection:
        def __init__(self, inner):
            self._inner = inner
            self._closed = False

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

        def close(self):
            if not self._closed:
                self._closed = True
                closed.append(True)
            return self._inner.close()

        def __getattr__(self, name):
            return getattr(self._inner, name)

    def tracked_connect(*args, **kwargs):
        connection = TrackedConnection(real_connect(*args, **kwargs))
        connections.append(connection)
        return connection

    monkeypatch.setattr(publisher_module.sqlite3, "connect", tracked_connect)
    try:
        publisher_module._protocol_binding(repo_root)
        assert closed == [True]
    finally:
        for connection in connections:
            connection.close()


def test_v3_execution_semantics_successor_binds_1aed_predecessor_and_current_sources(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    manifest = json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["predecessor"] == {
        "supplement_id": "1aed70f1af38a191",
        "manifest_sha256": "70e4dfa09f11cbafd5aebf76903ecb95ca6a491635d1d94b3d713db5481beac0",
    }
    assert manifest["source_bindings"]["v3_executor"]["sha256"] == _sha(
        ROOT / "strategy_core/v3_relative_strength_executor.py"
    )
    for binding in manifest["source_bindings"].values():
        assert binding["sha256"] == _sha(ROOT / binding["path"])


def test_v3_execution_semantics_publishes_and_verifies_exact_approval(tmp_path: Path) -> None:
    supplement_dir, result = _publish(tmp_path)
    verified = verify_v3_execution_semantics(supplement_dir)
    assert result["status"] == "published"
    assert verified["status"] == "verified"
    manifest = json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "supplement_id"}
    expected_id = hashlib.sha256(_canonical(payload)).hexdigest()[:16]
    assert result["supplement_id"] == expected_id
    assert verified["supplement_id"] == expected_id
    assert verified["manifest_sha256"] == _sha(supplement_dir / "manifest.json")
    assert manifest["market_regime"]["owner_approval_id"] == "6170c11c8068f407"
    assert manifest["market_regime"]["owner_approval_manifest_sha256"] == "75aeb703f09a6876e329466b435e78574c24922ea56a9ba987b0ab7d17165b50"
    assert manifest["strategy"]["strategy_revision_id"] == "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
    assert manifest["schema_version"] == "v3_execution_semantics_supplement.v2"
    assert manifest["predecessor"] == {
        "supplement_id": "1aed70f1af38a191",
        "manifest_sha256": "70e4dfa09f11cbafd5aebf76903ecb95ca6a491635d1d94b3d713db5481beac0",
    }
    assert manifest["protocol"] == {
        "protocol_snapshot_id": "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        "protocol_profile": "b6_coverage_bound",
        "strategy_revision_id": "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
        "payload_sha256": "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3",
        "database_path": "data/strategy.db",
    }
    assert manifest["source_bindings"]["v3_executor"]["sha256"] == CURRENT_EXECUTOR_SHA256
    assert manifest["criteria"] == {
        "gate_snapshot_id": "prototype_gate_v2_gate_v2_2bd8670c2e0fe084",
        "gate_manifest_sha256": "9a534c58da7634defc1b30dd7ff1bfb91302365f08bb0ef413fa64253997d113",
        "gate_content_hash": "ab9c2320d54d17420e045a981085b44fd0c05fcdc572380debc64ba72bc3d21c",
        "kill_snapshot_id": "prototype_gate_v2_kill_v2_ea47b0c73ed2476e",
        "kill_manifest_sha256": "604a435ca7a3295f134e870dc8cc3b05239f58831176dec4c9fce60b984d914e",
        "kill_content_hash": "7339c8849ecf5cd813995b1eeb18060102bc5fde1608481fb81d93818abb34f7",
        "envelope_hash": "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738",
    }
    assert manifest["common_calendar"]["artifact_id"] == "shsz_common_trade_calendar_v1"
    assert manifest["common_calendar"]["manifest_sha256"] == "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
    assert manifest["common_calendar"]["date_set_sha256"] == "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
    assert _sha(supplement_dir / "manifest.json") == (supplement_dir / "manifest.json.sha256").read_text(encoding="utf-8").split()[0]


def test_v3_execution_semantics_exact_retry_reuses_same_temp_supplement(tmp_path: Path) -> None:
    repo_root = _copy_fixture_repo(tmp_path / "repo")
    output_root = tmp_path / "supplements"

    from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics

    first = publish_v3_execution_semantics(output_root=output_root, repo_root=repo_root)
    second = publish_v3_execution_semantics(output_root=output_root, repo_root=repo_root)

    assert first["status"] == "published"
    assert second["status"] == "already_published"
    assert first["supplement_id"] == second["supplement_id"]
    assert len(list(output_root.iterdir())) == 1


def test_v3_execution_semantics_rejects_mixed_old_new_lineage(tmp_path: Path) -> None:
    supplement_dir, result = _publish(tmp_path)
    old_manifest = json.loads(
        (ROOT / "data/pit/v3_execution_semantics_supplements/680cd55c91254667/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    old_manifest["supplement_id"] = result["supplement_id"]
    raw = _canonical(old_manifest)
    (supplement_dir / "manifest.json").write_bytes(raw)
    (supplement_dir / "manifest.json.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n",
        encoding="utf-8",
    )

    assert verify_v3_execution_semantics(supplement_dir)["status"] == "invalid"


def test_v3_execution_semantics_missing_new_protocol_fails_before_temp_publish(tmp_path: Path) -> None:
    repo_root = _copy_fixture_repo(
        tmp_path / "repo",
        db_source=ROOT / "data/strategy_backups/b6_preclaim/"
        "d67fff62dff63793354ebb148e1b1826474f7c9c78fe182463a75f586a2d0600."
        "ba475e75a1a9627ccf46bfe8a07c9bd112e58a9e3de742a5fa62f1cfc4af8d6a.sqlite3",
    )

    from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics

    with pytest.raises(ValueError, match="approved v3 protocol binding missing"):
        publish_v3_execution_semantics(output_root=tmp_path / "supplements", repo_root=repo_root)
    assert not (tmp_path / "supplements").exists()


def test_v3_execution_semantics_verifier_rejects_missing_new_protocol_row(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path / "published")
    repo_root = _copy_fixture_repo(
        tmp_path / "repo",
        db_source=ROOT / "data/strategy_backups/b6_preclaim/"
        "d67fff62dff63793354ebb148e1b1826474f7c9c78fe182463a75f586a2d0600."
        "ba475e75a1a9627ccf46bfe8a07c9bd112e58a9e3de742a5fa62f1cfc4af8d6a.sqlite3",
    )

    result = verify_v3_execution_semantics(supplement_dir, repo_root=repo_root)

    assert result["status"] == "invalid"


def test_v3_execution_semantics_verifier_rejects_stable_criteria_source_drift(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path / "published")
    repo_root = _copy_fixture_repo(tmp_path / "repo")
    stable_source = repo_root / "backend/services/prototype_gate_criteria_surface.py"
    stable_source.write_bytes(stable_source.read_bytes() + b"\n# drift\n")

    result = verify_v3_execution_semantics(supplement_dir, repo_root=repo_root)

    assert result["status"] == "invalid"


def test_v3_execution_semantics_verifier_rejects_stable_source_root_drift(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path / "published")
    manifest = json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))
    source_root = tmp_path / "source-root"
    for binding in manifest["source_bindings"].values():
        source_path = source_root / binding["path"]
        source_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / binding["path"], source_path)
    stable_source = source_root / "backend/services/prototype_gate_criteria_surface.py"
    stable_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "backend/services/prototype_gate_criteria_surface.py", stable_source)
    stable_source.write_bytes(stable_source.read_bytes() + b"\n# source-root drift\n")

    result = verify_v3_execution_semantics(supplement_dir, source_root=source_root)

    assert result["status"] == "invalid"


def test_v3_execution_semantics_binds_v2_criteria_and_protocol(tmp_path: Path) -> None:
    from scripts.publish_v3_execution_semantics import build_payload

    payload = build_payload(_copy_fixture_repo(tmp_path / "repo"))

    assert payload["protocol"]["protocol_snapshot_id"] == (
        "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
    )
    assert payload["protocol"]["payload_sha256"] == (
        "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3"
    )
    assert payload["criteria"] == {
        "gate_snapshot_id": "prototype_gate_v2_gate_v2_2bd8670c2e0fe084",
        "gate_manifest_sha256": "9a534c58da7634defc1b30dd7ff1bfb91302365f08bb0ef413fa64253997d113",
        "gate_content_hash": payload["criteria"]["gate_content_hash"],
        "kill_snapshot_id": "prototype_gate_v2_kill_v2_ea47b0c73ed2476e",
        "kill_manifest_sha256": "604a435ca7a3295f134e870dc8cc3b05239f58831176dec4c9fce60b984d914e",
        "kill_content_hash": payload["criteria"]["kill_content_hash"],
        "envelope_hash": "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738",
    }


def test_v3_execution_semantics_rejects_manifest_tamper(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    manifest_path = supplement_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantics"]["portfolio"]["max_positions"] = 6
    manifest_path.write_bytes(_canonical(manifest))
    assert verify_v3_execution_semantics(supplement_dir)["status"] == "invalid"


def test_v3_execution_semantics_rejects_source_tamper(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    manifest = json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))
    source_root = tmp_path / "source-root"
    for binding in manifest["source_bindings"].values():
        source_path = source_root / binding["path"]
        source_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / binding["path"], source_path)
    executor_path = source_root / "strategy_core/v3_relative_strength_executor.py"
    executor_path.write_bytes(executor_path.read_bytes() + b"\n# tampered\n")
    assert verify_v3_execution_semantics(supplement_dir, source_root=source_root)["status"] == "invalid"


def test_v3_execution_semantics_write_once_conflict_is_loud(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    manifest_path = supplement_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantics"]["portfolio"]["max_positions"] = 6
    manifest_path.write_bytes(_canonical(manifest))
    with pytest.raises(ValueError, match="write-once"):
        publish_v3_execution_semantics(output_root=tmp_path / "supplements")


def test_v3_runtime_rejects_immutable_predecessor(tmp_path: Path) -> None:
    predecessor = tmp_path / "708dbfa1c5601113"
    shutil.copytree(
        ROOT / "data/pit/v3_execution_semantics_supplements/708dbfa1c5601113",
        predecessor,
    )

    result = verify_v3_execution_semantics(predecessor)
    assert result["status"] == "superseded"
    assert result["supplement_id"] == "708dbfa1c5601113"


def test_v3_runtime_rejects_current_dc6_predecessor(tmp_path: Path) -> None:
    predecessor = tmp_path / "dc6ba0ca0df66624"
    shutil.copytree(
        ROOT / "data/pit/v3_execution_semantics_supplements/dc6ba0ca0df66624",
        predecessor,
    )

    result = verify_v3_execution_semantics(predecessor)
    assert result["status"] == "superseded"
    assert result["supplement_id"] == "dc6ba0ca0df66624"


def test_v3_runtime_rejects_older_immutable_predecessor(tmp_path: Path) -> None:
    predecessor = tmp_path / "680cd55c91254667"
    shutil.copytree(
        ROOT / "data/pit/v3_execution_semantics_supplements/680cd55c91254667",
        predecessor,
    )

    result = verify_v3_execution_semantics(predecessor)
    assert result["status"] == "superseded"
    assert result["supplement_id"] == "680cd55c91254667"


def test_v3_runtime_rejects_tampered_immutable_predecessors(tmp_path: Path) -> None:
    for supplement_id in ("dc6ba0ca0df66624", "708dbfa1c5601113", "680cd55c91254667"):
        predecessor = tmp_path / supplement_id
        shutil.copytree(
            ROOT / "data/pit/v3_execution_semantics_supplements" / supplement_id,
            predecessor,
        )
        manifest_path = predecessor / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "tampered"
        manifest_path.write_bytes(_canonical(manifest))

        result = verify_v3_execution_semantics(predecessor)
        assert result["status"] == "invalid"


def test_v3_dispatch_requires_runtime_verified_supplement(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    data = _data()
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id="6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
        protocol_snapshot_id="8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        data_snapshot_hash="d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e",
        supplement_id=json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))["supplement_id"],
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )
    result = run_event_backtest(
        spec, data, None, spec.protocol_snapshot_id, spec.data_snapshot_hash,
        supplement_path=supplement_dir,
    )
    assert result.strategy_revision_id == spec.strategy_revision_id
    assert result.protocol_snapshot_id == spec.protocol_snapshot_id


def test_v3_dispatch_forwards_optional_observation_sink(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    data = _data()
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id="6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
        protocol_snapshot_id="8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        data_snapshot_hash="d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e",
        supplement_id=json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))["supplement_id"],
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )
    snapshots = []
    result = run_event_backtest(
        spec, data, None, spec.protocol_snapshot_id, spec.data_snapshot_hash,
        supplement_path=supplement_dir, observation_sink=snapshots.append,
    )
    assert result.future_violations == ()
    assert len(snapshots) == len(data.dates[-10:-1])


def test_v3_dispatch_rejects_runtime_tampered_supplement(tmp_path: Path) -> None:
    supplement_dir, _ = _publish(tmp_path)
    manifest_path = supplement_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantics"]["orders"]["blocked_entry"] = "carry_forward"
    manifest_path.write_bytes(_canonical(manifest))
    data = _data()
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id="6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
        protocol_snapshot_id="8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        data_snapshot_hash="d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e",
        supplement_id=json.loads((manifest_path).read_text(encoding="utf-8"))["supplement_id"],
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )
    with pytest.raises(ValueError, match="supplement invalid"):
        run_event_backtest(spec, data, None, spec.protocol_snapshot_id, spec.data_snapshot_hash, supplement_path=supplement_dir)


def test_v3_dispatch_accepts_frozen_verified_supplement_without_path_or_verifier_and_keeps_legacy_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supplement_dir, _ = _publish(tmp_path)
    verified = verify_v3_execution_semantics(supplement_dir)
    frozen = {
        key: verified[key]
        for key in (
            "status",
            "supplement_id",
            "manifest_sha256",
            "strategy_revision_id",
            "protocol_snapshot_id",
            "data_snapshot_hash",
        )
    }
    assert "path" not in frozen
    data = _data()
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=verified["strategy_revision_id"],
        protocol_snapshot_id=verified["protocol_snapshot_id"],
        data_snapshot_hash=verified["data_snapshot_hash"],
        supplement_id=verified["supplement_id"],
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )

    def verifier_must_not_run(*_args, **_kwargs):
        raise AssertionError("frozen supplement must not call the path verifier")

    monkeypatch.setattr(
        "scripts.verify_v3_execution_semantics.verify_v3_execution_semantics",
        verifier_must_not_run,
    )
    frozen_result = run_event_backtest(
        spec,
        data,
        None,
        spec.protocol_snapshot_id,
        spec.data_snapshot_hash,
        verified_supplement=frozen,
    )
    assert frozen_result.strategy_revision_id == spec.strategy_revision_id

    calls = []

    def recording_verifier(path):
        calls.append(Path(path))
        return verified

    monkeypatch.setattr(
        "scripts.verify_v3_execution_semantics.verify_v3_execution_semantics",
        recording_verifier,
    )
    legacy_result = run_event_backtest(
        spec,
        data,
        None,
        spec.protocol_snapshot_id,
        spec.data_snapshot_hash,
        supplement_path=supplement_dir,
    )
    assert legacy_result.strategy_revision_id == spec.strategy_revision_id
    assert calls == [supplement_dir]

    with pytest.raises(ValueError, match="exactly one"):
        run_event_backtest(
            spec,
            data,
            None,
            spec.protocol_snapshot_id,
            spec.data_snapshot_hash,
        )
    with pytest.raises(ValueError, match="exactly one"):
        run_event_backtest(
            spec,
            data,
            None,
            spec.protocol_snapshot_id,
            spec.data_snapshot_hash,
            supplement_path=supplement_dir,
            verified_supplement=frozen,
        )
