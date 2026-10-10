# PIT Membership Date Reconciliation Policy

**Main-plan task:** Task 1 — Gate 0 before formal validation wiring.  
**Owner decision date:** 2026-07-15.  
**Scope:** TraderLens consumption of already-bound SW2021 membership intervals; this is not a statement about vendor coverage or source semantics.

## Decision

The source `effective_from` and `effective_to` fields are preserved exactly in
the formal PIT membership artifact. The publisher must not truncate them,
shift them to trading days, or rewrite their canonical records.

For a validation-window SH/SZ common trading day `d`, membership is valid only
when:

```text
d <= snapshot_date
effective_from <= d
effective_to is None or d <= effective_to
```

The interval is closed at both ends. A non-trading effective date is not
adjusted: ordinary date comparison determines membership on the next or prior
common trading day.

## Window and terminal rules

- An interval beginning before `2016-01-04` and covering that day is already
  effective on the first validation-window day.
- An interval ending after the validation-window end, but not after
  `snapshot_date`, is kept unmodified. No future membership is read because
  queries never exceed the validation window.
- `effective_to=None` means only that no termination was observed through
  `snapshot_date`; no query may use it after `snapshot_date`.
- Any non-null effective date after `snapshot_date`, or an
  `effective_from > effective_to` interval, is a structural rejection.
- A snapshot with `snapshot_date` before the target validation-window end
  cannot cover that complete window and returns `validation_unavailable`.

## Canonicalization and boundary

The raw source dates, including null `effective_to`, enter canonical content
hashing. A window-projected or truncated interval must never replace them in
the canonical record.

This policy resolves only `membership_date_semantics_unavailable`: it defines
TraderLens consumption boundaries without redefining Tushare's membership-date
semantics. It does not establish `include_delisted=true`; the independent
`include_delisted_source_contract_unavailable` blocker remains. It authorizes
no snapshot publication, data scan, protocol, ledger operation, B6/OOS, Gate,
Promotion, or Signal action. Global status remains `validation_unavailable`.
