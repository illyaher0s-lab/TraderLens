"""B3 Time Consistency Guard - Prevent future information leak in historical validation."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvidenceConflictResult(BaseModel):
    """Evidence conflict detection result (separate from degradation)."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    has_conflict: bool
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class TimeConsistencyCheckResult(BaseModel):
    """
    Time consistency validation result.
    
    Separates:
    - blocking_violations: must fix before protocol freeze
    - warnings: degradation (can proceed with caution)
    - evidence_conflicts: separate from warnings
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    status: Literal["pass", "fail"]
    blocking_violations: tuple[str, ...]
    warnings: tuple[str, ...]


class TimeConsistencyGuard:
    """
    Guard against future information leak in historical validation.
    
    Enforces:
    - Universe snapshot date <= backtest_start
    - Current labels/candidates cannot filter history
    - Financial ann_date <= evaluation_date
    - Evidence run_date <= backtest_start
    - Missing delisted coverage blocks or degrades
    - Unknown daily status degrades
    
    No LLM, no DB write, no auto-repair.
    """
    
    def validate_universe_snapshot(
        self,
        snapshot_date: date,
        backtest_start: date,
        universe_type: str,
        historical_effective_from: date | None = None,
        historical_effective_to: date | None = None,
    ) -> TimeConsistencyCheckResult:
        """
        Validate universe snapshot time consistency.
        
        snapshot_date > backtest_start blocks formal validation.
        """
        if universe_type == "point_in_time_membership" and historical_effective_from is not None:
            if historical_effective_from > backtest_start:
                return TimeConsistencyCheckResult(
                    status="fail",
                    blocking_violations=(
                        f"PIT membership effective_from {historical_effective_from} is after "
                        f"backtest_start {backtest_start}.",
                    ),
                    warnings=(),
                )
            if historical_effective_to is not None and historical_effective_to < backtest_start:
                return TimeConsistencyCheckResult(
                    status="fail",
                    blocking_violations=(
                        f"PIT membership effective_to {historical_effective_to} is before "
                        f"backtest_start {backtest_start}.",
                    ),
                    warnings=(),
                )
            return TimeConsistencyCheckResult(
                status="pass",
                blocking_violations=(),
                warnings=(),
            )

        if snapshot_date > backtest_start:
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    f"Universe snapshot date {snapshot_date} is after backtest_start "
                    f"{backtest_start}. Cannot use future membership for historical validation.",
                ),
                warnings=(),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_filter_timestamp(
        self,
        filter_name: str,
        filter_timestamp: date,
        evaluation_date: date,
    ) -> TimeConsistencyCheckResult:
        """
        Validate filter input timestamp.
        
        filter_timestamp > evaluation_date blocks.
        """
        if filter_timestamp > evaluation_date:
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    f"Filter '{filter_name}' timestamp {filter_timestamp} is after "
                    f"evaluation date {evaluation_date}. Future information leak.",
                ),
                warnings=(),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_universe_source(
        self,
        source_type: str,
        source_snapshot_date: date,
        backtest_start: date,
        historical_effective_from: date | None = None,
        historical_effective_to: date | None = None,
    ) -> TimeConsistencyCheckResult:
        """
        Validate universe source type and timestamp.
        
        Confirmed candidate pool cannot be historical universe.
        source_snapshot_date > backtest_start blocks.
        """
        # Reject confirmed candidate pool
        if "candidate" in source_type.lower():
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    "Confirmed candidate pool cannot be used as formal backtest universe. "
                    "Use historical index membership or sector snapshots.",
                ),
                warnings=(),
            )
        
        # Reject missing source
        if source_type == "missing":
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    "Missing universe source. Cannot fall back to static symbol list.",
                ),
                warnings=(),
            )
        
        if source_type.startswith("B3:") and historical_effective_from is not None:
            if historical_effective_from > backtest_start:
                return TimeConsistencyCheckResult(
                    status="fail",
                    blocking_violations=(
                        f"PIT source effective_from {historical_effective_from} is after "
                        f"backtest_start {backtest_start}.",
                    ),
                    warnings=(),
                )
            if historical_effective_to is not None and historical_effective_to < backtest_start:
                return TimeConsistencyCheckResult(
                    status="fail",
                    blocking_violations=(
                        f"PIT source effective_to {historical_effective_to} is before "
                        f"backtest_start {backtest_start}.",
                    ),
                    warnings=(),
                )
            return TimeConsistencyCheckResult(
                status="pass",
                blocking_violations=(),
                warnings=(),
            )

        # Check timestamp
        if source_snapshot_date > backtest_start:
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    f"Universe source snapshot {source_snapshot_date} is after "
                    f"backtest_start {backtest_start}. Future information leak.",
                ),
                warnings=(),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_financial_filter(
        self,
        ann_date: date,
        evaluation_date: date,
    ) -> TimeConsistencyCheckResult:
        """
        Validate financial filter announcement date.
        
        ann_date > evaluation_date blocks.
        """
        if ann_date > evaluation_date:
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    f"Financial ann_date {ann_date} is after evaluation date "
                    f"{evaluation_date}. Future information leak.",
                ),
                warnings=(),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_delisted_coverage(
        self,
        has_delisted_coverage: bool,
        policy: Literal["strict", "lenient"],
    ) -> TimeConsistencyCheckResult:
        """
        Validate delisted stock coverage.
        
        strict: missing delisted coverage blocks
        lenient: missing delisted coverage degrades
        """
        if not has_delisted_coverage:
            if policy == "strict":
                return TimeConsistencyCheckResult(
                    status="fail",
                    blocking_violations=(
                        "Missing delisted stock coverage. Survivorship bias risk.",
                    ),
                    warnings=(),
                )
            else:  # lenient
                return TimeConsistencyCheckResult(
                    status="pass",
                    blocking_violations=(),
                    warnings=(
                        "Missing delisted stock coverage. Quality degraded.",
                    ),
                )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_daily_status_coverage(
        self,
        has_complete_status: bool,
    ) -> TimeConsistencyCheckResult:
        """
        Validate daily status coverage (ST, suspension, limit).
        
        Incomplete status creates degradation warning.
        """
        if not has_complete_status:
            return TimeConsistencyCheckResult(
                status="pass",
                blocking_violations=(),
                warnings=(
                    "Unknown daily status for some symbols. Quality degraded.",
                ),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def validate_evidence_timestamp(
        self,
        evidence_run_date: date,
        backtest_start: date,
    ) -> TimeConsistencyCheckResult:
        """
        Validate evidence run timestamp.
        
        evidence_run_date > backtest_start cannot clean historical universe.
        """
        if evidence_run_date > backtest_start:
            return TimeConsistencyCheckResult(
                status="fail",
                blocking_violations=(
                    f"Evidence run date {evidence_run_date} is after backtest_start "
                    f"{backtest_start}. Cannot use future evidence for historical validation.",
                ),
                warnings=(),
            )
        
        return TimeConsistencyCheckResult(
            status="pass",
            blocking_violations=(),
            warnings=(),
        )
    
    def check_evidence_conflict(
        self,
        evidence_a: str,
        evidence_b: str,
    ) -> EvidenceConflictResult:
        """
        Check for evidence conflicts.
        
        evidence_conflict is separate from degradation warnings.
        """
        # Simple keyword-based conflict detection
        conflicts = []
        
        if "bullish" in evidence_a.lower() and "bearish" in evidence_b.lower():
            conflicts.append(
                f"Conflict: '{evidence_a}' vs '{evidence_b}' (bullish vs bearish)"
            )
        elif "bearish" in evidence_a.lower() and "bullish" in evidence_b.lower():
            conflicts.append(
                f"Conflict: '{evidence_a}' vs '{evidence_b}' (bearish vs bullish)"
            )
        
        return EvidenceConflictResult(
            has_conflict=len(conflicts) > 0,
            conflicts=tuple(conflicts),
            warnings=(),  # Conflicts are separate, not warnings
        )
