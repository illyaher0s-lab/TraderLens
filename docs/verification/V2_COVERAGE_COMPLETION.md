# V2 Coverage Package Completion Summary

**Date:** 2026-07-13  
**Status:** Data processing stage complete  
**Coverage Hash:** `65d176b9706667e6`

## What was delivered

Real availability coverage package for qualification package `de3fed9c3819d25c`:

- **Expected stock-days:** 10,659,050 (matches qualification manifest)
- **Complete stock-days:** 10,476,263 (98.29%)
- **Unavailable stock-days:** 182,787 (1.71%)
- **Structural errors:** 0

## Artifacts

1. `data/pit/coverage_packages/65d176b9706667e6/`
   - `coverage_manifest.json` (coverage hash, totals, field counts, top-10s)
   - `coverage_by_date.parquet` (2,554 rows, daily aggregates)
   - `coverage_by_code.parquet` (per-security aggregates)
   - `unavailable_security_dates.parquet` (182,787 unavailable observations with sorted missing_fields)

2. `docs/verification/V2_AVAILABILITY_COVERAGE_REPORT.md`
   - Mandatory disclosure: "availability mask is coverage diagnostic product, not new formal package"
   - Field-level unavailability breakdown
   - Top 10 dates and codes by unavailable count
   - B6/OOS requirements (preserve denominator, disclose coverage rates)

## Verification results

All checks passed:
- ✓ Expected matches qualification (10,659,050)
- ✓ Algebraic invariant (complete + unavailable = expected)
- ✓ Unavailable parquet row count equals manifest unavailable_stock_days
- ✓ Missing fields sorted per row
- ✓ Coverage_by_date aggregates to global totals
- ✓ Coverage_by_code aggregates to global totals
- ✓ Field counts match expanded missing_fields
- ✓ Top-10 sorted descending by count, then ascending by date/code
- ✓ No structural errors (no duplicate rows, no date mismatches, all partitions present)
- ✓ Coverage hash binds template, snapshot, requirements, scope, algorithm
- ✓ Old packages untouched (35d996036cc04179, de3fed9c3819d25c)
- ✓ Placeholder coverage_packages/de3fed9c3819d25c still marked STATUS_INVALID

## Field-level unavailability

- `daily`: 181,890 stock-days (1.71%)
- `daily_basic`: 181,903 stock-days (1.71%)
- `stk_limit`: 7,699 stock-days (0.07%)
- `adj_factor`: 258 stock-days (0.002%)

Note: Fields can overlap; total field-missing count > unavailable_stock_days.

## Implementation approach

TDD with RED-GREEN phases:
1. Comprehensive failing tests written first
2. Real full-scan implementation using:
   - `eligible_codes_independent()` for expected universe (no daily row dependency)
   - Parallel reads (4 workers) for 2,554 dates
   - Per security-date unavailable tracking with sorted missing_fields
   - Set operations (intersection of available codes across tables)
3. ~560s total runtime for full 10.66M stock-day scan
4. Verification script confirms all invariants without re-scanning

## What this is NOT

Per V2 freeze and report disclosure:
- NOT a new formal qualification package
- NOT a tradability mask or market-entry eligibility rule
- NOT a backtest universe
- NOT authorization for B6/OOS/Promotion/Signal

## Next steps (if user approves)

This coverage package is the data processing endpoint per:
- `docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md` section "Data-stage completion criteria"
- No new data collection, identity mapping, or coverage gap-filling
- B6/OOS may begin (separate workflow, requires frozen split and pre-registration)

If B6/OOS skips unavailable observations, it MUST:
1. Keep expected=10,659,050 as denominator
2. Report per-date coverage rates alongside returns
3. NOT present returns only on complete observations while hiding coverage changes

## Is this the data-hole-filling stage conclusion?

YES. Per freeze: "The V2 data-processing stage is complete when the historical availability mask is reproducible from the bound snapshot and known gaps are disclosed rather than patched."

Ordinary coverage gaps (1.71% unavailable) do NOT reopen data engineering unless they demonstrate:
1. Future information leakage
2. Date misalignment
3. Duplicate-security counting
4. Wrong calculations in the supported subset

None of these defects were found (0 structural errors).
