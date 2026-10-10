# Market-Regime v1.2 Owner Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish and independently verify one immutable owner-approval artifact for the exact verified market-regime v1.2 candidate.

**Architecture:** Keep the qualified YAML and qualification artifacts byte-for-byte unchanged. A new canonical approval manifest binds their exact IDs and hashes plus the explicit owner decision; a separate verifier revalidates every referenced source and acceptance condition.

**Tech Stack:** Python 3.12, pathlib, hashlib/json, pytest, existing market-regime qualification verifier.

**Execution constraint:** Do not perform Git operations. Existing dirty work and immutable artifacts are user-owned.

---

### Task 1: Approval publisher and independent verifier

**Files:**
- Create: `scripts/publish_market_regime_v12_owner_approval.py`
- Create: `scripts/verify_market_regime_v12_owner_approval.py`
- Create: `tests/test_market_regime_v12_owner_approval.py`

- [ ] **Step 1: Write the focused failing tests**

Cover the real publisher/verifier boundary with temporary output only:

```python
def test_publish_and_verify_exact_v12_owner_approval(tmp_path):
    published = publish_owner_approval(output_root=tmp_path)
    assert published["status"] == "published"
    verified = verify_owner_approval(Path(published["path"]))
    assert verified["status"] == "verified"

def test_config_or_qualification_tamper_is_rejected(tmp_path):
    published = publish_owner_approval(output_root=tmp_path / "approval")
    copied_config = tmp_path / "market_regime_thresholds.yaml"
    copied_config.write_bytes(CONFIG_PATH.read_bytes() + b"\n# tampered\n")
    with pytest.raises(ValueError, match="config.*hash"):
        verify_owner_approval(Path(published["path"]), config_path=copied_config)

def test_owner_or_decision_mismatch_is_rejected(tmp_path):
    published = publish_owner_approval(output_root=tmp_path / "approval")
    manifest_path = Path(published["path"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authorized_by"] = "different-owner"
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    manifest["artifact_id"] = sha256(canonical(payload)).hexdigest()[:16]
    manifest_path.write_bytes(canonical(manifest))
    write_sidecar(manifest_path)
    with pytest.raises(ValueError, match="owner|authorization"):
        verify_owner_approval(Path(published["path"]))

def test_write_once_conflict_is_rejected(tmp_path):
    first = publish_owner_approval(output_root=tmp_path / "approval")
    manifest_path = Path(first["path"]) / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="write-once|sidecar"):
        publish_owner_approval(output_root=tmp_path / "approval")
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_market_regime_v12_owner_approval.py -q
```

Expected: non-zero exit because the publisher/verifier modules do not exist.

- [ ] **Step 3: Implement the minimal canonical publisher**

Use constants for the already approved exact evidence. The payload must contain no execution semantics:

```python
payload = {
    "schema_version": "market_regime_v12_owner_approval.v1",
    "status": "approved",
    "decision": "approved",
    "authorized_by": "illya",
    "authorization_scope": "v3_manual_trading_market_regime_only",
    "config": {
        "path": "backend/config/market_regime_thresholds.yaml",
        "version": "1.2",
        "sha256": CONFIG_SHA256,
        "semantic_hash": CONFIG_SEMANTIC_HASH,
    },
    "qualification": {
        "artifact_id": QUALIFICATION_ID,
        "manifest_sha256": QUALIFICATION_MANIFEST_SHA256,
        "validation_report_sha256": VALIDATION_REPORT_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "validation_semantic_hash": VALIDATION_SEMANTIC_HASH,
    },
    "evidence": {
        "artifact_id": EVIDENCE_ID,
        "manifest_sha256": EVIDENCE_MANIFEST_SHA256,
    },
    "index_source": {
        "artifact_id": INDEX_ID,
        "manifest_sha256": INDEX_MANIFEST_SHA256,
    },
    "acceptance": {
        "zero_gap": True,
        "stress_window_block_day_min": 1,
        "normal_window_block_ratio_max": 0.05,
    },
}
artifact_id = sha256(canonical(payload)).hexdigest()[:16]
```

For the exact payload above, the recomputed ID is `6170c11c8068f407`. Write `manifest.json` and `manifest.json.sha256` once under `data/pit/market_regime_owner_approvals/6170c11c8068f407/`. The implementation must still recompute the ID rather than hardcode it. If the directory already exists, accept only byte-identical valid content; otherwise raise a write-once conflict.

- [ ] **Step 4: Implement the independent verifier**

The verifier must:

```python
verify_sidecar(manifest_path)
assert recompute_artifact_id(payload) == manifest["artifact_id"]
assert sha_file(config_path) == manifest["config"]["sha256"]
assert load_config(config_path)[1] == manifest["config"]["semantic_hash"]
qualification = verify_bounded_qualification_independently(qualification_dir)
assert qualification["artifact_id"] == manifest["qualification"]["artifact_id"]
assert sha_file(qualification_dir / "manifest.json") == manifest["qualification"]["manifest_sha256"]
assert sha_file(qualification_dir / "validation_report.json") == manifest["qualification"]["validation_report_sha256"]
assert sha_file(qualification_dir / "source_manifest.json") == manifest["qualification"]["source_manifest_sha256"]
assert decision == "approved" and authorized_by == "illya"
```

It must also read the validation report and require `zero_gap=true`, stress B blocked days at least `1`, and normal block ratio at most `0.05`. Recompute the evidence and index manifest hashes from disk. Fail loud on any mismatch.

- [ ] **Step 5: Run GREEN and focused compatibility**

Run separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_market_regime_v12_owner_approval.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_market_regime_bounded_replay.py -q
```

Expected: both commands exit `0`; report exact pass counts and warnings.

### Task 2: Publish once and stop at the approval boundary

**Files:**
- Create: `data/pit/market_regime_owner_approvals/6170c11c8068f407/manifest.json`
- Create: `data/pit/market_regime_owner_approvals/6170c11c8068f407/manifest.json.sha256`

- [ ] **Step 1: Record immutable baselines**

Read and record the YAML SHA, qualification/evidence/index manifest hashes, and the counts of `research_protocol_snapshots`, `b6_validation_tasks`, `oos_budget_reservations`, `oos_budget_state`, and `oos_evaluation_ledgers`.

- [ ] **Step 2: Publish exactly once**

Run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.publish_market_regime_v12_owner_approval
```

Expected: exit `0`, `status=published`, and one new artifact ID/path.

- [ ] **Step 3: Independently verify exactly once**

Run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_market_regime_v12_owner_approval D:\Codex\TraderLens\data\pit\market_regime_owner_approvals\6170c11c8068f407
```

Expected: exit `0`, `status=verified`, exact owner/config/qualification bindings, and all acceptance conditions true.

- [ ] **Step 4: Confirm stop boundary**

Recompute the YAML and predecessor hashes and confirm they are unchanged. Confirm database/OOS counts are unchanged and OOS was not read, reserved, or consumed. Do not run one-shot, executor, B4, B6 task, Gate, Promotion, or Signal.
