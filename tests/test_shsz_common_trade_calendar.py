from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "scripts"))
import stage_shsz_common_trade_calendar as stage
import verify_shsz_common_trade_calendar as verifier

CANDIDATE_REL = "data/pit/.staging/shsz_common_trade_calendar_v1"
FORMAL_REL = "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
FIXTURE_CANDIDATE = SOURCE_ROOT / "tests/fixtures/shsz_common_trade_calendar_v1"
REAL_ROOT = Path(r"D:\Codex\TraderLens")
TRUST_FILES = (
    "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003/policy.json",
    "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003/policy.json.sha256",
    "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
    "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
    "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet",
    "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256",
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _inventory(root: Path, relative: str) -> dict | None:
    path = root / Path(*relative.split("/"))
    if not path.exists():
        return None
    files = []
    for item in sorted(path.rglob("*")):
        if item.is_file():
            raw = item.read_bytes()
            files.append({"path": item.relative_to(path).as_posix(), "bytes": len(raw), "sha256": _sha(raw)})
    return {"exists": True, "files": files}


@pytest.fixture(scope="session")
def temp_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("shsz_calendar_repo")
    for relative in ("scripts/stage_shsz_common_trade_calendar.py", "scripts/verify_shsz_common_trade_calendar.py"):
        source = SOURCE_ROOT / Path(*relative.split("/"))
        target = root / Path(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in TRUST_FILES:
        source = SOURCE_ROOT / Path(*relative.split("/"))
        target = root / Path(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


@pytest.fixture(scope="session", autouse=True)
def preserve_real_artifacts():
    before = {
        "candidate": _inventory(REAL_ROOT, CANDIDATE_REL),
        "formal": _inventory(REAL_ROOT, FORMAL_REL),
    }
    yield
    after = {
        "candidate": _inventory(REAL_ROOT, CANDIDATE_REL),
        "formal": _inventory(REAL_ROOT, FORMAL_REL),
    }
    assert after == before


@pytest.fixture(autouse=True)
def clean_temp_artifacts(temp_repo: Path):
    for relative in (CANDIDATE_REL, FORMAL_REL):
        path = temp_repo / Path(*relative.split("/"))
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    yield
    for relative in (CANDIDATE_REL, FORMAL_REL):
        path = temp_repo / Path(*relative.split("/"))
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()


def _candidate(repo_root: Path) -> Path:
    return repo_root / Path(*CANDIDATE_REL.split("/"))


def _formal(repo_root: Path) -> Path:
    return repo_root / Path(*FORMAL_REL.split("/"))


def _rows(repo_root: Path) -> list[dict]:
    table = pq.read_table(repo_root / Path(*TRUST_FILES[4].split("/"))).to_pylist()
    sse_open = {r["cal_date"] for r in table if r["exchange"] == "SSE" and r["is_open"] == 1}
    rows = []
    current = date(2016, 1, 1)
    end = date(2026, 7, 10)
    while current <= end:
        d = current.strftime("%Y%m%d")
        rows.append({"exchange": "SZSE", "cal_date": d, "is_open": int(d in sse_open), "pretrade_date": (current - timedelta(days=1)).strftime("%Y%m%d")})
        current += timedelta(days=1)
    return rows


@pytest.fixture
def test_facts(monkeypatch, temp_repo: Path):
    rows = _rows(temp_repo)
    row_hash = _sha(_canonical(rows).encode("utf-8"))
    monkeypatch.setattr(stage, "EXPECTED_SZSE_ROWS_SHA256", row_hash)
    monkeypatch.setattr(verifier, "EXPECTED_SZSE_ROWS_SHA256", row_hash)
    return rows


def _write_candidate(repo_root: Path, rows: list[dict]) -> None:
    candidate = _candidate(repo_root)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.mkdir()
    for name, raw in stage._build_artifact_bytes(repo_root, rows).items():
        (candidate / name).write_bytes(raw)


def _restore_baseline_candidate(repo_root: Path) -> None:
    shutil.copytree(FIXTURE_CANDIDATE, _candidate(repo_root))


def _run_verifier_cli(repo_root: Path, artifact_root: str, formal_mode: bool = False):
    command = [str(Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")), str(repo_root / "scripts/verify_shsz_common_trade_calendar.py"), "--repo-root", str(repo_root), "--artifact-root", artifact_root]
    if formal_mode:
        command.append("--formal-mode")
    return subprocess.run(command, capture_output=True, text=True)


def _run_publish_cli(repo_root: Path):
    python = r"D:\Codex\TraderLens\.venv\Scripts\python.exe"
    return subprocess.run([python, str(repo_root / "scripts/stage_shsz_common_trade_calendar.py"), "--repo-root", str(repo_root), "--publish-formal"], capture_output=True, text=True)


def test_valid_candidate_is_accepted_by_standalone_verifier(test_facts, temp_repo: Path):
    _write_candidate(temp_repo, test_facts)
    result = verifier.verify_candidate(temp_repo, CANDIDATE_REL)
    assert result["artifact_id"] == "shsz_common_trade_calendar_v1"
    assert sorted(p.name for p in _candidate(temp_repo).iterdir()) == ["manifest.json", "manifest.json.sha256", "szse_trade_cal.parquet", "szse_trade_cal.parquet.sha256"]


@pytest.mark.parametrize("mutation,reason", [
    (lambda rows: rows.__setitem__(10, {**rows[10], "exchange": "SSE"}), "exchange"),
    (lambda rows: rows.__setitem__(10, {**rows[10], "cal_date": rows[9]["cal_date"]}), "duplicate"),
    (lambda rows: rows.__setitem__(10, {**rows[10], "is_open": 1 - rows[10]["is_open"]}), "canonical rows"),
])
def test_response_mutations_are_rejected(test_facts, temp_repo: Path, mutation, reason):
    rows = [dict(row) for row in test_facts]
    mutation(rows)
    _write_candidate(temp_repo, rows)
    with pytest.raises(verifier.VerificationError, match=reason):
        verifier.verify_candidate(temp_repo, CANDIDATE_REL)


def test_existing_candidate_or_formal_rejects_before_network(monkeypatch, temp_repo: Path):
    calls = []
    monkeypatch.setattr(stage, "_fetch_szse_rows", lambda _root: calls.append(True))
    candidate = _candidate(temp_repo)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.mkdir()
    with pytest.raises(stage.StageError, match="candidate exists"):
        stage.build_candidate(temp_repo)
    shutil.rmtree(candidate)
    formal = _formal(temp_repo)
    formal.parent.mkdir(parents=True, exist_ok=True)
    formal.mkdir()
    with pytest.raises(stage.StageError, match="formal guard exists"):
        stage.build_candidate(temp_repo)
    assert calls == []


def test_real_reparse_guard_rejects_before_network(monkeypatch, temp_repo: Path, tmp_path: Path):
    monkeypatch.setattr(stage, "_fetch_szse_rows", lambda _root: pytest.fail("network called"))
    staging = temp_repo / "data/pit/.staging"
    target = tmp_path / "target"
    target.mkdir()
    if staging.exists() or staging.is_symlink():
        shutil.rmtree(staging)
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(staging), str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"real junction unavailable: {result.stdout}{result.stderr}")
    try:
        with pytest.raises(stage.StageError, match="reparse"):
            stage.build_candidate(temp_repo)
    finally:
        subprocess.run(["cmd", "/c", "rmdir", str(staging)], check=False)


def test_scripts_have_no_publication_or_downstream_imports():
    forbidden = ("publish", "reconcile", "b6", "gate", "promotion", "signal")
    for path in (SOURCE_ROOT / "scripts/stage_shsz_common_trade_calendar.py", SOURCE_ROOT / "scripts/verify_shsz_common_trade_calendar.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom): names = [node.module or ""]
            else: continue
            assert not any(any(token in name.lower() for token in forbidden) for name in names), path


def test_formal_mode_accepts_only_fixed_formal_path(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    shutil.copytree(_candidate(temp_repo), _formal(temp_repo))
    result = _run_verifier_cli(temp_repo, FORMAL_REL, formal_mode=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "ACCEPTED: shsz_common_trade_calendar_v1"
    assert result.stderr == ""


def test_default_verifier_rejects_formal_path(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    shutil.copytree(_candidate(temp_repo), _formal(temp_repo))
    result = _run_verifier_cli(temp_repo, FORMAL_REL)
    assert result.returncode != 0
    assert "REJECTED:" in result.stdout


def test_publish_formal_atomically_preserves_four_file_bytes(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    candidate = _candidate(temp_repo)
    baseline = {p.name: p.read_bytes() for p in candidate.iterdir()}
    result = _run_publish_cli(temp_repo)
    assert result.returncode == 0
    assert result.stdout.strip().splitlines() == ["PUBLISHED: data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1", "ACCEPTED: shsz_common_trade_calendar_v1"]
    assert result.stderr == ""
    assert not candidate.exists()
    assert {p.name: p.read_bytes() for p in _formal(temp_repo).iterdir()} == baseline


def test_existing_formal_rejects_without_rename(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    candidate = _candidate(temp_repo)
    formal = _formal(temp_repo)
    shutil.copytree(candidate, formal)
    candidate_before = {p.name: p.read_bytes() for p in candidate.iterdir()}
    formal_before = {p.name: p.read_bytes() for p in formal.iterdir()}
    result = _run_publish_cli(temp_repo)
    assert result.returncode != 0
    assert "formal exists" in result.stdout
    assert {p.name: p.read_bytes() for p in candidate.iterdir()} == candidate_before
    assert {p.name: p.read_bytes() for p in formal.iterdir()} == formal_before


def test_precheck_failure_does_not_rename(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    rejected = subprocess.CompletedProcess([], 1, "REJECTED: candidate verifier rejected", "")
    with pytest.raises(stage.StageError, match="candidate verifier rejected"):
        stage.publish_formal(temp_repo, verifier_runner=lambda *_args: rejected)
    assert _candidate(temp_repo).exists()
    assert not _formal(temp_repo).exists()


def test_postcheck_failure_keeps_formal_and_staging_absent(temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    accepted = subprocess.CompletedProcess([], 0, "ACCEPTED: shsz_common_trade_calendar_v1", "")
    rejected = subprocess.CompletedProcess([], 1, "REJECTED: formal verifier rejected", "")
    calls = []

    def runner(*args):
        calls.append(args)
        return accepted if len(calls) == 1 else rejected

    with pytest.raises(stage.StageError, match="post-publication formal verifier rejected"):
        stage.publish_formal(temp_repo, verifier_runner=runner)
    assert len(calls) == 2
    assert _formal(temp_repo).exists()
    assert not _candidate(temp_repo).exists()


def test_publication_branch_cannot_reach_fetch(monkeypatch, temp_repo: Path):
    _restore_baseline_candidate(temp_repo)
    monkeypatch.setattr(stage, "_fetch_szse_rows", lambda *_args: pytest.fail("network fetch reached publication branch"))
    accepted = subprocess.CompletedProcess([], 0, "ACCEPTED: shsz_common_trade_calendar_v1", "")
    stage.publish_formal(temp_repo, verifier_runner=lambda *_args: accepted)
    assert _formal(temp_repo).exists()
    assert not _candidate(temp_repo).exists()
