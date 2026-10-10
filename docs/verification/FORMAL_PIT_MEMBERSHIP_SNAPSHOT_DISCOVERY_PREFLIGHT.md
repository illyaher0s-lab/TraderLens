# Formal PIT Membership Snapshot Discovery Preflight

**Status:** formal_pit_membership_snapshot_unavailable  
**Preflight Date:** 2026-07-14  
**Scope:** Read-only discovery, no creation, no data scanning

---

## Executive Summary

**Conclusion:** `formal_pit_membership_snapshot_unavailable`

No formal, immutable `PointInTimeMembershipSnapshot` exists in the repository. The current V2 formal data snapshot manifest uses only a metadata-only universe reference (`uref_traderlens_v2_shsz_sw2021_pit_001`) explicitly marked `provenance_only=true`. B6 validation flow requires a real `PointInTimeMembershipSnapshot` with PIT membership records; the metadata-only reference cannot substitute.

**Status remains:** `validation_unavailable`  
**B6/OOS:** Not authorized (unchanged)

---

## 1. PointInTimeMembershipSnapshot Contract Requirements

### 1.1 Contract Definition

**File:** `backend/services/b3_protocol_types.py` (lines 27-43)

```python
class PointInTimeMembershipSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    snapshot_id: str
    snapshot_date: date
    universe_rule_type: Literal["point_in_time_membership"]
    membership_source: str
    include_delisted: bool
    records: tuple[UniverseMembershipRecord, ...]
    quality_status: Literal["ok", "insufficient", "partial"]
    gaps: tuple[str, ...]
```

**Required fields:**
- `snapshot_id`: unique identity
- `snapshot_date`: PIT effective date
- `universe_rule_type`: must be `"point_in_time_membership"`
- `membership_source`: data source identifier
- `include_delisted`: **must be True** for formal backtest (contract docstring explicit)
- `records`: tuple of `UniverseMembershipRecord` (symbol, effective_from, effective_to, source, snapshot_id)
- `quality_status`: data quality assessment
- `gaps`: detected coverage gaps
- `frozen=True`: immutable (enforced by Pydantic ConfigDict)

### 1.2 B6 Validation Flow Hard Requirement

**File:** `backend/services/b6_validation_flow.py` (lines 69-88)

```python
def run_validation(
    self,
    strategy_draft,
    protocol,
    manifest,
    universe: PointInTimeMembershipSnapshot | None,  # Required
    b4_qualification: dict | None,
    ...
) -> B6ValidationRunResult:
    """
    Args:
        universe: PointInTimeMembershipSnapshot (required)
        ...
    """
    if universe is None:
        raise ValueError("PointInTimeMembershipSnapshot is required for B6 validation flow")
```

**Enforcement:** Hard error if `universe=None`.

### 1.3 BacktestEngineQualification (B4) Hard Requirement

**File:** `backend/services/backtest_engine_qualification.py` (lines 10-40+)

```python
from backend.services.b3_protocol_types import (
    PointInTimeMembershipSnapshot,
    ...
)

def qualify(..., universe_spec):  # PointInTimeMembershipSnapshot
    """
    Args:
        universe_spec: B3 PointInTimeMembershipSnapshot (frozen, required)
    """
    if isinstance(universe_spec, PointInTimeMembershipSnapshot):
        # Accept only PointInTimeMembershipSnapshot (strict type check)
```

**Enforcement:** Strict `isinstance()` check, no duck typing.

---

## 2. Repository Discovery Results

### 2.1 Formal PIT Membership Snapshot Search

**Search performed:**
```bash
find data/pit -name "*membership*snapshot*" -o -name "*pit_membership*"
grep -r "snapshot_id.*membership|membership.*snapshot_id" data/pit/ --include="*.json"
find data/pit -type d -name "*membership*"
```

**Results:**
- **Zero formal PIT membership snapshot artifacts found**
- **Zero registered snapshot IDs in manifests**
- **One staging directory:** `data/pit/tushare/.staging/.../sw_l1_membership/` (not formal)

### 2.2 Metadata-Only Universe Reference

**Path:** `data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/manifest.json`

**Content:**
```json
{
  "universe_reference_id": "uref_traderlens_v2_shsz_sw2021_pit_001",
  "sw2021_membership_manifest_sha256": "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3",
  "sw2021_universe_candidate_sha256": "8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994",
  "universe_definition_hash": "55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc",
  "source_taxonomy": "SW2021",
  "provenance_only": true,
  "not_authorized_for_b6_oos_gate_promotion_signal": true
}
```

**Semantic:**
- `provenance_only: true` — **explicitly not a formal snapshot**
- Purpose: audit trail binding source manifests, not a `PointInTimeMembershipSnapshot.snapshot_id`
- Cannot be passed to B6 `run_validation(universe=...)`
- No `records` field, no `snapshot_date`, no `include_delisted`

### 2.3 Formal Data Snapshot Manifest

**Path:** `data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/manifest.json`

**Universe fields:**
```json
{
  "universe_snapshot_ids": [],
  "universe_reference_ids": ["uref_traderlens_v2_shsz_sw2021_pit_001"]
}
```

**Compliance:**
- ✓ `universe_snapshot_ids` is empty (correct — no formal snapshot exists)
- ✓ `universe_reference_ids` contains only metadata-only reference (correct — not misused as snapshot ID)
- ✓ Design requirement satisfied: metadata-only reference NOT populated into `universe_snapshot_ids`

---

## 3. SW2021 Universe Candidate Analysis

### 3.1 Candidate Status

**Path:** `data/pit/tushare/.staging/.../sw2021_universe_candidate.json`

**Metadata:**
```json
{
  "status": "candidate_universe_ready",
  "checked_trade_days": 2554,
  "universe_definition_hash": "55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc",
  "formal_qualification_run": true
}
```

**Hash binding:**
- Universe definition hash: `55d2ceb6...` ✓ matches universe reference
- Checked trade days: 2,554 ✓ matches coverage manifest
- Formal qualification run: `true`

### 3.2 Why Candidate Cannot Substitute Formal Snapshot

**Missing fields:**
1. **No `snapshot_id`** — identity not assigned
2. **No `snapshot_date`** — PIT effective date undefined
3. **No `records`** — no `tuple[UniverseMembershipRecord, ...]`
4. **No `include_delisted` declaration** — survivorship bias status unknown
5. **No `quality_status` or `gaps`** — data quality undeclared
6. **Status is `candidate_universe_ready`** — staging artifact, not formal frozen snapshot

**Semantic:**
- Candidate evidence = proof that universe definition was qualified
- Not a formal snapshot = not usable by B6/B4 entry points
- Staging path (`.staging/...`) = not immutable formal artifact root

**Design compliance:**
- ✓ Correctly not treated as formal snapshot in data manifest
- ✓ Bound via universe reference for provenance only
- ✓ Not passed to B6 validation flow

---

## 4. Blocking Dependencies

### 4.1 What B6 Requires (Unmet)

**Entry point:** `B6ValidationFlow.run_validation(universe=...)`

**Required input:**
```python
universe: PointInTimeMembershipSnapshot
```

**Must contain:**
- `snapshot_id`: formal identity (not staging path, not package ID, not coverage ID, not semantic hash, not universe reference ID)
- `records`: actual PIT membership records with `symbol`, `effective_from`, `effective_to`, `source`
- `include_delisted=True`: explicit survivorship-bias protection
- `quality_status`: data quality declared
- `frozen=True`: immutable

**Current state:** None of these exist.

### 4.2 What ResearchProtocolFreezer Would Need

**File:** `backend/services/research_protocol_freezer.py`

**Search result:** No `universe.*snapshot_id` usage found in current implementation.

**Inference:** Protocol freezer not yet wired to require universe snapshot (legacy or incomplete).

**Blocker:** Even if protocol freezer accepts None, B6 validation flow hard-rejects None.

### 4.3 Unavailable vs. Unimplemented

**Candidate universe JSON exists** → Data collection complete  
**Formal snapshot artifact missing** → Snapshot publication not implemented  
**B6 hard-requires snapshot** → B6 cannot run until formal snapshot created

**Nature of gap:** Implementation gap, not data gap.

---

## 5. Verification Checklist

### 5.1 Contract Compliance

- ✓ `PointInTimeMembershipSnapshot` contract defined in `b3_protocol_types.py`
- ✓ B6 validation flow enforces `universe` parameter required
- ✓ B4 qualification enforces `isinstance(universe_spec, PointInTimeMembershipSnapshot)`
- ✓ Contract requires `include_delisted=True` for formal backtest (docstring)
- ✓ Contract requires `frozen=True` (Pydantic ConfigDict)

### 5.2 Repository State

- ✓ Zero formal PIT membership snapshot artifacts found
- ✓ Metadata-only universe reference correctly marked `provenance_only=true`
- ✓ Formal data snapshot manifest correctly uses empty `universe_snapshot_ids`
- ✓ Universe reference ID not misused as snapshot ID
- ✓ Candidate universe evidence exists but staging only

### 5.3 Design Compliance

- ✓ Metadata-only reference not passed to B6 (correct)
- ✓ Candidate not treated as formal snapshot (correct)
- ✓ No staging IDs used as formal identities (correct)
- ✓ No coverage masks misrepresented as membership (correct)
- ✓ No survivorship-biased current constituents used (correct)

### 5.4 Data Scanning

- ✓ **No membership parquet read** (manifest metadata only)
- ✓ **No business data scanned** (JSON metadata only)
- ✓ **No partition enumeration** (directory listing only)

### 5.5 Modifications

- **One file created:** `docs/verification/FORMAL_PIT_MEMBERSHIP_SNAPSHOT_DISCOVERY_PREFLIGHT.md` (this report)
- **Zero files modified**
- **Zero artifacts created**
- **Zero data补洞**

---

## 6. Minimum Non-Substitutable Missing Evidence

**To enable B6 validation:**

1. **Formal PIT membership snapshot artifact** with:
   - Owner-assigned `snapshot_id` (not derived from hash/path)
   - Explicit `snapshot_date` (PIT effective date)
   - Populated `records: tuple[UniverseMembershipRecord, ...]`
   - `include_delisted=True`
   - `quality_status` and `gaps` declared
   - Independent content hash and sidecar
   - Immutable publication in `data/pit/pit_membership_snapshots/` or equivalent formal root

2. **Binding to V2 formal data snapshot:**
   - Formal snapshot `snapshot_id` populated into `DataSnapshotManifest.universe_snapshot_ids`
   - Cross-validation with universe reference provenance
   - No conflict with SW2021 membership manifest hash, universe definition hash, scope/template/snapshot binding

3. **B6 entry point wiring:**
   - `B6ValidationFlow.run_validation(universe=<formal_snapshot>)` callable
   - ResearchProtocolFreezer binding (if required)
   - No reliance on candidate staging artifacts

**Cannot be substituted by:**
- ✗ Metadata-only universe reference
- ✗ Candidate universe JSON
- ✗ Coverage expected universe
- ✗ Current SW2021 constituents
- ✗ Inferred membership from availability mask
- ✗ Universe definition hash alone

---

## 7. Final Status

**Discovery result:** `formal_pit_membership_snapshot_unavailable`

**Current workflow status:** `validation_unavailable` (unchanged)

**Authorization status:** Not authorized for B6/OOS, Gate, Promotion, Signal (unchanged)

**Blocking condition:** No formal `PointInTimeMembershipSnapshot` exists. B6 validation flow cannot execute without one.

**Design compliance:** V2 formal data snapshot manifest and universe reference correctly implement metadata-only provenance. No misuse or workaround detected.

**Data integrity:** Candidate universe evidence exists and is properly bound via provenance reference. No data loss or corruption. Implementation gap, not data gap.

**Next action:** Formal PIT membership snapshot publication requires independent design and implementation task, outside scope of this preflight.

---

**Report end.**
