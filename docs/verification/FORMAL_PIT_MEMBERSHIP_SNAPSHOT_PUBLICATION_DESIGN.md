# Formal PIT Membership Snapshot Publication Design

**Status:** Owner-approved corrective implementation and source-evidence preflight for `_002`; publication is not yet authorized. Workflow status remains `validation_unavailable`.

## Purpose and non-goals

Publish one immutable, historical-interval `PointInTimeMembershipSnapshot` for the existing V2 SH/SZ SW2021 source. It is a missing B6 admission input, not a data collection, data-hole-filling, coverage, qualification, OOS, Gate, Promotion, or Signal task.

The design never derives membership from coverage, expected universe, current constituents, qualification output, or an availability mask. It reads only the already bound SW2021 membership source parquet files during a separately authorized future implementation. It does not collect, patch, remap, or add exceptions.

## Owner decisions

- `pims_traderlens_v2_shsz_sw2021_pit_001` is permanently retired and unaccepted audit evidence. Its directory is immutable, must not be deleted, changed, overwritten, republished, or supplied to B6.
- The only prospective formal write-once identity is `pims_traderlens_v2_shsz_sw2021_pit_002`.
- Snapshot semantics are historical intervals. For a trade date `d`, a record is active exactly when `effective_from <= d` and (`effective_to is None` or `d <= effective_to`). Both finite boundaries are inclusive.
- `snapshot_date` is the actual artifact publication/freeze date. It is not a member effective date, cannot be prefilled or backfilled, and a published artifact must never be used for `d > snapshot_date`.
- `effective_to=None` means active through `snapshot_date` only; it does not assert future validity.
- The artifact itself binds the immutable formal data manifest identity `ds_traderlens_v2_shsz_pit_001`, its V2 semantic hash `da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e`, metadata-only provenance reference `uref_traderlens_v2_shsz_sw2021_pit_001`, and the source membership/candidate hashes. The already published DataSnapshotManifest remains byte-identical.
- `include_delisted=true` must be proved from source records and validation results. It is never a contract-driven assertion.

## Artifact layout and identity

The future publisher may publish only:

```text
data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002/
  manifest.json
  manifest.json.sha256
  records.parquet
  records.parquet.sha256
```

`snapshot_id` is the owner-assigned business identity above. It is never a content hash, directory name, staging identifier, coverage ID, qualification ID, semantic hash, or metadata-only universe-reference ID.

The manifest has a deterministic `canonical_content_hash`: SHA-256 of canonical JSON excluding `canonical_content_hash`, `manifest_published_at`, absolute paths, machine paths, temporary names, and operator identity. The detached manifest sidecar is SHA-256 of the written raw manifest bytes. `records.parquet.sha256` is SHA-256 of written parquet bytes.

For the same owner ID, a pre-existing artifact with the same canonical content hash and valid sidecars returns `already_published`. Any different canonical content hash, missing file, invalid sidecar, or invalid existing artifact is a conflict and fails without overwrite. A failed pre-publication validation writes no formal artifact.

## Required content and bindings

The artifact contains:

- `snapshot_id`, `snapshot_date`, `frozen=true`, schema version, algorithm-content hash, and fixed interval-semantics version.
- `universe_rule_type="point_in_time_membership"`, `membership_source`, `include_delisted`, `quality_status`, and `gaps`.
- A records parquet encoding `UniverseMembershipRecord` values: `symbol`, `effective_from`, `effective_to`, `source`, and this formal `snapshot_id`.
- Explicit binding fields for formal data manifest ID, V2 semantic hash, metadata-only universe reference ID, SW2021 membership manifest SHA-256, SW2021 candidate SHA-256, candidate universe-definition hash, and every relevant source hash already bound by canonical coverage.
- Record count, date range, source manifest hashes, records parquet hash, canonical content hash, raw manifest hash, and a non-authorization statement for B6/OOS, Gate, Promotion, Signal, and data collection.

The published records must use the formal snapshot ID, not the upstream staging identifier. The upstream metadata-only universe reference remains provenance only and never enters a B6 `universe` parameter.

## Structural validation before publication

The future implementation must validate before it writes the formal directory:

1. Recompute and verify the source membership manifest, candidate, formal data manifest, universe reference, qualification successor, coverage manifest/sidecar, and V2 scope-freeze bindings.
2. Verify the candidate and source hashes agree with the canonical coverage input map and V2 semantic/template/requirements/scope chain.
3. Read only the previously bound membership parquet source files needed to construct records. It must not read daily, daily_basic, stk_limit, adj_factor, lifecycle, expected-universe, or coverage detail data.
4. Prove `include_delisted=true` from source data and validation evidence. If it cannot be proved, fail before publication.
5. Reject duplicate records with the same full identity, invalid dates, `effective_to < effective_from`, records outside the artifact horizon, records using the wrong snapshot ID, and any use after `snapshot_date`.
6. Define and validate symbol-level overlap policy before code is written. Overlapping intervals are structural failures unless the source contract proves they are identical representations of the same membership state and canonicalization merges them deterministically without losing provenance. No per-symbol exception is permitted.
7. Validate date-level PIT lookup against the fixed closed-interval rule and candidate/source metadata. Ordinary availability limitations are disclosed in `gaps`; they are never patched. Structural defects fail loud and publish nothing.

## B6 boundary

This artifact alone does not authorize B6. A future B6 coverage-bound entry must accept only the formal snapshot as `universe`, reject metadata-only references and candidate JSON, enforce `d <= snapshot_date`, and cross-validate the formal snapshot bindings against the immutable formal data manifest and provenance reference. The existing `DataSnapshotManifest.universe_snapshot_ids=()` remains correct and is not rewritten.

Independent hard gates remain: approved template governance, frozen gate/kill criteria, a shared file-backed runtime owner, compatibility repairs explicitly excluded from this design, and a separately authorized B6 freeze/execution workflow.

## Required future tests

- RED/GREEN tests for inclusive interval membership, `None` bounded by `snapshot_date`, and rejection of dates after `snapshot_date`.
- Real parquet-boundary tests proving records are from the named membership source, not coverage or current constituents.
- Structural-failure tests for duplicate, overlap, invalid interval, wrong snapshot ID, and unproven delisted coverage; each proves zero formal artifact writes.
- Binding/tamper tests for every source hash, formal data manifest ID/semantic hash, universe reference, candidate definition hash, records hash, manifest sidecar, and canonical content hash.
- Write-once tests: same content is `already_published`; changed content conflicts without overwrite.
- Pre/post SHA-256 tests proving all existing qualification, coverage, successor, formal-data-manifest, and universe-reference artifacts remain unchanged.
- Tests proving no B6/OOS, ledger, Gate, Promotion, Signal, database write, network call, or business-market partition read.

## Authorization status

This document authorizes only corrective publisher/verifier/test implementation and a source-evidence preflight for `pims_traderlens_v2_shsz_sw2021_pit_002`. It does not authorize `_002` publication until an independent source contract proves `include_delisted=true` and resolves the conflicting date semantics. It does not authorize modifying the existing formal data manifest, data collection, data repair, runtime-owner configuration, protocol creation, B6/OOS, Gate, Promotion, Signal, or ledger reservation/consumption. Any future publication removes only this PIT-membership blocker; overall workflow status remains `validation_unavailable`.
