"""Full local audit of the SW2021-scoped industry-relative strategy universe."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
SW_DIR = FORMAL / "sw_l1_membership"


def _life() -> pd.DataFrame:
    table = pd.concat([
        pd.read_parquet(FORMAL / "stock_basic" / f"list_status={status}" / "part.parquet", columns=["ts_code", "list_date", "delist_date"])
        for status in "LDP"
    ]).set_index("ts_code")
    supplement = json.loads((ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e/security_lifecycle_candidate.json").read_text())
    for item in supplement["codes"]:
        table.loc[item["ts_code"]] = [item["list_date"], item["delist_date"]]
    table["list_date"] = pd.to_numeric(table["list_date"])
    table["delist_date"] = pd.to_numeric(table["delist_date"]).fillna(99991231)
    return table


def _events(days: list[int]):
    manifest = json.loads((SW_DIR / "manifest.json").read_text())
    parts = [part for part in manifest["partitions"] if part["src"] == "SW2021"]
    frame = pd.concat([pd.read_parquet(SW_DIR / part["name"], columns=["ts_code", "l1_code", "in_date", "out_date"]) for part in parts])
    frame["in_date"] = pd.to_numeric(frame["in_date"])
    frame["out_date"] = pd.to_numeric(frame["out_date"]).fillna(99991231)
    index = pd.Index(days)
    starts, ends = defaultdict(list), defaultdict(list)
    for row in frame.itertuples(index=False):
        start = int(index.searchsorted(row.in_date, side="left"))
        end = int(index.searchsorted(row.out_date, side="right"))
        if start < len(days) and end > start:
            starts[start].append((row.ts_code, row.l1_code))
            if end < len(days):
                ends[end].append((row.ts_code, row.l1_code))
    return manifest, parts, starts, ends


def run_audit() -> dict:
    calendar = pd.read_parquet(FORMAL / "trade_cal" / "part.parquet")
    days = sorted(pd.to_numeric(calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"]).astype(int).tolist())
    lifecycle = _life()
    manifest, parts, starts, ends = _events(days)
    active: dict[str, Counter] = defaultdict(Counter)
    daily_stock_days = eligible_stock_days = excluded_pre_listing = excluded_no_industry = lifecycle_unknown = 0
    for index, date in enumerate(days):
        for code, industry in ends[index]:
            active[code][industry] -= 1
            if active[code][industry] == 0:
                del active[code][industry]
            if not active[code]:
                del active[code]
        for code, industry in starts[index]:
            active[code][industry] += 1
        codes = pd.read_parquet(FORMAL / "daily" / f"trade_date={date}" / "part.parquet", columns=["ts_code"])["ts_code"].dropna().unique()
        daily_stock_days += len(codes)
        life = lifecycle.reindex(codes)
        lifecycle_unknown += int(life["list_date"].isna().sum())
        listed = life.dropna(subset=["list_date"])
        valid = set(listed.index[(listed["list_date"] <= date) & (listed["delist_date"] >= date)])
        excluded_pre_listing += len(codes) - len(valid)
        eligible = {code for code in valid if len(active.get(code, ())) == 1}
        excluded_no_industry += len(valid) - len(eligible)
        eligible_stock_days += len(eligible)
    supplement_path = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e/security_lifecycle_candidate.json"
    selected = [{"name": part["name"], "sha256": part["sha256"]} for part in parts]
    scope = {
        "taxonomy_source": "SW2021",
        "pit_rule": "in_date <= as_of_date <= out_date",
        "universe_rule": "listed_daily AND exactly_one_effective_sw2021_l1_membership",
        "membership_partitions": selected,
        "vendor_lifecycle_candidate_sha256": hashlib.sha256(supplement_path.read_bytes()).hexdigest(),
    }
    status = "candidate_universe_ready" if lifecycle_unknown == 0 else "candidate_universe_not_ready"
    evidence = {
        "status": status,
        "taxonomy_source": "SW2021",
        "checked_trade_days": len(days),
        "daily_stock_days": daily_stock_days,
        "eligible_stock_days": eligible_stock_days,
        "excluded_pre_listing_stock_days": excluded_pre_listing,
        "excluded_no_pit_industry_stock_days": excluded_no_industry,
        "lifecycle_unknown_stock_days": lifecycle_unknown,
        "universe_definition_hash": hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest(),
        "formal_qualification_run": False,
    }
    (SW_DIR / "sw2021_universe_candidate.json").write_text(json.dumps(evidence, indent=2))
    (ROOT / "docs/verification/SW2021_PIT_UNIVERSE_CANDIDATE.md").write_text(
        "# SW2021 PIT Universe Candidate\n\n" + "\n".join(f"- {key}: {value}" for key, value in evidence.items()) + "\n\nUnclassified codes are explicitly excluded; this is not formal qualification.\n"
    )
    return evidence


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps({"status": result["status"], "eligible_stock_days": result["eligible_stock_days"]}))
    sys.exit(0 if result["status"] == "candidate_universe_ready" else 1)
