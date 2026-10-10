# V2 Availability-Bounded Qualification Successor Design

**Status:** Owner-approved design. The workflow remains `validation_unavailable`.

**Goal:** Produce one immutable, machine-verifiable qualification successor that records V2 availability-bounded admissibility from existing artifacts. It does not alter the old qualification, coverage data, universe, or B6 authorization state.

## Why this exists

The old qualification `de3fed9c3819d25c` is immutably `not_qualified` because its legacy algorithm treats every missing required row as a blocking gap. V2 scope freeze explicitly supersedes the zero-gap requirement: normal unavailable observations must be masked and disclosed, while structural defects remain blocking.

The successor therefore does not rename or reinterpret the old package. It records a new conclusion, `availability_bounded_qualified`, whose evidence is the unchanged predecessor qualification, the verified availability coverage package, and the owner-approved V2 scope freeze.

## Artifact layout and identity

Create exactly one directory when an authorized implementation runs:

```text
data/pit/qualification_successors/<successor_id>/
  manifest.json
  manifest.json.sha256
```

`successor_id` is the first 16 hex characters of SHA-256 over canonical JSON of the semantic payload below. The payload excludes `successor_id`, timestamps, absolute paths, temporary names, and machine values. `manifest.json.sha256` is SHA-256 of the written manifest bytes.

The implementation must fail if the target directory already exists. It must never write to:

- `data/pit/formal_packages/de3fed9c3819d25c/`
- `data/pit/formal_packages/35d996036cc04179/`
- `data/pit/coverage_packages/695245b51005e50b/`
- `data/pit/coverage_packages/de3fed9c3819d25c/`

## Required semantic payload

The manifest contains these exact classes of facts:

- `status: "availability_bounded_qualified"`
- `successor_schema_version`
- predecessor qualification package ID, raw manifest SHA-256, raw status `"not_qualified"`, scope hash, template hash, requirements hash, snapshot hash, guard hash, and algorithm hash
- SHA-256 of `docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md`
- canonical coverage package ID, raw coverage-manifest SHA-256, detached manifest hash, coverage algorithm hash, coverage schema version, structural-validation result, structural-error list, expected/complete/unavailable totals, field-missing counts, and all three parquet hashes
- template ID, version, and frozen template hash
- scope hash, requirements hash, and snapshot hash, each equal across the bound predecessor and coverage inputs

The manifest may repeat only data read from bound artifacts or from the current frozen template definition. It records no `DataSnapshotManifest.snapshot_id` and must not invent one.

## Qualification rule

The successor is `availability_bounded_qualified` only if all of these hold:

1. The predecessor manifest bytes hash to the recorded value and its immutable status is `not_qualified`.
2. The coverage manifest and detached sidecar hash are valid; all three referenced parquet hashes match their contents.
3. Coverage reports `status == "coverage_published"`, completed build status, passed structural validation, and an empty structural-error list.
4. Coverage algebra is exact: `complete_stock_days + unavailable_stock_days == expected_stock_days`.
5. Coverage binds the predecessor package ID and predecessor manifest hash, and its scope, requirements, template hash, and snapshot hash equal predecessor values.
6. The supplied template ID/version/hash resolve to the current frozen template; its hash matches both predecessor and coverage. Template governance may remain candidate here because approval is a later B6 hard gate.
7. The current V2 scope-freeze document bytes hash to the recorded value.

Ordinary unavailable observations and their field counts are disclosed evidence, not zero-gap failures. Any failed hash, structural defect, arithmetic inconsistency, schema mismatch, or binding mismatch rejects publication.

## Strict no-scan boundary

The successor builder may read only the two manifests, their hash sidecars, the three coverage parquet files for SHA-256, the scope-freeze document, and the frozen template definition. It may not read daily partitions, lifecycle data, membership data, or expected-universe helpers. It may not execute the qualification scanner or coverage builder.

It must not create, replace, or modify a coverage parquet, a formal qualification package, a data snapshot manifest, a database row, a ledger reservation, or a protocol snapshot. It has no B6, OOS, Gate, Promotion, Signal, or network capability.

## Relationship to B6 freeze

The B6 freeze entry accepts this successor only as availability-bounded qualification evidence. It still requires a formal discoverable `DataSnapshotManifest` with the correct `snapshot_id` and `semantic_hash`, an `approved` `StrategyTemplateDefinition`, real frozen gate/kill references, and the shared file-backed runtime ledger.

The successor itself must state that it does not authorize B6/OOS, Gate, Promotion, Signal, or data collection. It does not reserve or consume an OOS draw.

## Required verification for implementation

1. RED/GREEN positive test creates the successor from copied temporary metadata and asserts deterministic ID, sidecar validity, and exact manifest fields.
2. One-at-a-time mutation tests reject predecessor hash/status, coverage manifest hash/sidecar, each parquet hash, structural status/errors, arithmetic, scope/requirements/template/snapshot binding, scope-freeze hash, and template ID/version/hash mismatch.
3. A read-trace test proves no daily, lifecycle, membership, qualification-scan, or coverage-builder path is opened.
4. Pre/post SHA-256 assertions prove all four protected legacy artifact roots are byte-identical.
5. Tests assert no SQLite connection, ledger operation, protocol store, OOS runner, Gate, Promotion, or Signal dependency is called.

## Authorization status

This successor is metadata-only qualification evidence. It is not a B6 freeze record and does not change the current `validation_unavailable` status.
