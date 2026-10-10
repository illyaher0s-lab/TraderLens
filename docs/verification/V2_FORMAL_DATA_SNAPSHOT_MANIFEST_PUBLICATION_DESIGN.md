# V2 Formal DataSnapshotManifest Publication Design

**Status:** Owner-approved design. Current workflow status remains `validation_unavailable`.

**Scope:** Publish immutable V2 snapshot provenance from existing metadata and the verified coverage aggregate. This is not data collection, a daily-partition scan, B6 freeze/execution, a protocol record, a ledger action, Gate, Promotion, or Signal.

## Decisions bound by this design

- Formal snapshot identity is owner-assigned: `ds_traderlens_v2_shsz_pit_001`.
- Provider is exactly `mixed_vendor_tushare`, backed by separate vendor and Tushare/SW2021 source hashes; no vendor brand is invented.
- Source retrieval time is unknown: `retrieval_date=None`, `retrieval_date_status="unknown"`. `manifest_published_at` is publication audit time only, never a retrieval-date proxy and never part of the existing V2 semantic hash.
- A metadata-only universe reference is owner-assigned: `uref_traderlens_v2_shsz_sw2021_pit_001`. It is provenance only, never a `PointInTimeMembershipSnapshot.snapshot_id` and never an entry in `universe_snapshot_ids`.
- `semantic_hash` is exactly `da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e`, the established V2 bound-snapshot semantic hash in the predecessor, coverage, and availability successor. The legacy builder's different algorithm is not used for this path.
- `quality_status="ok"` means structural/time/binding checks pass. It does not mean full-market coverage or B6 readiness. `gaps=("availability_limited",)` is mandatory and the structured coverage disclosure carries the actual totals and field counts.

## Artifact layout

An implementation publishes exactly these two immutable metadata artifacts:

```text
data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/
  manifest.json
  manifest.json.sha256

data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/
  manifest.json
  manifest.json.sha256
```

Each directory is write-once. For the same owner-assigned ID, an existing byte-identical manifest content hash returns `already_published`; a different content hash is a conflict and must fail without overwrite. No random IDs, hash-derived IDs, staging names, or machine paths are used as identities.

`manifest.json.sha256` is SHA-256 of written manifest bytes. The manifest also stores `manifest_content_hash`, SHA-256 of canonical JSON containing every field except `manifest_content_hash` itself. This makes the content hash non-self-referential; it includes `manifest_published_at`. It is distinct from V2 `semantic_hash`.

On retry, the publisher reads the existing owner-assigned directory before sampling a publication time. It reuses the existing `manifest_published_at` solely to recompute the candidate content hash: identical content returns `already_published`; any difference is a conflict. It never replaces an existing file.

## Contract evolution

Extend `DataSnapshotManifest` without changing the meaning of existing protocol/report `data_snapshot_hash` fields:

- `retrieval_date: date | None = None`
- `retrieval_date_status: Literal["verified", "unknown"]`
- `manifest_published_at: datetime`
- `universe_reference_ids: tuple[str, ...] = ()`
- `coverage_disclosure: CoverageDisclosure | None = None`
- `source_manifest_hashes: tuple[tuple[str, str], ...] = ()`, sorted named hashes for the SW2021 membership manifest, SW2021 universe candidate, vendor snapshot manifest, and vendor lifecycle candidate.
- `manifest_content_hash: str`
- `not_authorized_for_b6_oos_gate_promotion_signal: Literal[True] = True`
- `universe_snapshot_ids: tuple[str, ...] = ()` for backward-readable provenance records only.

The validator requires `retrieval_date` if and only if status is `verified`; `unknown` requires `None`. For this V2 manifest, it requires the fixed `gaps` token, one universe reference, a complete coverage disclosure, and the declared semantic hash. It does not permit `universe_reference_ids` to populate or stand in for `universe_snapshot_ids`.

`CoverageDisclosure` is frozen and contains: coverage package ID, coverage manifest SHA-256, expected/complete/unavailable stock-day totals, and a tuple of `(field_name, missing_count)` pairs sorted by field name. It contains no absolute path, raw unavailable detail, or business-data row. `source_manifest_hashes` carries the separately named provenance hashes; it contains hashes only, never source paths.

Existing B6-facing consumers continue to compare `protocol.data_snapshot_hash` / report / Gate hashes to `manifest.semantic_hash`. Those protocol/report field names are not deprecated. Only consumers that read the old manifest attributes `data_snapshot_id` or `data_snapshot_hash` require migration.

## Universe-reference publication

The universe-reference manifest binds:

- `universe_reference_id="uref_traderlens_v2_shsz_sw2021_pit_001"`
- SW2021 membership manifest SHA-256
- SW2021 universe-candidate SHA-256 and its `universe_definition_hash`
- source taxonomy `SW2021`
- `provenance_only=true`
- a non-authorization statement for B6/OOS, Gate, Promotion, Signal, and data collection.

It does not read membership parquet. It does not claim a formal membership snapshot, PIT membership records, or a substitute identity for them. Until a real formal PIT membership snapshot exists, B6 remains unavailable even after formal data-manifest publication.

## Formal data-manifest publication rule

The publisher reads only explicit metadata paths: predecessor qualification manifest, coverage manifest/sidecar, coverage-by-date parquet, the four source metadata files bound by coverage (SW2021 membership manifest, SW2021 universe candidate, vendor snapshot manifest, vendor lifecycle candidate), and the current V2 scope-freeze document. It may use a parquet reader only to read `trade_date`, `expected_codes`, `complete_codes`, and `unavailable_codes` from `coverage_by_date.parquet`.

It must first verify:

1. All manifest and sidecar SHA-256 values match their files.
2. Coverage is `coverage_published`, build completion is `completed`, structural validation passed, structural errors are empty, and arithmetic is exact.
3. The coverage-by-date parquet hash matches its manifest; it contains exactly 2,554 distinct trading dates; its first/last dates are the published `market_data_start`/`market_data_end`; and its aggregates equal coverage expected/complete/unavailable totals.
4. Predecessor, coverage, and availability successor all bind the exact V2 semantic hash, scope hash, requirements hash, and template hash.
5. The universe reference binds the exact membership/universe source hashes recorded by coverage.

It then publishes:

- `snapshot_id="ds_traderlens_v2_shsz_pit_001"`
- `provider="mixed_vendor_tushare"`
- `retrieval_date=None`, `retrieval_date_status="unknown"`
- `market_data_start` and `market_data_end` from the verified coverage aggregate
- `universe_snapshot_ids=()` and `universe_reference_ids=("uref_traderlens_v2_shsz_sw2021_pit_001",)`
- `semantic_hash` equal to the fixed established V2 value
- `quality_status="ok"`, `gaps=("availability_limited",)`, and the structured disclosure
- a true frozen flag and `not_authorized_for_b6_oos_gate_promotion_signal=true`.

The publisher must not read daily, daily_basic, stk_limit, adj_factor, lifecycle, membership, or expected-universe business partitions. It must not generate a `ResearchProtocolSnapshot`, write SQLite, invoke the ledger, or call B4/B6/OOS/Gate/Promotion/Signal.

## Consumer migration boundary

The formal publisher and its verifier use `snapshot_id` and `semantic_hash`. The old `DataSnapshotManifestBuilder` is legacy and is excluded from this path.

`ResearchProtocolFreezer` and `BacktestEngineQualification` have known manifest-field drift and require separate, focused compatibility repairs before any B6 implementation. Their repair must map manifest `semantic_hash` to the unchanged protocol/report `data_snapshot_hash` binding; it must not rename protocol/report fields or broaden execution scope.

## Required verification for implementation

1. RED/GREEN contract tests cover unknown versus verified retrieval dates, coverage disclosure sorting, and rejection of a universe reference used as a universe snapshot ID.
2. Temporary-metadata tests prove manifest publication reads only source manifests plus coverage-by-date `trade_date`; no daily or membership business partition is opened.
3. Mutation tests independently reject every source-manifest hash, coverage sidecar, coverage aggregate hash/count/date/total, universe-reference hash, successor binding, semantic hash, and disclosure mismatch.
4. Publication tests prove same ID plus same content returns `already_published`, while same ID plus different content fails without write.
5. Existing formal and coverage artifact roots are SHA-256 checked unchanged before and after; no parquet is written.
6. Integration tests prove all manifest consumers use `snapshot_id`/`semantic_hash` correctly where they consume a `DataSnapshotManifest`, while protocol/report fields remain unchanged.
7. Tests assert no B6/OOS, ledger, Gate, Promotion, Signal, DB, or network call.

## Authorization status

This design authorizes only a future metadata-publication implementation. The resulting formal manifest remains provenance and coverage evidence. It does not provide a formal PIT membership snapshot, approved template governance, frozen gate/kill criteria, runtime owner, protocol freeze, or B6/OOS authorization. Until every independent gate is verified, status stays `validation_unavailable`.
