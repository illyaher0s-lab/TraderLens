# B6 Protocol Freeze Contract-Binding Design

**Status:** Owner-approved design. Current workflow status remains `validation_unavailable`.

**Scope:** Define the smallest safe B6 coverage-bound protocol-freeze boundary. This design does not implement code, create a qualification result or data manifest, publish a coverage artifact, configure a runtime owner, execute or view OOS, or invoke Gate, Promotion, or Signal.

## Decision

Add a separate B6-only entry, `freeze_b6_coverage_bound_protocol()`. Keep the existing generic `freeze_protocol()` as a legacy B3 compatibility path. B6 execution must accept only a `ResearchProtocolSnapshot` whose `protocol_profile` is `"b6_coverage_bound"`; `legacy_b3` is never B6 admission evidence.

The B6 entry returns either a frozen protocol snapshot or a non-persistent `ProtocolFreezePreflightResult`. Expected missing or unavailable prerequisites return the latter. Artifact corruption, a false hash claim, or an internal invariant violation fails loudly.

```text
immutable inputs + shared durable ledger (read only)
                    |
                    v
        B6 coverage-bound preflight
          | unavailable          | all checks pass
          v                      v
ProtocolFreezePreflightResult  ResearchProtocolSnapshot
  (never persisted)              (caller may append once)
```

## Current boundary

The current qualification package `de3fed9c3819d25c` is immutably `not_qualified`; the canonical coverage package `695245b51005e50b` is bound to its manifest. The raw pair cannot create or store a protocol.

The approved successor path is a separate immutable metadata artifact with status `availability_bounded_qualified`. It binds the raw predecessor qualification, the canonical coverage package, and the scope-freeze hash without changing either old artifact or rescanning business data. The successor is qualification evidence only, not B6 authorization. Until it exists, preflight returns `validation_unavailable`.

## Non-persistent unavailable result

Define a frozen `ProtocolFreezePreflightResult` with:

- `status: Literal["validation_unavailable"]`
- `reason_code`: one closed value from:
  `availability_qualification_unavailable`, `availability_successor_binding_invalid`,
  `snapshot_manifest_unavailable`,
  `template_not_approved`, `template_binding_mismatch`,
  `artifact_binding_mismatch`, `criteria_reference_unavailable`,
  `criteria_content_hash_mismatch`, `criteria_envelope_hash_mismatch`,
  `ledger_owner_unavailable`, `ledger_active_reservation`,
  `ledger_budget_exhausted`, `split_or_time_consistency_invalid`
- `detail: str | None` for diagnostics only; callers must never route on it.

This type is not accepted by `StrategyDB.store_protocol_snapshot()` and contains no protocol ID. It is the only normal return for unavailable prerequisites. It never reserves or consumes a draw.

## B6 input contract and hard gates

`freeze_b6_coverage_bound_protocol()` receives explicit keyword-only inputs: the draft, approved frozen template definition, universe, formal `DataSnapshotManifest`, registered OOS window, qualification and coverage package locations, frozen gate and kill references, a DB-backed ledger, `frozen_by`, and `backtest_start`.

It evaluates these gates in order and short-circuits on the first unavailable condition:

1. **Availability-bounded qualification.** A separately verified successor has status exactly `availability_bounded_qualified`. Its ID, manifest hash, predecessor qualification ID/hash/status, scope-freeze document hash, and canonical coverage ID/hash all validate. The raw predecessor is never relabeled `formal_qualified`.
2. **Formal snapshot.** A discoverable `DataSnapshotManifest` exists. Its owner-assigned `snapshot_id` is non-empty and its `semantic_hash` equals both qualification `snapshot_hash` and coverage `input_snapshot_hash`. `snapshot_hash`, a package ID, and a staging-directory name never substitute for `snapshot_id`. A metadata-only `universe_reference_id` is provenance only; it never substitutes for the formal PIT membership snapshot required by B6.
3. **Approved template governance.** The caller supplies a frozen `StrategyTemplateDefinition` with `governance_status == "approved"`. Its template ID, version, and hash must each equal the draft, qualification manifest, and coverage manifest values. Missing version evidence is unavailable, not inferred from an ID or filename.
4. **Artifact binding.** Recompute each manifest's SHA-256 from bytes; verify the coverage detached sidecar; then require template, requirements, scope, predecessor qualification, successor, snapshot, and algorithm bindings to agree. Require coverage structural validation to pass and `complete + unavailable == expected`, reading all totals from the coverage manifest rather than source constants.
5. **Frozen criteria.** Both gate and kill references have non-empty snapshot IDs, non-empty canonical JSON content, and declared content hashes. `{}`, empty values, defaults, and runtime-generated values are unavailable.
6. **Read-only durable budget projection.** The ledger is DB-backed by the future execution owner, not `:memory:`. One `get_ledger_state()` call must report `available`, no active reservation, and remaining budget.
7. **Existing safety checks.** The OOS rule is registered and the existing universe/time-consistency checks pass.

No gate may be relaxed because another gate passed.

## Criteria hashing

The freezer independently canonicalizes each criteria JSON value by parsing it, requiring a non-empty object, then serializing with sorted keys and compact separators. It computes each SHA-256 from that canonical serialization and compares it with the reference's declared content hash. Raw JSON bytes and caller-provided hashes are not trusted.

Only after both content hashes match does the freezer compute `gate_criteria_hash` as SHA-256 of this canonical envelope:

```json
{"gate_content_hash":"...","gate_snapshot_id":"...","kill_content_hash":"...","kill_snapshot_id":"..."}
```

The computed envelope hash must equal the supplied `gate_criteria_hash`. This exact computed hash is stored in the protocol. The protocol also stores both snapshot IDs and both recomputed content hashes.

## Frozen protocol shape and identity

Extend `ResearchProtocolSnapshot` with a profile discriminator defaulting to `legacy_b3`, plus optional B6 binding fields for legacy reads:

- `protocol_profile: Literal["legacy_b3", "b6_coverage_bound"]`
- availability-qualification successor ID, manifest hash, and algorithm hash
- predecessor qualification package ID, manifest hash, status, and algorithm hash
- coverage package ID, manifest hash, and algorithm hash
- `source_scope_hash`, `data_requirements_hash`
- `expected_stock_days`, `complete_stock_days`, `unavailable_stock_days`
- gate snapshot ID/content hash and kill content hash (the existing kill snapshot ID remains the kill ID)

A model validator requires every B6 field, non-placeholder criteria values, and coverage arithmetic when `protocol_profile == "b6_coverage_bound"`. Legacy snapshots remain readable but cannot claim the B6 profile.

The B6 protocol ID is SHA-256 of canonical JSON containing the profile, draft revision, universe identity, snapshot ID and semantic hash, all artifact bindings, recomputed criteria envelope hash, and registered split/OOS-window values. It excludes `frozen_at`, `frozen_by`, absolute paths, temporary names, and physical database paths. The legacy ID algorithm remains unchanged.

## Composition-root invariant

A future composition root owns the configured, file-backed `StrategyDB` and constructs the DB-backed `OOSBudgetLedger` used by both the B6 freeze entry and the later execution entry. Freeze rejects `:memory:` and an owner/ledger mismatch.

The future execution entry must prove in an integration test that it resolves its ledger from the same configured database identity as freeze, then revalidates bindings and atomically reserves its draw. Database identity is runtime-only; no physical path or machine-specific value enters protocol fields or semantic hashes.

Freeze calls only `get_ledger_state()`. It performs no state, reservation, audit, or protocol-DB write. A successful freezer return is still only an in-memory snapshot; the separate caller-controlled append boundary may store it once. Any preflight failure leaves protocol, state, reservation, and audit row counts unchanged.

## Explicit exclusions and related work

- No data collection, expected-universe change, data-hole filling, coverage scan, or modification of any existing formal/coverage artifact.
- No runtime API/composition-root implementation, B6/OOS execution, result viewing, Gate, Promotion, or Signal.
- Producing the immutable `availability_bounded_qualified` successor and publishing a formal discoverable `DataSnapshotManifest` are separate upstream tasks. This design specifies only their required input interface and rejection behavior. The successor must not scan or rewrite PIT data.
- `backtest_engine_qualification.py` still reads the migrated-away `manifest.data_snapshot_hash` field. Its alignment to `manifest.semantic_hash` is a separate contract-drift repair; this design does not treat it as resolved.

## Required verification for a later implementation

1. Focused RED/GREEN tests cover every reason code and assert zero protocol, ledger, reservation, and audit writes on every unavailable branch.
2. Tests mutate one template ID/version/hash, qualification binding, coverage binding, detached hash, criteria value, criteria declared hash, or envelope hash at a time and prove rejection.
3. Tests prove the freezer recomputes canonical criteria hashes despite equivalent JSON key order and rejects byte-different semantic content.
4. A positive test uses only a new, `availability_bounded_qualified`, fully cross-bound successor plus the unchanged predecessor and canonical coverage artifacts; it verifies immutable snapshot store/read round-trip and deterministic B6 protocol identity.
5. A real file-backed temporary DB integration test proves freeze and future execution obtain their ledger through the same composition-root configuration. A separate connection verifies no freeze writes; execution reservation remains a later, separately authorized test boundary.
6. B6 entry tests reject `legacy_b3` before report construction and assert report/OOS/Gate/Promotion/Signal doubles receive zero calls.
7. All V2 canonical and invalid artifact paths are pre/post content-hash checked unchanged.

## Authorization status

This design is an admission-boundary specification, not execution authority. Until the availability-bounded successor, formal data manifest, approved template governance, real criteria references, and shared runtime owner all exist and pass their own verification, the only permitted outcome is `validation_unavailable`.
