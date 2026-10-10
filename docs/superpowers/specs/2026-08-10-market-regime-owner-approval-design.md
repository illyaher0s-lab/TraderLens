# Market-Regime v1.2 Owner Approval Design

## Objective

Approve the already verified market-regime v1.2 candidate without modifying its qualified YAML bytes or rerunning qualification. The approval must be immutable, independently verifiable, and limited to the v3 manual-trading strategy path.

## Approved evidence

- Candidate config: `backend/config/market_regime_thresholds.yaml`
  - version: `1.2`
  - file SHA-256: `65d4fa29e8a16f5c3e839fda44d26ae3c4c588d08d630a578b84859b32d26cfc`
  - semantic hash: `483c251850f6f6aeea63df059e2f8b8a81992ad71921176ec16ef8ff93918eec`
- Qualification: `be92ad203fc0f2cd`
  - manifest SHA-256: `3a0a4330f517cd758a37de4a4c01e684211e6b6fd41eec9c5845f1639ce8aa9d`
  - validation report SHA-256: `0dbae0397f4878cf4b4ac47af636ecc845403282eec45118ad6f2ac368021d35`
  - source manifest SHA-256: `31ae3b30df723638faf60e90e502ac1e7e32e71db191976601fb4100e22d1ee8`
  - validation semantic hash: `62889a54dde15376acc39fec01579059ab16ec35160755201e4651430be91999`
- Qualification result:
  - `zero_gap=true`
  - stress B blocked days: `1/5`
  - normal blocked days: `0/60`
  - normal block ratio: `0.0`
- Evidence successor: `adcfa06eebc44ceb`
  - manifest SHA-256: `e1f6132b2a818dd2523a0da33fa393cc69b1aed22be1241f741fe4bdfeddaaeb`
- Index successor: `b1208520d9b0c0b0`
  - manifest SHA-256: `efe435a732e60eab316db6d042f22383b051d6a4712e3d289027956adc6ade68`

## Design

Publish one write-once approval artifact under a dedicated market-regime approval directory. Its canonical payload binds every identity and hash above, records `decision=approved`, `authorized_by=illya`, and states that the approval applies only to the exact v1.2 semantics and verified bounded qualification.

The candidate YAML remains byte-for-byte unchanged. Approval is represented by the new artifact rather than by filling the YAML's mutable status fields. This preserves the qualification's exact config-file binding and avoids a second replay.

The approval artifact must not contain strategy execution choices. A later execution-semantics supplement may reference this approval artifact, but approval and executor work remain separate nodes.

## Independent verification

The verifier must independently:

1. Verify the approval manifest sidecar and deterministic artifact ID.
2. Re-read the candidate YAML and recompute its file and semantic hashes.
3. Run the existing independent qualification verifier on `be92ad203fc0f2cd`.
4. Recompute and compare the qualification manifest, validation report, source manifest, evidence successor, and index successor hashes.
5. Require the recorded acceptance facts: zero gaps, at least one blocked stress day, and normal block ratio no greater than `0.05`.
6. Require the exact owner decision and authorization scope.

Any mismatch fails loud. Existing artifacts are never overwritten or repaired in place.

## TDD and acceptance

Focused RED-to-GREEN tests must cover successful publication and independent verification, config or qualification tampering rejection, owner/decision mismatch rejection, and write-once conflict rejection.

Acceptance requires one real publication, one independent verification, unchanged YAML bytes, unchanged database/OOS state, and no downstream workflow execution.

## Scope boundary

This node does not implement the v3 executor, freeze the execution-semantics supplement, run B4/OOS/B6/Gate/Promotion/Signal, modify strategy parameters, call external APIs, or perform Git operations.
