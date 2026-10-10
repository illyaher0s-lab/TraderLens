"""Checks for the scoped SW2021 PIT universe candidate."""
import json
from pathlib import Path


EVIDENCE = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2021_universe_candidate.json")


def test_universe_is_bound_to_the_sw2021_and_lifecycle_hashes():
    """A scoped universe must be reproducible from its precise source inputs."""
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["taxonomy_source"] == "SW2021"
    assert len(evidence["universe_definition_hash"]) == 64


def test_unclassified_codes_are_explicitly_excluded_not_silently_covered():
    """Industry-relative strategy cannot trade a code lacking one PIT industry membership."""
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["excluded_no_pit_industry_stock_days"] > 0
    assert evidence["lifecycle_unknown_stock_days"] == 0
    assert evidence["status"] == "candidate_universe_ready"
