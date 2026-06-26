# TraderLens Project Memory

## Architecture
- Three modules: A (Selection Research), B (Strategy Validation), C (Action Plan)
- Module A entry: `/themes`, Module B/C entry: `status.md`
- `ProposedAction → reducer → DB → Research Board` is the only state write path
- Analysis routes (run_serenity, run_evidence) do NOT increment board_version

## Key Conventions
- Contracts live in `contracts/research.py` (Pydantic BaseModel)
- Research DB in `backend/db/research.py` (SQLite)
- Validation in `backend/services/research_validation.py`
- Evidence runner in `backend/services/evidence_light.py`
- API in `backend/api/research.py`
- All tests must work offline with FakeTushareClient / FakeLLM

## Hard-Filter Rules (Deterministic)
- HardFilterSnapshot: is_listed, is_st, is_suspended, avg_daily_volume — all bool|None or float|None
- None = "unknown/unavailable" = BLOCKS (not a pass)
- validate_candidate produces: unknown_listing_status, unknown_st_status, unknown_suspension_status, unknown_liquidity
- 数据缺失绝不默认通过
- Gaps recorded in HardFilterSnapshot.gaps and copied to EvidenceOutput.evidence_gaps

## Trust Chain
- verify_ticker() generates verification_id with 24h expiry
- CandidateStock.verification_id = original verification reference
- Evidence API reads candidate.verification_id, rejects missing/expired/mismatched
- Evidence never silently re-verifies — uses candidate's original verification_id
- ConfirmedCandidate freezes verification_id at confirmation time

## EvidenceItem Source Identity (2026-06-24)
- source_type: announcement|financial_report|prospectus|interaction_platform|news|social_media|unknown
- source_quality: first_hand|second_hand|weak
- Defaults: source_type="unknown", source_quality="weak" (conservative)
- supports/falsifies/conflicts: list[str] linking to specific theses
- DB uses model_dump(mode='json') for serialization — full round-trip
- evidence_light injection paths accept new fields via .get(... defaults)

## DataTools (2026-06-24)
- Unified contract: DataToolResult(tool_name, raw_data, source, retrieved_at, gaps, errors)
- DataToolsService in backend/services/data_tools.py
- get_financials(symbol) — Tushare income API, 4 quarters, per-field gap tracking
- Missing fields NOT filled with defaults; absent from raw_data dict entirely
- FakeTushareClient supports income + anns + stock_basic(industry) APIs
- Invariant: empty raw_data MUST have gap or error

## Evidence Quality Rules (2026-06-24)
- EvidenceQualityValidator in backend/services/evidence_quality.py
- Deterministic source mapping: tushare → first_hand, news → second_hand, social → weak
- Rules: no-source→block, all-weak→block, weak→capped, expired→gap, conflict→block
- must have support chain AND counter-evidence chain for confirmation
- can_auto_confirm = has_support AND no-blocking-reasons
- EvidenceLightRunner integration: quality runs after evidence injection

## Evidence Agent (2026-06-24)
- EvidenceDataPacket: immutable aggregation of 3 tool results + symbol/verification_id/snapshot
- EvidenceAgentAudit: model, provider, input_hash, tool_calls, token_usage, errors
- EvidenceAgentOrchestrator: calls 3 tools → builds packet → LLM extraction → rebind → validate
- Input blob sanitized: no raw financial numbers leaked to LLM
- LLM output restricted: description, supports, falsifies, conflicts, summary only
- source_type/source_quality always rebind after LLM (LLM values never trusted)
- FakeLLM enables offline testing
- EvidenceItem.source_record_id links each item to tool_name:row_index
- _verify_facts: rejects fabricated numbers, tickers, company names, wrong row indices
- tool_gaps items only accepted when actual gaps exist in the packet

## Evidence Snapshot Chain (2026-06-24)
- evidence_snapshots table: immutable, append-only, stores full EvidenceOutput + hashes
- ConfirmedCandidate: evidence_snapshot_ids + primary_evidence_snapshot_id
- Reducer confirmation gate: snapshot existence, candidate/symbol match, no blocking issues
- At least one valid snapshot required; confirmation freezes all references

## A 模块 Vertical Flow (2026-06-24)
- Gate checks: verification_id consistency between snapshot and candidate
- Hash integrity: packet_data recomputed hash must match stored hash
- 9 E2E tests: theme→verify→add→hard-filter→evidence→snapshot→confirm→pool
- A 模块 output verified clean: no entry_price/stop_loss/position_pct/buy_tomorrow

## Serenity Agent (SMA-P2)
- SerenityAgentRunner in backend/services/serenity_agent.py
- Goal-driven tool-use: no fixed pipeline
- Tools: read_theme, verify_ticker, propose_add_candidate
- 产业链逆向拆解 + 玩家审计 + red-team证伪
- Falls back to SerenityStubRunner when no LLM client
- Banned: trading advice, direct state writes, fabricating tickers

## Serenity Tools (SMA-P2 extension, 2026-06-24)
- ResearchSource + SerenityToolResult contracts in contracts/research.py
- SerenityTools in backend/services/serenity_tools.py
  - retrieve_supply_chain: theme→infer symbols→financials/anns/sector→ResearchSource records
  - discover_players: extract tickers from records→verify_ticker gate→verified only
  - audit_sources: source quality (all-weak/expired/no first_hand/insufficient players)
  - red_team_falsify: gap→falsification, sector/peer gaps→counter-argument warnings
- Anti-injection: external text cannot modify system prompt, tool whitelist, or execution path
- SerenityAgentRunner updated: 7 tools registered (3 core + 4 research)

## Test Suite
- Full: 754 tests OK, 2 skipped (data-dependent, not bugs)
