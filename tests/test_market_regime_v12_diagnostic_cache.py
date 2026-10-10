from pathlib import Path

import scripts.diagnose_market_regime_v12_daily_gaps as diagnostic


def test_partition_metadata_is_hashed_once_for_shared_day_and_once_again_for_self_check(tmp_path: Path, monkeypatch) -> None:
    formal = tmp_path / "formal"
    for interface in ("daily", "stock_st", "suspend_d"):
        path = formal / interface / "trade_date=20200101" / "part.parquet"
        path.parent.mkdir(parents=True)
        path.write_bytes(interface.encode("ascii"))

    calls: dict[str, int] = {}
    real_sha_file = diagnostic._sha_file

    def counted_sha_file(path: Path) -> str:
        key = str(path)
        calls[key] = calls.get(key, 0) + 1
        return real_sha_file(path)

    monkeypatch.setattr(diagnostic, "_sha_file", counted_sha_file)
    metadata = diagnostic._partition_metadata(formal, "20200101")
    shared_gap_partitions = [metadata, metadata]
    for partitions in shared_gap_partitions:
        assert partitions["daily"]["sha256"]
        assert partitions["stock_st"]["sha256"]
        assert partitions["suspend_d"]["sha256"]
    for item in metadata.values():
        assert counted_sha_file(diagnostic.ROOT / item["repo_relative_path"])

    assert set(calls.values()) == {2}
