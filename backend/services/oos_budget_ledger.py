"""OOS Budget Ledger - Theme-level OOS evaluation budget and cache."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from backend.services.b5_oos_types import OOSReservation


class OOSBudgetLedger:
    """
    Theme-level OOS budget ledger with 3-draw limit and atomic reservation.
    
    Budget rules:
    - Maximum 3 completed draws per theme/hypothesis
    - Same (strategy_config_hash, data_snapshot_hash, gate_criteria_hash) returns cached result (no budget draw)
    - Any hash change consumes new draw
    - Infrastructure failure releases reservation without consuming draw
    - Completed rejected reports consume budget
    - Cross-theme same OOS window + data hash is rejected
    - Ledger is append-only
    
    No LLM calls, no status bypass, no prototype_passed write.
    """
    
    def __init__(self):
        # In-memory storage for MVP
        # {theme_id: {hypothesis_source_snapshot_id: ledger_state}}
        self._ledgers: dict[str, dict[str, dict]] = {}
        
        # Cache key: (strategy_config_hash, data_snapshot_hash, gate_criteria_hash) -> reservation_id
        self._cache: dict[tuple[str, str, str], str] = {}
        
        # Cross-theme OOS window guard: (shared_oos_window_id, data_snapshot_hash) -> theme_id
        self._oos_window_usage: dict[tuple[str, str], str] = {}
        
        # Active reservations: reservation_id -> OOSReservation
        self._active_reservations: dict[str, OOSReservation] = {}
    
    def _get_ledger_state(self, theme_id: str, hypothesis_source_snapshot_id: str) -> dict:
        """Get or create ledger state for theme/hypothesis."""
        if theme_id not in self._ledgers:
            self._ledgers[theme_id] = {}
        
        if hypothesis_source_snapshot_id not in self._ledgers[theme_id]:
            self._ledgers[theme_id][hypothesis_source_snapshot_id] = {
                "completed_draw_count": 0,
                "next_oos_draw_index": 1,
                "completed_reservations": [],
                "budget_status": "available",
            }
        
        return self._ledgers[theme_id][hypothesis_source_snapshot_id]
    
    def check_cache(
        self,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
    ) -> str | None:
        """
        Check if same hash tuple has cached result.
        
        Returns:
            reservation_id if cached, None if not
        """
        cache_key = (strategy_config_hash, data_snapshot_hash, gate_criteria_hash)
        return self._cache.get(cache_key)
    
    def reserve_oos_draw(
        self,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
        shared_oos_window_id: str,
    ) -> OOSReservation:
        """
        Reserve OOS draw atomically.
        
        Raises:
            ValueError: If budget exhausted, concurrent reservation active, or cross-theme reuse
        
        Returns:
            OOSReservation with status="reserved"
        """
        # Check cache first
        cached_reservation_id = self.check_cache(
            strategy_config_hash, data_snapshot_hash, gate_criteria_hash
        )
        if cached_reservation_id:
            raise ValueError(
                f"Same hash tuple already has cached result: {cached_reservation_id}. "
                f"No new draw consumed."
            )
        
        # Check cross-theme OOS window reuse
        oos_guard_key = (shared_oos_window_id, data_snapshot_hash)
        if oos_guard_key in self._oos_window_usage:
            existing_theme = self._oos_window_usage[oos_guard_key]
            if existing_theme != theme_id:
                raise ValueError(
                    f"Cross-theme OOS reuse rejected: "
                    f"shared_oos_window_id='{shared_oos_window_id}' + data_snapshot_hash='{data_snapshot_hash}' "
                    f"already used by theme '{existing_theme}'"
                )
        
        # Get ledger state
        state = self._get_ledger_state(theme_id, hypothesis_source_snapshot_id)
        
        # Check budget exhausted
        if state["completed_draw_count"] >= 3:
            raise ValueError(
                f"OOS budget exhausted: theme '{theme_id}' hypothesis '{hypothesis_source_snapshot_id}' "
                f"has completed {state['completed_draw_count']} draws (max 3)"
            )
        
        # Check active reservation (prevent concurrent over-draw)
        cache_key = (strategy_config_hash, data_snapshot_hash, gate_criteria_hash)
        for active_rsv in self._active_reservations.values():
            if (
                active_rsv.theme_id == theme_id
                and active_rsv.hypothesis_source_snapshot_id == hypothesis_source_snapshot_id
            ):
                raise ValueError(
                    f"Active reservation blocks new draw: {active_rsv.reservation_id} "
                    f"is still reserved for theme '{theme_id}'"
                )
        
        # Create reservation
        oos_draw_index = state["next_oos_draw_index"]
        reservation_id = self._generate_reservation_id(theme_id, oos_draw_index)
        
        reservation = OOSReservation(
            reservation_id=reservation_id,
            theme_id=theme_id,
            hypothesis_source_snapshot_id=hypothesis_source_snapshot_id,
            strategy_config_hash=strategy_config_hash,
            data_snapshot_hash=data_snapshot_hash,
            gate_criteria_hash=gate_criteria_hash,
            oos_draw_index=oos_draw_index,
            status="reserved",
            reserved_at=datetime.now(),
        )
        
        # Record active reservation
        self._active_reservations[reservation_id] = reservation
        
        # Record OOS window usage
        self._oos_window_usage[oos_guard_key] = theme_id
        
        return reservation
    
    def complete_reservation(
        self,
        reservation_id: str,
        verdict: str,  # "rejected" | "needs_review" | "candidate_for_prototype_passed"
    ) -> None:
        """
        Complete OOS reservation and consume budget.
        
        Even rejected reports consume budget (to prevent OOS shopping).
        
        Raises:
            ValueError: If reservation not found or already completed
        """
        if reservation_id not in self._active_reservations:
            raise ValueError(f"Reservation '{reservation_id}' not found or already completed")
        
        reservation = self._active_reservations[reservation_id]
        
        # Update ledger state
        state = self._get_ledger_state(reservation.theme_id, reservation.hypothesis_source_snapshot_id)
        state["completed_draw_count"] += 1
        state["next_oos_draw_index"] += 1
        state["completed_reservations"].append({
            "reservation_id": reservation_id,
            "oos_draw_index": reservation.oos_draw_index,
            "verdict": verdict,
            "completed_at": datetime.now().isoformat(),
        })
        
        if state["completed_draw_count"] >= 3:
            state["budget_status"] = "oos_budget_exhausted"
        
        # Add to cache
        cache_key = (
            reservation.strategy_config_hash,
            reservation.data_snapshot_hash,
            reservation.gate_criteria_hash,
        )
        self._cache[cache_key] = reservation_id
        
        # Remove from active
        del self._active_reservations[reservation_id]
    
    def release_reservation(self, reservation_id: str, reason: str) -> None:
        """
        Release OOS reservation due to infrastructure failure.
        
        Does NOT consume budget.
        
        Raises:
            ValueError: If reservation not found
        """
        if reservation_id not in self._active_reservations:
            raise ValueError(f"Reservation '{reservation_id}' not found")
        
        reservation = self._active_reservations[reservation_id]
        
        # Remove OOS window usage guard (allow retry)
        oos_guard_key = None
        for key, theme in self._oos_window_usage.items():
            if theme == reservation.theme_id:
                oos_guard_key = key
                break
        
        if oos_guard_key:
            del self._oos_window_usage[oos_guard_key]
        
        # Remove from active
        del self._active_reservations[reservation_id]
    
    def _generate_reservation_id(self, theme_id: str, oos_draw_index: int) -> str:
        """Generate deterministic reservation ID."""
        payload = {
            "theme_id": theme_id,
            "oos_draw_index": oos_draw_index,
            "timestamp": datetime.now().isoformat(),
        }
        hash_input = json.dumps(payload, sort_keys=True)
        hash_digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
        return f"rsv_{theme_id}_{oos_draw_index}_{hash_digest}"
    
    def get_ledger_state(self, theme_id: str, hypothesis_source_snapshot_id: str) -> dict:
        """Get current ledger state (read-only)."""
        return self._get_ledger_state(theme_id, hypothesis_source_snapshot_id).copy()
