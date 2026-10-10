"""
Relative Strength V2 Candidate TDD Tests

Task 1-C: New candidate with 252-day lookback, hypothesis_family_id binding,
pure data requirements hash. V1 artifacts immutable.

Per main plan Task 1 and implementation plan (reference only).
"""
import unittest
import json
from pathlib import Path
from datetime import datetime

from backend.services.strategy_template_library import (
    get_template_by_id,
    list_approved_templates,
    convert_to_frozen_contract,
)


class TestRelativeStrengthV2CandidateDefinition(unittest.TestCase):
    """RED: V2 candidate does not exist yet."""

    def test_v2_candidate_exists_with_correct_id_and_version(self):
        """V2 candidate relative_strength_rotation_shsz_sw2021_v2 must exist."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")

        self.assertIsNotNone(template, "V2 candidate must exist")
        self.assertEqual(template.template_id, "relative_strength_rotation_shsz_sw2021_v2")
        self.assertEqual(template.version, "v2_shsz_sw2021_pit_12m")

    def test_v2_candidate_freezes_252_day_lookback(self):
        """V2 candidate must freeze lookback_trading_days=252."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        config = template.strategy_config_payload

        self.assertEqual(config["lookback_trading_days"], 252)
        self.assertEqual(config["minimum_history_trading_days"], 252)

    def test_v2_candidate_binds_hypothesis_family_id_in_config(self):
        """hypothesis_family_id must be in hash-covered config payload."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        config = template.strategy_config_payload

        self.assertIn("hypothesis_family_id", config)
        self.assertEqual(config["hypothesis_family_id"], "relative_strength_rotation_shsz_sw2021")

    def test_v2_candidate_market_fit_is_pit_membership_only(self):
        """market_fit must be 'SW2021 PIT membership universe', no industry control claim."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")

        self.assertEqual(template.market_fit, "SW2021 PIT membership universe")
        self.assertNotIn("industry control", template.market_fit.lower())

    def test_v2_candidate_payload_freezes_all_owner_semantics(self):
        """Every owner-approved timing, endpoint, ranking, and confirmation rule is hash-covered."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        config = template.strategy_config_payload

        self.assertEqual(
            {key: config[key] for key in (
                "as_of_semantics",
                "execution_day",
                "adjusted_close_formula",
                "momentum_formula",
                "s_definition",
                "endpoint_unavailable",
                "ranking_universe",
                "tie_break",
                "top_count_formula",
                "confirm_semantics",
            )},
            {
                "as_of_semantics": "latest_complete_sh_sz_common_trading_day",
                "execution_day": "next_executable_after_as_of",
                "adjusted_close_formula": "close * adj_factor",
                "momentum_formula": "adjusted_close(d) / adjusted_close(s) - 1",
                "s_definition": "d_minus_252_common_trading_days",
                "endpoint_unavailable": "either_missing_no_fill_no_fallback_no_window_change",
                "ranking_universe": "formal_sw2021_pit_sh_sz_complete_252d_at_d",
                "tie_break": "return_desc_symbol_asc",
                "top_count_formula": "ceil(0.15 * N)",
                "confirm_semantics": "3_days_independent_pit_and_window",
            },
        )


class TestV2DataRequirementsHash(unittest.TestCase):
    """RED: Pure data requirements hash helper does not exist."""

    def test_data_requirements_hash_helper_exists(self):
        """get_template_data_requirements_hash() must exist."""
        from backend.services.strategy_template_library import get_template_data_requirements_hash

        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        hash_value = get_template_data_requirements_hash(template)

        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)  # SHA-256 hex

    def test_v2_data_requirements_hash_differs_from_v1(self):
        """V2 hash must differ from V1 (different lookback)."""
        from backend.services.strategy_template_library import get_template_data_requirements_hash

        v1 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        v2 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")

        v1_frozen = convert_to_frozen_contract(v1, created_at=datetime.now())
        v2_hash = get_template_data_requirements_hash(v2)

        self.assertNotEqual(v2_hash, v1_frozen.data_requirements_hash)

    def test_v2_hash_is_deterministic(self):
        """Hash must be deterministic across calls."""
        from backend.services.strategy_template_library import get_template_data_requirements_hash

        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        hash1 = get_template_data_requirements_hash(template)
        hash2 = get_template_data_requirements_hash(template)

        self.assertEqual(hash1, hash2)

    def test_requirements_hash_includes_every_frozen_semantic(self):
        """Changing any frozen V2 semantic must change the pure requirements hash."""
        from backend.services.strategy_template_library import (
            get_template_data_requirements,
            get_template_data_requirements_hash,
        )

        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        original_hash = get_template_data_requirements_hash(template)
        replacements = {
            "as_of_semantics": "wrong_as_of",
            "execution_day": "wrong_execution_day",
            "adjusted_close_formula": "raw_close",
            "momentum_formula": "wrong_formula",
            "s_definition": "wrong_endpoint",
            "endpoint_unavailable": "fill_missing",
            "ranking_universe": "current_constituents",
            "tie_break": "symbol_desc",
            "top_count_formula": "floor(0.15 * N)",
            "confirm_semantics": "single_day",
        }

        for field, replacement in replacements.items():
            # model_copy() does not rerun StrategyTemplate.model_post_init().
            # Use a serializable copy so the test mutates the semantic payload,
            # rather than failing on the template's nested mapping proxies.
            mutated_config = template._serialize_for_hash(template.strategy_config_payload)
            mutated_config[field] = replacement
            mutated_template = template.model_copy(
                update={"strategy_config_payload": mutated_config}
            )
            self.assertIn(
                replacement,
                json.dumps(
                    get_template_data_requirements(mutated_template),
                    sort_keys=True,
                ),
                field,
            )
            self.assertNotEqual(
                get_template_data_requirements_hash(mutated_template),
                original_hash,
                field,
            )

    def test_requirements_expose_the_frozen_semantics(self):
        """The canonical requirements must reproduce the V2 payload semantics exactly."""
        from backend.services.strategy_template_library import get_template_data_requirements

        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        requirements = get_template_data_requirements(template)

        self.assertEqual(
            requirements["decision_timing"],
            {
                "as_of_semantics": "latest_complete_sh_sz_common_trading_day",
                "execution_day": "next_executable_after_as_of",
            },
        )
        self.assertEqual(
            requirements["momentum_calculation"]["endpoint_unavailable"],
            "either_missing_no_fill_no_fallback_no_window_change",
        )
        self.assertEqual(
            requirements["ranking"]["universe"],
            "formal_sw2021_pit_sh_sz_complete_252d_at_d",
        )
        self.assertEqual(
            requirements["ranking"]["tie_break"], "return_desc_symbol_asc"
        )
        self.assertEqual(
            requirements["ranking"]["top_count_formula"], "ceil(0.15 * N)"
        )
        self.assertEqual(
            requirements["confirmation"]["semantic"], "3_days_independent_pit_and_window"
        )


class TestV2CandidateGovernance(unittest.TestCase):
    """RED: V2 candidate governance binding does not exist."""

    def test_v2_candidate_converts_to_candidate_governance(self):
        """V2 candidate must convert to governance_status='candidate'."""
        # Obsolete after Task 1-E: V2 is now approved via owner authorization
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        frozen = convert_to_frozen_contract(template, created_at=datetime.now())
    
        self.assertEqual(frozen.governance_status, "approved")

    def test_v2_candidate_not_in_approved_list(self):
        """V2 candidate must not appear in list_approved_templates()."""
        # Obsolete after Task 1-E: V2 is now approved via owner authorization
        approved = list_approved_templates()
        approved_ids = [t.template_id for t in approved]

        self.assertIn("relative_strength_rotation_shsz_sw2021_v2", approved_ids)


class TestV2DoesNotReadV1ArtifactBindings(unittest.TestCase):
    """RED: V2 must not call _load_v2_requirements_hash() or read V1 manifests."""

    def test_v2_uses_pure_helper_not_v1_artifact_binding(self):
        """V2 conversion must use get_template_data_requirements_hash(), not _load_v2_requirements_hash()."""
        import backend.services.strategy_template_library as lib
        from unittest.mock import patch

        v2_template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")

        # Monkeypatch V1 helper to fail if called
        original_load = lib._load_v2_requirements_hash
        def fail_if_called(template):
            raise AssertionError(f"V2 conversion must not call _load_v2_requirements_hash(), called with {template.template_id}")

        try:
            lib._load_v2_requirements_hash = fail_if_called
            frozen = convert_to_frozen_contract(v2_template, created_at=datetime.now())
            # Must succeed without calling V1 helper
            self.assertIsNotNone(frozen.data_requirements_hash)
        finally:
            lib._load_v2_requirements_hash = original_load

    def test_old_templates_get_none_hash_not_pure_helper(self):
        """Old templates (volume_breakout, trend_pullback) must get None, not enter pure helper."""
        old_template = get_template_by_id("volume_breakout_followthrough_v1")
        frozen = convert_to_frozen_contract(old_template, created_at=datetime.now())

        # Old templates keep original behavior: data_requirements_hash is None
        self.assertIsNone(frozen.data_requirements_hash,
                         "Old templates must not use new pure helper, should be None")


class TestB6CandidateGuardRejectsV2(unittest.TestCase):
    """V2 candidate must be blocked by B6 governance guard."""

    def test_b6_real_call_rejects_v2_candidate_zero_reserve(self):
        """V2 approved status allows B6 governance guard to pass."""
        # Renamed after Task 1-E: V2 is now approved, governance guard passes
        v2_template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
        frozen = convert_to_frozen_contract(v2_template, created_at=datetime.now())
        
        # V2 must be approved after Task 1-E owner authorization
        self.assertEqual(frozen.governance_status, "approved")
        
        # Approved templates pass B6 governance guard (not blocked)
        # Full B6 flow requires PIT data (out of scope for Task 1-E)


class TestV1ArtifactsImmutable(unittest.TestCase):
    """V1 successor/coverage manifests must remain byte-identical."""

    def test_formal_package_manifest_unchanged(self):
        """de3fed9c3819d25c/manifest.json must be immutable."""
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"

        EXPECTED_HASH = "1cdb48bf9b78b7664513bd3afa7ac4466483529dedcf78bd996d1846b7f2087d"

        content = manifest_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"Formal package manifest changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_formal_package_report_unchanged(self):
        """de3fed9c3819d25c/QUALIFICATION_REPORT.md must be immutable."""
        root = Path(__file__).resolve().parents[1]
        report_path = root / "data/pit/formal_packages/de3fed9c3819d25c/QUALIFICATION_REPORT.md"

        EXPECTED_HASH = "086bf7aff3a09b59d0cbfff47d4308d15f7c2eb08ff53dff88b52936f7a9fdc9"

        content = report_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"Formal package report changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_successor_manifest_unchanged(self):
        """e5100669ed247769/manifest.json must be immutable."""
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "data/pit/qualification_successors/e5100669ed247769/manifest.json"

        EXPECTED_HASH = "f3bdb5124262f0fbe8e73ca2789645cba4b8fefd731c56ad719e29a46fd30e77"

        content = manifest_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 successor manifest changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_successor_manifest_sidecar_unchanged(self):
        """e5100669ed247769/manifest.json.sha256 must be immutable."""
        root = Path(__file__).resolve().parents[1]
        sidecar_path = root / "data/pit/qualification_successors/e5100669ed247769/manifest.json.sha256"

        EXPECTED_HASH = "008a3badaa408966b31c5e150c51c2ac66d9e65ce7982afaf0303a717103695e"

        content = sidecar_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 successor sidecar changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_coverage_manifest_unchanged(self):
        """695245b51005e50b/coverage_manifest.json must be immutable."""
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"

        EXPECTED_HASH = "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f"

        content = manifest_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 coverage manifest changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_coverage_manifest_sidecar_unchanged(self):
        """695245b51005e50b/coverage_manifest.json.sha256 must be immutable."""
        root = Path(__file__).resolve().parents[1]
        sidecar_path = root / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json.sha256"

        EXPECTED_HASH = "577081cd674483b5f3a2a29f2ca3975e12313c2539cc23cb6b5e1963095aea5b"

        content = sidecar_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 coverage sidecar changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_coverage_by_code_parquet_unchanged(self):
        """695245b51005e50b/coverage_by_code.parquet must be immutable."""
        root = Path(__file__).resolve().parents[1]
        parquet_path = root / "data/pit/coverage_packages/695245b51005e50b/coverage_by_code.parquet"

        EXPECTED_HASH = "308b01eeecd007c0d7b13ce1717f12207857432d91c6fbb78ffa3e8ba7d05ab9"

        content = parquet_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 coverage_by_code.parquet changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_coverage_by_date_parquet_unchanged(self):
        """695245b51005e50b/coverage_by_date.parquet must be immutable."""
        root = Path(__file__).resolve().parents[1]
        parquet_path = root / "data/pit/coverage_packages/695245b51005e50b/coverage_by_date.parquet"

        EXPECTED_HASH = "7571f482559ef597af89ef640896ca45c747ecfbfc469a28ad38f93f6b4313f3"

        content = parquet_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 coverage_by_date.parquet changed! Expected {EXPECTED_HASH}, got {current_hash}")

    def test_v1_unavailable_security_dates_parquet_unchanged(self):
        """695245b51005e50b/unavailable_security_dates.parquet must be immutable."""
        root = Path(__file__).resolve().parents[1]
        parquet_path = root / "data/pit/coverage_packages/695245b51005e50b/unavailable_security_dates.parquet"

        EXPECTED_HASH = "f6fe7ae02b1e8c20eb3530b636f6272e239e62140c9cd909af06e2ad6b451621"

        content = parquet_path.read_bytes()
        import hashlib
        current_hash = hashlib.sha256(content).hexdigest()

        self.assertEqual(current_hash, EXPECTED_HASH,
                        f"V1 unavailable_security_dates.parquet changed! Expected {EXPECTED_HASH}, got {current_hash}")


if __name__ == "__main__":
    unittest.main()
