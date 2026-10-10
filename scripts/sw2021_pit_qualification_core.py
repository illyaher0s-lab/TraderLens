"""Pure, bounded helpers for SW2021 PIT universe qualification."""
from collections import Counter, defaultdict

import pandas as pd


def build_events(memberships: pd.DataFrame, days: list[int]):
    index = pd.Index(days)
    starts, ends = defaultdict(list), defaultdict(list)
    for row in memberships[["ts_code", "l1_code", "in_date", "out_date"]].itertuples(index=False):
        start = int(index.searchsorted(row.in_date, side="left"))
        end = int(index.searchsorted(row.out_date, side="right"))
        if start < len(days) and end > start:
            starts[start].append((row.ts_code, row.l1_code))
            if end < len(days):
                ends[end].append((row.ts_code, row.l1_code))
    return starts, ends


def step_active(active: dict[str, Counter], ends, starts, index: int) -> dict[str, Counter]:
    counts = {code: Counter(industries) for code, industries in active.items()}
    for code, industry in ends[index]:
        counts[code][industry] -= 1
        if counts[code][industry] == 0:
            del counts[code][industry]
        if not counts[code]:
            del counts[code]
    for code, industry in starts[index]:
        counts.setdefault(code, Counter())[industry] += 1
    return counts


def eligible_codes_independent(lifecycle: pd.DataFrame, active: dict[str, Counter], date: int):
    """Build expected universe independent of daily row existence.
    
    Expected universe = all codes where:
    - list_date <= date <= delist_date (from lifecycle)
    - has exactly one SW2021 L1 membership (from active)
    
    Does NOT depend on daily/daily_basic/stk_limit/adj_factor rows.
    """
    # All codes with valid lifecycle at this date
    listed = lifecycle.dropna(subset=["list_date"])
    valid = set(listed.index[(listed["list_date"] <= date) & (listed["delist_date"] >= date)])
    
    # Filter by membership
    ambiguous = {code for code in valid if len(active.get(code, Counter())) > 1}
    eligible = {code for code in valid if len(active.get(code, Counter())) == 1}
    excluded_no_industry = len(valid) - len(eligible) - len(ambiguous)
    
    excluded_pre = len(lifecycle) - len(listed)  # ponytail: approximate, exact needs separate tracking
    unknown = 0  # lifecycle is complete by construction
    
    return eligible, excluded_pre, excluded_no_industry, unknown, ambiguous


def eligible_codes(daily_codes: set[str], lifecycle: pd.DataFrame, active: dict[str, Counter], date: int):
    """Legacy wrapper - delegates to independent version, then validates daily_codes against lifecycle."""
    eligible, excluded_pre, excluded_no_industry, unknown, ambiguous = eligible_codes_independent(lifecycle, active, date)
    
    # Check for codes in daily but missing lifecycle (data quality issue)
    lifecycle_unknown = len(daily_codes - set(lifecycle.index))
    
    return eligible, excluded_pre, excluded_no_industry, lifecycle_unknown, ambiguous


def apply_market_scope(eligible: set[str], market_scope: list[str]) -> tuple[set[str], set[str], set[str]]:
    """Apply market scope filter to eligible codes.
    
    Returns:
        expected: codes in scope
        bse: .BJ codes out of scope
        other: other codes out of scope
    """
    scope_suffixes = {f".{m}" for m in market_scope}
    expected = {code for code in eligible if any(code.endswith(s) for s in scope_suffixes)}
    bse = {code for code in eligible if code.endswith(".BJ") and code not in expected}
    other = eligible - expected - bse
    return expected, bse, other
