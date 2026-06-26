"""B3 Point-in-Time Universe Builder - Deterministic universe construction from BacktestUniverseSpec."""
from __future__ import annotations

from datetime import date

from backend.services.b3_protocol_types import (
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)
from contracts.strategy import BacktestUniverseSpec, ForwardWatchlistSnapshot


class InMemoryMembershipSource:
    """
    Deterministic in-memory membership source for testing and prototyping.
    
    Provides membership records with effective date windows.
    Does NOT allow current membership to backfill history.
    """
    
    def __init__(
        self,
        records: tuple[UniverseMembershipRecord, ...],
        source_snapshot_date: date,
    ):
        """
        Args:
            records: Membership records with effective_from/to windows
            source_snapshot_date: When this membership snapshot was taken
                                  (must be <= backtest_start for formal backtest)
        """
        self.records = records
        self.source_snapshot_date = source_snapshot_date
    
    def records_for_universe(
        self,
        universe_spec: BacktestUniverseSpec,
        backtest_start: date,
        backtest_end: date,
    ) -> tuple[UniverseMembershipRecord, ...]:
        """
        Filter records to those valid during [backtest_start, backtest_end].
        
        Inclusion rule:
            record.effective_from <= backtest_end
            AND
            (record.effective_to is None OR record.effective_to >= backtest_start)
        
        This ensures:
        - Stock listed after backtest_end: excluded
        - Stock delisted before backtest_start: excluded
        - Stock listed/delisted during backtest: included
        - Stock still trading (effective_to=None): included if listed before backtest_end
        """
        # Check backfill protection
        if self.source_snapshot_date > backtest_start:
            raise ValueError(
                f"Membership source snapshot date {self.source_snapshot_date} "
                f"is after backtest_start {backtest_start}. "
                f"Cannot use current membership to backfill history (future information leak)."
            )
        
        filtered = []
        for record in self.records:
            # Record must start before or during backtest period
            if record.effective_from > backtest_end:
                continue
            
            # Record must not end before backtest period
            if record.effective_to is not None and record.effective_to < backtest_start:
                continue
            
            filtered.append(record)
        
        return tuple(filtered)


class PointInTimeUniverseBuilder:
    """
    Build point-in-time universe from BacktestUniverseSpec.
    
    Deterministic, no LLM calls.
    Enforces:
    - Only BacktestUniverseSpec accepted
    - ForwardWatchlistSnapshot rejected
    - Plain symbol list rejected
    - Confirmed candidate pool rejected
    - Membership requires effective_from/to
    - Delisted stocks included if valid during period
    - Current membership cannot backfill history
    """
    
    def __init__(self, membership_source: InMemoryMembershipSource | None = None):
        """
        Args:
            membership_source: Deterministic membership source with effective date windows.
                               If None, formal builds will fail with insufficient status.
        """
        self.membership_source = membership_source
    
    def build_membership_snapshot(
        self,
        universe_spec: BacktestUniverseSpec,
        backtest_start: date,
        backtest_end: date | None = None,
    ) -> PointInTimeMembershipSnapshot:
        """
        Build membership snapshot for backtest period.
        
        Args:
            universe_spec: BacktestUniverseSpec (not watchlist or plain list)
            backtest_start: Backtest start date
            backtest_end: Backtest end date (defaults to backtest_start if None)
        
        Returns:
            PointInTimeMembershipSnapshot with effective membership
        
        Raises:
            TypeError: If universe_spec is not BacktestUniverseSpec
            ValueError: If membership source snapshot_date > backtest_start (future leak)
        """
        if backtest_end is None:
            backtest_end = backtest_start
        
        if not isinstance(universe_spec, BacktestUniverseSpec):
            raise TypeError(
                f"Only BacktestUniverseSpec accepted, got {type(universe_spec).__name__}"
            )
        
        if isinstance(universe_spec, ForwardWatchlistSnapshot):
            raise TypeError("ForwardWatchlistSnapshot not allowed for formal backtest")
        
        # Check for confirmed candidate pool (A module output, not formal universe)
        if "confirmed_candidate" in universe_spec.universe_spec_id.lower():
            raise ValueError(
                "Confirmed candidate pool cannot be used as formal backtest universe. "
                "Use historical index membership or sector/concept historical snapshots."
            )
        
        # Missing membership source: fail loud
        if self.membership_source is None:
            return PointInTimeMembershipSnapshot(
                snapshot_id=f"snapshot_{backtest_start.isoformat()}",
                snapshot_date=backtest_start,
                universe_rule_type="point_in_time_membership",
                membership_source=universe_spec.universe_spec_id,
                include_delisted=True,
                records=(),
                quality_status="insufficient",
                gaps=("No membership source provided",),
            )
        
        # Build from membership source
        try:
            records = self.membership_source.records_for_universe(
                universe_spec,
                backtest_start,
                backtest_end,
            )
        except ValueError as e:
            # Future information leak detected
            if "backfill history" in str(e):
                raise
            # Other errors: mark insufficient
            return PointInTimeMembershipSnapshot(
                snapshot_id=f"snapshot_{backtest_start.isoformat()}",
                snapshot_date=backtest_start,
                universe_rule_type="point_in_time_membership",
                membership_source=universe_spec.universe_spec_id,
                include_delisted=True,
                records=(),
                quality_status="insufficient",
                gaps=(str(e),),
            )
        
        quality_status = "ok" if len(records) > 0 else "insufficient"
        gaps = () if len(records) > 0 else ("No records in effective date window",)
        
        return PointInTimeMembershipSnapshot(
            snapshot_id=f"snapshot_{backtest_start.isoformat()}",
            snapshot_date=backtest_start,
            universe_rule_type="point_in_time_membership",
            membership_source=universe_spec.universe_spec_id,
            include_delisted=True,
            records=records,
            quality_status=quality_status,
            gaps=gaps,
        )
    
    def validate_universe_input(self, universe) -> tuple[bool, str]:
        """
        Validate universe input type.
        
        Returns (is_valid, error_message).
        """
        if isinstance(universe, (list, tuple)):
            return (False, "Plain symbol list not allowed for formal backtest")
        
        if isinstance(universe, ForwardWatchlistSnapshot):
            return (False, "ForwardWatchlistSnapshot not allowed for formal backtest")
        
        if not isinstance(universe, BacktestUniverseSpec):
            return (False, f"Must be BacktestUniverseSpec, got {type(universe).__name__}")
        
        return (True, "")
