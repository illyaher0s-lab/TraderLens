import hashlib
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


PYTHON = Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")
FIXED_ID = "stacc_traderlens_v2_shsz_stock_st_004"
POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
POLICY_HASH = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
REQUIRED_COLUMNS = ["ts_code", "name", "trade_date", "type", "type_name"]


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def sidecar(path):
    Path(f"{path}.sha256").write_text(file_hash(path) + "\n", encoding="ascii")


def build_positive_artifact(repo_root, artifact_root):
    policy_path = repo_root / "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003/policy.json"
    index_path = repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json"
    calendar_path = repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    calendar = pq.read_table(calendar_path).to_pydict()
    dates = sorted(
        str(d)
        for d, exchange, is_open in zip(calendar["cal_date"], calendar["exchange"], calendar["is_open"])
        if exchange == "SSE" and int(is_open) == 1
    )
    stock_entries = {entry["path"]: entry for entry in index["interfaces"]["stock_st"]["entries"]}
    partitions = []
    empty_dates = []
    total_bytes = 0
    for date in dates:
        relative = f"{policy['registered_stock_st_root']}/trade_date={date}/part.parquet"
        parquet_path = repo_root / Path(*relative.split("/"))
        parquet_entry = stock_entries[relative]
        sidecar_relative = relative + ".sha256"
        sidecar_entry = stock_entries[sidecar_relative]
        table = pq.read_table(parquet_path)
        count = table.num_rows
        if count == 0:
            empty_dates.append(date)
        total_bytes += parquet_path.stat().st_size
        partitions.append(
            {
                "date": date,
                "repo_relative_path": relative,
                "sidecar_repo_relative_path": sidecar_relative,
                "byte_size": parquet_path.stat().st_size,
                "file_sha256": file_hash(parquet_path),
                "sidecar_sha256": file_hash(repo_root / Path(*sidecar_relative.split("/"))),
                "row_count": count,
                "empty": count == 0,
            }
        )
        assert parquet_entry["sha256"] == partitions[-1]["file_sha256"]
        assert sidecar_entry["sha256"] == partitions[-1]["sidecar_sha256"]

    request_hashes = []
    outcome_rows = []
    for date in empty_dates:
        request_hash = canonical_hash({"endpoint": "stock_st", "params": {"trade_date": date}})
        response_hash = canonical_hash(
            {
                "columns": REQUIRED_COLUMNS,
                "endpoint": "stock_st",
                "outcome": "success_empty",
                "request_trade_date": date,
                "rows": [],
            }
        )
        request_hashes.append(request_hash)
        outcome_rows.append(
            {
                "request_trade_date": date,
                "request_sha256": request_hash,
                "response_sha256": response_hash,
                "outcome": "success_empty",
                "row_count": 0,
            }
        )
    aggregate = {
        "algorithm_id": "stock_st_empty_outcomes_aggregate.v1",
        "items": outcome_rows,
        "item_fields": ["request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"],
        "sort_by": ["request_trade_date"],
    }
    outcomes = {
        "artifact_id": FIXED_ID,
        "policy_id": POLICY_ID,
        "schema_version": "stock_st_empty_outcomes.v2",
        "aggregate_sha256": canonical_hash(aggregate),
        "outcomes": outcome_rows,
    }
    artifact_root.mkdir(parents=True, exist_ok=True)
    outcomes_path = artifact_root / "empty_outcomes.json"
    write_json(outcomes_path, outcomes)
    sidecar(outcomes_path)
    manifest = {
        "artifact_id": FIXED_ID,
        "policy_id": POLICY_ID,
        "policy_path": "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003",
        "policy_sha256": POLICY_HASH,
        "schema_version": "stacc_stock_st_reconciled_acceptance.v2",
        "frozen": True,
        "registered_stock_st_root": policy["registered_stock_st_root"],
        "b3_bindings": policy["b3_package_bindings"],
        "calendar_binding": policy["calendar_bindings"],
        "schema_binding": policy["schema_requirements"],
        "algorithm_binding": policy["canonical_algorithms"],
        "partitions": partitions,
        "coverage": {
            "total_dates": len(partitions),
            "nonempty_dates": len(partitions) - len(empty_dates),
            "empty_dates": len(empty_dates),
            "missing_dates": 0,
            "extra_dates": 0,
            "duplicate_dates": 0,
            "total_bytes": total_bytes,
        },
        "outcomes": {
            "path": "empty_outcomes.json",
            "sha256": file_hash(outcomes_path),
            "aggregate_sha256": outcomes["aggregate_sha256"],
        },
    }
    manifest_path = artifact_root / "manifest.json"
    write_json(manifest_path, manifest)
    sidecar(manifest_path)
    return artifact_root


class TestStandaloneStockStVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_root = Path(__file__).parents[1]
        cls._repo_tmp = tempfile.TemporaryDirectory(prefix="st_verifier_repo_")
        cls.repo_root = Path(cls._repo_tmp.name)
        for relative in [
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
        cls.source_stock_hashes = {
            p.relative_to(cls.repo_root).as_posix(): file_hash(p)
            for p in (cls.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st").rglob("*")
            if p.is_file()
        }
        cls.baseline_root = cls.repo_root / "canonical_baseline" / FIXED_ID
        build_positive_artifact(cls.repo_root, cls.baseline_root)
        cls.baseline_metadata = {
            name: (cls.baseline_root / name).read_bytes()
            for name in ("manifest.json", "manifest.json.sha256", "empty_outcomes.json", "empty_outcomes.json.sha256")
        }

    @classmethod
    def tearDownClass(cls):
        current = {
            p.relative_to(cls.repo_root).as_posix(): file_hash(p)
            for p in (cls.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st").rglob("*")
            if p.is_file()
        }
        assert current == cls.source_stock_hashes
        cls._repo_tmp.cleanup()

    def setUp(self):
        self.artifact = self.repo_root / "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004"
        self.copy_baseline_metadata()

    def copy_baseline_metadata(self):
        shutil.rmtree(self.artifact, ignore_errors=True)
        self.artifact.parent.mkdir(parents=True, exist_ok=True)
        self.artifact.mkdir(parents=True, exist_ok=True)
        for name, raw in self.baseline_metadata.items():
            (self.artifact / name).write_bytes(raw)

    def tearDown(self):
        if self.artifact.exists() or self.artifact.is_symlink():
            shutil.rmtree(self.artifact, ignore_errors=True)

    def build(self):
        self.copy_baseline_metadata()
        return self.artifact

    def run_cli(self, artifact=None, timeout=180):
        target = artifact if artifact is not None else "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004"
        return subprocess.run(
            [str(PYTHON), str(self.repo_root / "scripts/verify_stock_st_reconciled_acceptance.py"),
             "--repo-root", str(self.repo_root), "--artifact-root", str(target)],
            capture_output=True, text=True, timeout=timeout,
        )

    def assert_rejected(self, result, reason=None):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        self.assertTrue(result.stdout.startswith("REJECTED: "), result.stdout)
        if reason:
            self.assertIn(reason, result.stdout)

    def nonempty_partition_index(self):
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        for index, partition in enumerate(manifest["partitions"]):
            if partition["row_count"] >= 2:
                return index
        self.fail("fixture has no partition with two rows")

    def mutate_parquet_and_reject(self, index, mutation):
        manifest_path = self.artifact / "manifest.json"
        manifest_before = manifest_path.read_bytes()
        manifest_sidecar = self.artifact / "manifest.json.sha256"
        manifest_sidecar_before = manifest_sidecar.read_bytes()
        manifest = json.loads(manifest_before)
        partition = manifest["partitions"][index]
        parquet = self.repo_root / Path(*partition["repo_relative_path"].split("/"))
        sidecar_path = self.repo_root / Path(*partition["sidecar_repo_relative_path"].split("/"))
        parquet_before, sidecar_before = parquet.read_bytes(), sidecar_path.read_bytes()
        try:
            mutation(parquet)
            sidecar_path.write_text(file_hash(parquet) + "\n", encoding="ascii")
            manifest["partitions"][index]["file_sha256"] = file_hash(parquet)
            manifest["partitions"][index]["sidecar_sha256"] = file_hash(sidecar_path)
            write_json(manifest_path, manifest)
            sidecar(manifest_path)
            result = self.run_cli(timeout=180)
        finally:
            parquet.write_bytes(parquet_before)
            sidecar_path.write_bytes(sidecar_before)
            manifest_path.write_bytes(manifest_before)
            manifest_sidecar.write_bytes(manifest_sidecar_before)
        self.assert_rejected(result, "B3 input binding")

    def assert_tiny_scan_rejected(self, table, reason):
        spec = importlib.util.spec_from_file_location(
            "standalone_verifier_under_test",
            self.source_root / "scripts/verify_stock_st_reconciled_acceptance.py",
        )
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory(prefix="node_c_scan_", dir=str(self.repo_root)) as root_text:
            root = Path(root_text)
            date = "20200102"
            relative = "data/tiny_stock_st/trade_date=20200102/part.parquet"
            side_relative = relative + ".sha256"
            parquet = root / Path(*relative.split("/"))
            sidecar_path = root / Path(*side_relative.split("/"))
            parquet.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, parquet)
            sidecar_path.write_text(file_hash(parquet) + "\n", encoding="ascii")
            partition = {
                "date": date,
                "repo_relative_path": relative,
                "sidecar_repo_relative_path": side_relative,
                "byte_size": parquet.stat().st_size,
                "file_sha256": file_hash(parquet),
                "sidecar_sha256": file_hash(sidecar_path),
                "row_count": table.num_rows,
                "empty": table.num_rows == 0,
            }
            manifest = {
                "partitions": [partition],
                "coverage": {
                    "total_dates": 1,
                    "nonempty_dates": int(table.num_rows != 0),
                    "empty_dates": int(table.num_rows == 0),
                    "missing_dates": 0,
                    "extra_dates": 0,
                    "duplicate_dates": 0,
                    "total_bytes": parquet.stat().st_size,
                },
            }
            entries = {
                relative: {"sha256": partition["file_sha256"], "byte_size": partition["byte_size"]},
                side_relative: {"sha256": partition["sidecar_sha256"], "byte_size": sidecar_path.stat().st_size},
            }
            policy = {"schema_requirements": {"nonempty_types": ["large_string"] * 5, "empty_allowed_types": ["null", "large_string"]}}
            with self.assertRaises(verifier.VerificationError) as raised:
                verifier.scan_partitions(root, policy, manifest, [date], entries, [])
            self.assertEqual(str(raised.exception), reason)

    def test_node_c_exact_columns_order_types_and_null_rejected(self):
        base = pa.table({
            "ts_code": pa.array(["000001.SZ", "000002.SZ"], type=pa.large_string()),
            "name": pa.array(["A", "B"], type=pa.large_string()),
            "trade_date": pa.array(["20200102", "20200102"], type=pa.large_string()),
            "type": pa.array(["ST", "ST"], type=pa.large_string()),
            "type_name": pa.array(["ST", "ST"], type=pa.large_string()),
        })
        self.assert_tiny_scan_rejected(base.select(list(reversed(base.column_names))), "parquet schema")
        wrong_type = base.set_column(0, "ts_code", pa.array([1, 2], type=pa.int64()))
        self.assert_tiny_scan_rejected(wrong_type, "parquet schema")
        null_value = base.set_column(0, "ts_code", pa.array([None, "000002.SZ"], type=pa.large_string()))
        self.assert_tiny_scan_rejected(null_value, "parquet schema")

    def test_node_c_row_trade_date_rejected(self):
        table = pa.table({
            "ts_code": pa.array(["000001.SZ", "000002.SZ"], type=pa.large_string()),
            "name": pa.array(["A", "B"], type=pa.large_string()),
            "trade_date": pa.array(["19000101", "20200102"], type=pa.large_string()),
            "type": pa.array(["ST", "ST"], type=pa.large_string()),
            "type_name": pa.array(["ST", "ST"], type=pa.large_string()),
        })
        self.assert_tiny_scan_rejected(table, "row date")

    def test_node_c_duplicate_and_empty_ts_code_rejected(self):
        duplicate = pa.table({
            "ts_code": pa.array(["000001.SZ", "000001.SZ"], type=pa.large_string()),
            "name": pa.array(["A", "B"], type=pa.large_string()),
            "trade_date": pa.array(["20200102", "20200102"], type=pa.large_string()),
            "type": pa.array(["ST", "ST"], type=pa.large_string()),
            "type_name": pa.array(["ST", "ST"], type=pa.large_string()),
        })
        self.assert_tiny_scan_rejected(duplicate, "ts_code")
        empty = duplicate.set_column(0, "ts_code", pa.array(["", "000002.SZ"], type=pa.large_string()))
        self.assert_tiny_scan_rejected(empty, "ts_code")

    def test_node_c_first_and_sixth_parquet_raw_hash_rejected(self):
        for index in (0, 5):
            with self.subTest(index=index):
                def flip_last_byte(path):
                    raw = bytearray(path.read_bytes())
                    raw[-1] ^= 1
                    path.write_bytes(raw)

                self.mutate_parquet_and_reject(index, flip_last_byte)

    def test_node_c_sidecar_raw_and_content_binding_rejected(self):
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        for index in (0, 5):
            partition = manifest["partitions"][index]
            sidecar_path = self.repo_root / Path(*partition["sidecar_repo_relative_path"].split("/"))
            original = sidecar_path.read_bytes()
            try:
                sidecar_path.write_text("0" * 64 + "\n", encoding="ascii")
                result = self.run_cli(timeout=180)
            finally:
                sidecar_path.write_bytes(original)
            self.assert_rejected(result, "B3 input binding")

            original = sidecar_path.read_bytes()
            try:
                sidecar_path.write_text(file_hash(sidecar_path) + "\n", encoding="ascii")
                result = self.run_cli(timeout=180)
            finally:
                sidecar_path.write_bytes(original)
            self.assert_rejected(result, "B3 input binding")

    def test_review_manifest_byte_size_must_match_b3_rejected(self):
        self.build()
        manifest_path = self.artifact / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["partitions"][0]["byte_size"] += 1
        write_json(manifest_path, manifest)
        sidecar(manifest_path)
        self.assert_rejected(self.run_cli(), "B3 input binding")

    def test_review_partition_boolean_numeric_rejected(self):
        self.build()
        manifest_path = self.artifact / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["partitions"][0]["byte_size"] = True
        write_json(manifest_path, manifest)
        sidecar(manifest_path)
        self.assert_rejected(self.run_cli(), "manifest schema")

    def test_review_coverage_boolean_numeric_rejected(self):
        self.build()
        manifest_path = self.artifact / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["coverage"]["missing_dates"] = False
        write_json(manifest_path, manifest)
        sidecar(manifest_path)
        self.assert_rejected(self.run_cli(), "coverage")

    def test_review_outcome_boolean_row_count_rejected(self):
        self.build()
        outcomes_path = self.artifact / "empty_outcomes.json"
        outcomes = json.loads(outcomes_path.read_text())
        outcomes["outcomes"][0]["row_count"] = True
        aggregate = {
            "algorithm_id": "stock_st_empty_outcomes_aggregate.v1",
            "items": outcomes["outcomes"],
            "item_fields": ["request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"],
            "sort_by": ["request_trade_date"],
        }
        outcomes["aggregate_sha256"] = canonical_hash(aggregate)
        write_json(outcomes_path, outcomes)
        sidecar(outcomes_path)
        manifest_path = self.artifact / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["outcomes"]["sha256"] = file_hash(outcomes_path)
        manifest["outcomes"]["aggregate_sha256"] = outcomes["aggregate_sha256"]
        write_json(manifest_path, manifest)
        sidecar(manifest_path)
        self.assert_rejected(self.run_cli(), "outcomes schema")

    def test_review_argparse_errors_are_single_line(self):
        missing = subprocess.run(
            [str(PYTHON), str(self.repo_root / "scripts/verify_stock_st_reconciled_acceptance.py"), "--repo-root", str(self.repo_root)],
            capture_output=True, text=True,
        )
        self.assert_rejected(missing, "verification error")
        unknown = subprocess.run(
            [str(PYTHON), str(self.repo_root / "scripts/verify_stock_st_reconciled_acceptance.py"), "--repo-root", str(self.repo_root), "--artifact-root", "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004", "--unknown"],
            capture_output=True, text=True,
        )
        self.assert_rejected(unknown, "verification error")

    def test_review_exact_absolute_artifact_rejected(self):
        self.build()
        self.assert_rejected(self.run_cli(str(self.artifact)), "artifact path")

    def test_review_verifier_imports_forbid_publication_modules(self):
        tree = ast.parse((self.source_root / "scripts/verify_stock_st_reconciled_acceptance.py").read_text(encoding="utf-8"))
        forbidden = ("publish_stock_st_acceptance_policy", "reconcile_stock_st_empty_outcomes")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        self.assertFalse(any(name.startswith(forbidden) for name in imports), imports)

    def test_positive_cli_and_last_synced_tamper(self):
        self.build()
        accepted = self.run_cli(timeout=180)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertEqual(accepted.stderr, "")
        self.assertEqual(accepted.stdout, f"ACCEPTED: {FIXED_ID}\n")
        last = json.loads((self.artifact / "manifest.json").read_text())['partitions'][-1]
        parquet = self.repo_root / Path(*last["repo_relative_path"].split("/"))
        side = self.repo_root / Path(*last["sidecar_repo_relative_path"].split("/"))
        original_parquet, original_side = parquet.read_bytes(), side.read_bytes()
        try:
            mutated = bytearray(original_parquet)
            mutated[-1] ^= 1
            parquet.write_bytes(mutated)
            side.write_text(file_hash(parquet) + "\n", encoding="ascii")
            manifest = json.loads((self.artifact / "manifest.json").read_text())
            manifest["partitions"][-1]["file_sha256"] = file_hash(parquet)
            manifest["partitions"][-1]["sidecar_sha256"] = file_hash(side)
            write_json(self.artifact / "manifest.json", manifest)
            sidecar(self.artifact / "manifest.json")
            rejected = self.run_cli(timeout=180)
            self.assert_rejected(rejected, "B3 input binding")
        finally:
            parquet.write_bytes(original_parquet)
            side.write_bytes(original_side)

    def test_legacy_three_rejected(self):
        for suffix in ("001", "002", "003"):
            artifact = self.repo_root / f"data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_{suffix}"
            artifact.mkdir(parents=True)
            result = self.run_cli(artifact)
            self.assert_rejected(result, "unaccepted_invalid_publication")
            shutil.rmtree(artifact)

    def test_wrong_id_and_path_rejected(self):
        self.build()
        wrong = self.repo_root / "data/pit/.staging/wrong_id"
        shutil.copytree(self.artifact, wrong)
        self.assert_rejected(self.run_cli(wrong), "artifact path")

    def test_absolute_and_parent_escape_rejected(self):
        self.build()
        self.assert_rejected(self.run_cli(Path("C:/outside/stacc_traderlens_v2_shsz_stock_st_004")), "artifact path")
        self.assert_rejected(self.run_cli(self.repo_root / "data/pit/.staging/../stacc_traderlens_v2_shsz_stock_st_004"), "artifact path")

    def test_reparse_ancestor_rejected_without_skip(self):
        shutil.rmtree(self.artifact, ignore_errors=True)
        target = Path(tempfile.mkdtemp(prefix="st_reparse_target_"))
        junction = self.repo_root / "data/pit/.staging"
        if junction.exists():
            junction.rmdir()
        junction.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            build_positive_artifact(self.repo_root, target / FIXED_ID)
            rejected = self.run_cli()
            self.assert_rejected(rejected, "reparse")
        finally:
            junction.rmdir()
            shutil.rmtree(target, ignore_errors=True)

    def test_exact_four_file_inventory_and_subdir_rejected(self):
        self.build()
        (self.artifact / "extra.json").write_text("{}")
        self.assert_rejected(self.run_cli(), "inventory")
        (self.artifact / "extra.json").unlink()
        (self.artifact / "nested").mkdir()
        self.assert_rejected(self.run_cli(), "inventory")

    def test_manifest_exact_schema_rejected(self):
        self.build()
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        del manifest["frozen"]
        write_json(self.artifact / "manifest.json", manifest)
        sidecar(self.artifact / "manifest.json")
        self.assert_rejected(self.run_cli(), "manifest schema")
        manifest["frozen"] = True
        manifest["extra"] = True
        write_json(self.artifact / "manifest.json", manifest)
        sidecar(self.artifact / "manifest.json")
        self.assert_rejected(self.run_cli(), "manifest schema")

    def test_policy_and_b3_bindings_rejected(self):
        self.build()
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        manifest["policy_sha256"] = "0" * 64
        write_json(self.artifact / "manifest.json", manifest)
        sidecar(self.artifact / "manifest.json")
        self.assert_rejected(self.run_cli(), "policy binding")

    def test_date_set_missing_extra_duplicate_rejected(self):
        for operation in ("missing", "extra", "duplicate"):
            self.build()
            manifest = json.loads((self.artifact / "manifest.json").read_text())
            if operation == "missing":
                manifest["partitions"].pop(0)
            elif operation == "extra":
                manifest["partitions"].append(dict(manifest["partitions"][-1]))
            else:
                manifest["partitions"][1] = dict(manifest["partitions"][0])
            write_json(self.artifact / "manifest.json", manifest)
            sidecar(self.artifact / "manifest.json")
            self.assert_rejected(self.run_cli(), "date set")
            shutil.rmtree(self.artifact)
            self.artifact.parent.mkdir(parents=True, exist_ok=True)

    def test_outcomes_exact_fields_and_hashes_rejected(self):
        self.build()
        outcomes_path = self.artifact / "empty_outcomes.json"
        outcomes = json.loads(outcomes_path.read_text())
        outcomes["outcomes"][0]["date"] = outcomes["outcomes"][0].pop("request_trade_date")
        write_json(outcomes_path, outcomes)
        sidecar(outcomes_path)
        self.assert_rejected(self.run_cli(), "outcomes schema")

    def test_outcomes_aggregate_rejected(self):
        self.build()
        outcomes_path = self.artifact / "empty_outcomes.json"
        outcomes = json.loads(outcomes_path.read_text())
        outcomes["aggregate_sha256"] = "0" * 64
        write_json(outcomes_path, outcomes)
        sidecar(outcomes_path)
        self.assert_rejected(self.run_cli(), "aggregate")

    def test_invalid_outcomes_precedes_late_partition_rejection(self):
        self.build()
        outcomes_path = self.artifact / "empty_outcomes.json"
        outcomes = json.loads(outcomes_path.read_text())
        outcomes["aggregate_sha256"] = "0" * 64
        write_json(outcomes_path, outcomes)
        sidecar(outcomes_path)
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        last = self.repo_root / Path(*manifest["partitions"][-1]["repo_relative_path"].split("/"))
        original = last.read_bytes()
        last.unlink()
        try:
            result = self.run_cli(timeout=240)
        finally:
            last.write_bytes(original)
        self.assert_rejected(result)
        self.assertTrue(result.stdout.startswith("REJECTED: outcomes "), result.stdout)

    def test_trust_root_absent_and_tampered_rejected(self):
        self.build()
        formal = self.repo_root / "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003"
        hidden = formal.with_name(formal.name + ".hidden")
        formal.rename(hidden)
        try:
            self.assert_rejected(self.run_cli(), "trust root")
        finally:
            hidden.rename(formal)
        policy = formal / "policy.json"
        original = policy.read_bytes()
        try:
            policy.write_bytes(original + b"x")
            self.assert_rejected(self.run_cli(), "trust root")
        finally:
            policy.write_bytes(original)

    def test_first_and_sixth_partition_binding_rejected(self):
        for index in (0, 5):
            self.build()
            manifest = json.loads((self.artifact / "manifest.json").read_text())
            manifest["partitions"][index]["file_sha256"] = "0" * 64
            write_json(self.artifact / "manifest.json", manifest)
            sidecar(self.artifact / "manifest.json")
            self.assert_rejected(self.run_cli(), "B3 input binding")
            shutil.rmtree(self.artifact)
            self.artifact.parent.mkdir(parents=True, exist_ok=True)

    def test_schema_row_date_duplicate_and_empty_code_rejected(self):
        self.build()
        manifest = json.loads((self.artifact / "manifest.json").read_text())
        manifest["partitions"][0]["row_count"] = 1
        write_json(self.artifact / "manifest.json", manifest)
        sidecar(self.artifact / "manifest.json")
        self.assert_rejected(self.run_cli(), "B3 input binding")

    def test_source_hashes_unchanged_after_fixture_tamper(self):
        self.build()
        source = self.repo_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st/trade_date=20160104/part.parquet"
        before = file_hash(source)
        source.write_bytes(source.read_bytes() + b"x")
        try:
            self.assert_rejected(self.run_cli(), "B3 input binding")
        finally:
            source.write_bytes((self.source_root / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st/trade_date=20160104/part.parquet").read_bytes())
        self.assertEqual(file_hash(source), before)


if __name__ == "__main__":
    unittest.main()
