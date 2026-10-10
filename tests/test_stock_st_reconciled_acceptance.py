import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PYTHON = Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")
FIXED_ID = "stacc_traderlens_v2_shsz_stock_st_004"
CANDIDATE_REL = "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004"
FORMAL_REL = "data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_004"
REQUIRED_FILES = {
    "manifest.json", "manifest.json.sha256", "empty_outcomes.json", "empty_outcomes.json.sha256",
}
FIXTURE_REL = "formal_fixture_source_20260730/candidate"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestStockStReconciledAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_root = Path(__file__).parents[1]
        cls._repo_tmp = tempfile.TemporaryDirectory(prefix="reconciled_acceptance_repo_")
        cls.repo_root = Path(cls._repo_tmp.name)
        for relative in [
            "scripts/publish_stock_st_reconciled_acceptance.py",
            "scripts/verify_stock_st_reconciled_acceptance.py",
            "scripts/verify_stock_st_acceptance_policy.py",
            "scripts/reconcile_stock_st_empty_outcomes.py",
            "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256",
        ]:
            source = cls.source_root / relative
            target = cls.repo_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, copy_function=shutil.copy2)
            else:
                shutil.copy2(source, target)
        shutil.copytree(
            cls.source_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st",
            cls.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st",
            copy_function=shutil.copy2,
        )
        cls.source_hashes = {
            p.relative_to(cls.repo_root).as_posix(): file_hash(p)
            for p in (cls.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st").rglob("*")
            if p.is_file()
        }

    @classmethod
    def tearDownClass(cls):
        current = {
            p.relative_to(cls.repo_root).as_posix(): file_hash(p)
            for p in (cls.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st").rglob("*")
            if p.is_file()
        }
        assert current == cls.source_hashes
        cls._repo_tmp.cleanup()

    def setUp(self):
        shutil.rmtree(self.repo_root / CANDIDATE_REL, ignore_errors=True)
        shutil.rmtree(self.repo_root / FORMAL_REL, ignore_errors=True)

    def run_cli(self, *extra):
        return subprocess.run(
            [str(PYTHON), str(self.repo_root / "scripts/publish_stock_st_reconciled_acceptance.py"), "--repo-root", str(self.repo_root), *extra],
            capture_output=True, text=True, timeout=240,
        )

    def copy_fixture(self, destination_rel):
        source = self.source_root / FIXTURE_REL
        destination = self.repo_root / destination_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, copy_function=shutil.copy2)
        return destination

    def run_verifier(self, artifact_rel, formal_mode=False):
        command = [
            str(PYTHON), str(self.repo_root / "scripts/verify_stock_st_reconciled_acceptance.py"),
            "--repo-root", str(self.repo_root), "--artifact-root", artifact_rel,
        ]
        if formal_mode:
            command.append("--formal-mode")
        return subprocess.run(command, capture_output=True, text=True, timeout=240)

    def assert_rejected(self, result, reason):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(result.stdout.count("\n"), 1, result.stdout)
        self.assertIn(reason, result.stdout)

    def test_stage_only_builder_export_exists(self):
        publisher = ast.parse((self.source_root / "scripts/publish_stock_st_reconciled_acceptance.py").read_text(encoding="utf-8"))
        functions = {node.name for node in publisher.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("build_candidate", functions)

    def test_fresh_candidate_exact_four_files_and_verifier_output(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("ACCEPTED: " + FIXED_ID, result.stdout)
        candidate = self.repo_root / CANDIDATE_REL
        self.assertEqual({p.name for p in candidate.iterdir()}, REQUIRED_FILES)
        self.assertFalse((self.repo_root / FORMAL_REL).exists())

    def test_existing_candidate_and_formal_guards_reject_without_writes(self):
        candidate = self.repo_root / CANDIDATE_REL
        candidate.mkdir(parents=True)
        marker = candidate / "marker"
        marker.write_bytes(b"keep")
        result = self.run_cli()
        self.assert_rejected(result, "candidate exists")
        self.assertEqual(marker.read_bytes(), b"keep")
        shutil.rmtree(candidate)

        formal = self.repo_root / FORMAL_REL
        formal.mkdir(parents=True)
        formal_marker = formal / "marker"
        formal_marker.write_bytes(b"keep-formal")
        result = self.run_cli()
        self.assert_rejected(result, "formal guard")
        self.assertEqual(formal_marker.read_bytes(), b"keep-formal")

    def test_no_publication_or_reconciler_imports(self):
        tree = ast.parse((self.source_root / "scripts/publish_stock_st_reconciled_acceptance.py").read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        forbidden = ("reconcile_stock_st_empty_outcomes", "tushare", "requests", "urllib")
        self.assertFalse(any(name.startswith(forbidden) for name in imports), imports)

    def test_default_verifier_rejects_formal_path(self):
        self.copy_fixture(FORMAL_REL)
        result = self.run_verifier(FORMAL_REL)
        self.assert_rejected(result, "artifact path")

    def test_formal_mode_accepts_only_fixed_formal_path(self):
        self.copy_fixture(FORMAL_REL)
        result = self.run_verifier(FORMAL_REL, formal_mode=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.strip(), "ACCEPTED: " + FIXED_ID)

    def test_formal_mode_rejects_candidate_path(self):
        self.copy_fixture(CANDIDATE_REL)
        result = self.run_verifier(CANDIDATE_REL, formal_mode=True)
        self.assert_rejected(result, "artifact path")

    def test_formal_publish_success_moves_exact_bytes(self):
        candidate = self.copy_fixture(CANDIDATE_REL)
        before = {p.name: file_hash(p) for p in candidate.iterdir()}
        result = self.run_cli("--publish-formal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        formal = self.repo_root / FORMAL_REL
        self.assertFalse(candidate.exists())
        self.assertEqual({p.name: file_hash(p) for p in formal.iterdir()}, before)

    def test_formal_precheck_failure_does_not_rename(self):
        candidate = self.copy_fixture(CANDIDATE_REL)
        before = {p.name: file_hash(p) for p in candidate.iterdir()}
        formal = self.repo_root / FORMAL_REL
        formal.mkdir(parents=True)
        marker = formal / "marker"
        marker.write_bytes(b"keep-formal")
        result = self.run_cli("--publish-formal")
        self.assert_rejected(result, "formal exists")
        self.assertEqual({p.name: file_hash(p) for p in candidate.iterdir()}, before)
        self.assertEqual(marker.read_bytes(), b"keep-formal")

    def test_postcheck_failure_keeps_formal_and_removes_staging(self):
        candidate = self.copy_fixture(CANDIDATE_REL)
        before = {p.name: file_hash(p) for p in candidate.iterdir()}
        module_path = self.repo_root / "scripts/publish_stock_st_reconciled_acceptance.py"
        spec = importlib.util.spec_from_file_location("isolated_publisher", module_path)
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        calls = []

        def runner(repo_root, artifact_rel, formal_mode):
            calls.append((artifact_rel, formal_mode))
            if formal_mode:
                return subprocess.CompletedProcess([], 1, "REJECTED: formal verifier rejected\n", "")
            return subprocess.CompletedProcess([], 0, "ACCEPTED: " + FIXED_ID + "\n", "")

        with self.assertRaisesRegex(publisher.BuildError, "post-rename formal verifier rejected"):
            publisher.publish_formal(self.repo_root, verifier_runner=runner)
        formal = self.repo_root / FORMAL_REL
        self.assertEqual(calls, [(CANDIDATE_REL, False), (FORMAL_REL, True)])
        self.assertFalse(candidate.exists())
        self.assertTrue(formal.exists())
        self.assertEqual({p.name: file_hash(p) for p in formal.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
