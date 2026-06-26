# M3 Planning Discussion

**Status**: Planning Phase  
**Last Updated**: 2026-06-22  
**Prerequisites**: M2 CLOSED ✅

---

## M2 → M3 Transition

**M2 Achievement** (CLOSED 2026-06-22):
- 299 tests (+85 from M1 baseline, 39.7% growth)
- Contracts stability established (25 stable, 11 draft)
- Data Source Protocol frozen (8 methods)
- Task Execution boundaries defined (16 fields, 5 states)

**M2 Deliverables**:
- Stable contracts (schema version 1.0)
- CSV schema locked (4 files)
- DataSource Protocol (fail-loud, frozen snapshot)
- TaskRecord schema (state machine documented)

---

## M3 Scope Options (NOT Decided Yet)

M3 planning is **open for discussion**. The following are **options**, not commitments.

### Option A: Async Execution First

**Focus**: Implement async task queue and worker infrastructure.

**Scope**:
- Task queue (Redis or in-memory)
- Worker process (background execution)
- Progress streaming (WebSocket or polling)
- Task retry logic
- Task dependencies (optional)

**Value**:
- Enables long-running operations without blocking
- Better user experience (responsive UI)
- Foundation for future parallelism

**Risk**:
- Infrastructure complexity
- No immediate user-facing value (if Web UI not ready)
- May over-engineer before need is proven

---

### Option B: Real Data Integration First

**Focus**: Integrate Tushare/AKShare for real market data.

**Scope**:
- Data fetching (Tushare/AKShare API)
- DataWarehouse abstraction (fetch → store → serve)
- Data validation (detect bad data)
- Snapshot management (fixed data for backtests)
- Cache invalidation

**Value**:
- Enables real strategy testing (not just mock data)
- Validates backtest engine on real scenarios
- Unblocks user adoption

**Risk**:
- API rate limits and reliability
- Data quality issues
- Storage and caching complexity

---

### Option C: Evidence Agent First

**Focus**: Implement Evidence module for research automation.

**Scope**:
- Evidence task type
- Research workflow (hypothesis → evidence → kill criteria)
- Evidence storage and retrieval
- Integration with backtest pipeline

**Value**:
- Differentiator (automated research assistant)
- High-value feature for users
- Validates LLM integration patterns

**Risk**:
- LLM cost and latency
- Evidence quality validation
- Complex workflow coordination

---

### Option D: Signal Board First

**Focus**: Build live signal monitoring dashboard.

**Scope**:
- Signal generation (live mode)
- Signal Board UI (real-time display)
- Signal history and tracking
- Alert/notification system

**Value**:
- Real-time value for users
- Validates live execution readiness
- User engagement and feedback

**Risk**:
- Requires real data integration (depends on Option B)
- UI complexity
- Real-time infrastructure needs

---

### Option E: Incremental Refinement

**Focus**: Improve M2 deliverables without new features.

**Scope**:
- Performance optimization (backtest speed)
- More validation rules (data quality)
- Better error messages
- Documentation improvements
- Bug fixes and stability

**Value**:
- Low risk, high stability
- Better foundation before new features
- User feedback on existing features

**Risk**:
- Low user-visible progress
- May delay differentiation
- Risk of perfectionism paralysis

---

## M3 Minimum Viable Scope (To Discuss)

What is the **smallest M3** that delivers user value?

### Proposal: M3-Minimal = Real Data + Basic Evidence

**Rationale**:
- Real data unblocks real strategy testing
- Evidence provides differentiation
- No async queue (keep sync for now)
- No Signal Board (not needed for backtest workflow)

**Scope**:
- Real data fetching (Tushare/AKShare)
- Fixed snapshot management
- Evidence task type (basic implementation)
- Evidence storage (simple file-based)

**Deferred to M4**:
- Async task queue
- Signal Board
- Live execution
- Advanced Evidence workflows

---

## Open Questions for M3

1. **What is the primary user pain point M3 should solve?**
   - Lack of real data?
   - Manual research process?
   - Slow backtest execution?
   - Lack of live monitoring?

2. **What is M3 success criteria?**
   - "User can run real strategy on real data"?
   - "Evidence Agent automates 80% of research work"?
   - "10+ strategies run in parallel without blocking"?

3. **What is M3 timeline expectation?**
   - 1 month (incremental)?
   - 3 months (new feature)?
   - 6 months (major capability)?

4. **What is M3 NOT scope?**
   - Explicitly list what M3 will NOT do
   - Avoid scope creep

5. **What blockers exist for M3 options?**
   - Option A (Async): Web UI not ready, no immediate value
   - Option B (Real Data): API limits, data quality
   - Option C (Evidence): LLM cost, workflow complexity
   - Option D (Signal Board): Depends on real data + UI
   - Option E (Refinement): Low user-visible progress

---

## M3 Decision Framework (Suggested)

**Step 1: User Feedback**
- What do current/potential users need most?
- What blockers prevent adoption?

**Step 2: Value vs. Risk**
- Rank options by: User Value (High/Med/Low) × Implementation Risk (Low/Med/High)
- Prefer High Value + Low Risk

**Step 3: Sequential vs. Parallel**
- Can options be done in parallel (e.g., Real Data + Evidence)?
- Or must they be sequential (e.g., Real Data → Signal Board)?

**Step 4: M3 Commitment**
- Pick 1-2 options for M3
- Explicitly defer others to M4+
- Write M3 boundary doc (like M2 Boundary Discussion)

---

## Next Steps (Planning Phase)

1. **Gather user feedback** (if users exist)
   - Survey or interviews
   - Identify top pain points

2. **Estimate effort** for each option
   - Quick estimate (1 week, 1 month, 3 months)
   - Identify technical unknowns

3. **Draft M3 Boundary Discussion**
   - Similar to `M2-BOUNDARY-DISCUSSION.md`
   - Define M3 scope, deferred items, out of scope

4. **Decide M3 scope**
   - Write `M3-SCOPE.md` with commitment

5. **Start M3 execution** (after scope is locked)

---

## M3 Constraints (Inherited from M2)

**Must Preserve**:
- M2 contracts remain stable (no breaking changes)
- CSV schema remains locked (column order fixed)
- DataSource Protocol remains frozen (fail-loud, frozen snapshot)
- TaskRecord schema remains stable (state machine unchanged)

**Can Extend**:
- Add new contracts (Evidence, Serenity, Signal Board)
- Add new task types (evidence, serenity)
- Add new data sources (Tushare, AKShare)
- Implement async execution (without breaking sync API)

**Cannot Break**:
- M2 test suite must continue to pass (299 tests)
- M2 documentation remains accurate
- Backward compatibility with M2 exports

---

## Conclusion

M3 planning is **open**. No decisions have been made yet.

**Action Required**:
1. Discuss M3 options with stakeholders
2. Decide M3 minimum viable scope
3. Write M3 boundary discussion doc
4. Lock M3 scope before execution

**M2 is CLOSED**. M3 planning begins now.
