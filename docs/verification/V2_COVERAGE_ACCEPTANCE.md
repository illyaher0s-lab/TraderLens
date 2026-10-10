# V2 Coverage Canonical Artifact Acceptance

**Status:** accepted for the V2 data-processing boundary

## Canonical artifact

`695245b51005e50b` is the only canonical coverage package.

- Full build command exited with code 0 after 123.3 seconds.
- The manifest records 2,554 scanned trading days, 10,216 required-partition reads, and a completed structural validation.
- The detached manifest hash, three artifact hashes, input-manifest hash map, qualification bindings, schema, and current algorithm hash all verify.
- A repeat call returned `already_published` with unchanged artifact hashes.

## Conflict resolution

The following directories are **invalid for canonical acceptance**. Their contents remain untouched.

| Package | Reason |
|---|---|
| `65d176b9706667e6` | Earlier algorithm and missing schema, input-manifest map, detached manifest hash, and build-completion receipt. |
| `c65d089dd84b7f21` | Earlier algorithm and missing schema, input-manifest map, detached manifest hash, and build-completion receipt. |
| `5a50209be277c445` | Current algorithm/input binding, but created during a timed-out test run and has no build-completion receipt or detached manifest hash. |

Directory existence is not proof of a normal completed build; none of these three may supplement the canonical report.

## Accepted statistics

- Expected stock-days: 10,659,050, cross-checked against the bound qualification manifest.
- Complete stock-days: 10,476,263.
- Unavailable stock-days: 182,787.
- Structural errors: zero, from the recorded successful full build; this is not inferred from the artifact-only verifier.

The expected-universe regression group remains 3/5: two failures concern diagnostic exclusion counters and do not alter its expected-code assertions or the accepted coverage totals. They are not represented as a full regression pass.

## Boundary

This completes the V2 data-processing boundary only. It does not authorize B6/OOS, Promotion, Signal, or data-hole filling. B6/OOS requires its separately frozen split, OOS budget, and coverage-disclosure protocol.
