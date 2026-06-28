"""C module admission guard for B-validated strategies."""
from __future__ import annotations


class CAdmissionGate:
    """
    Allow Signal Board admission only for true prototype_passed strategies.

    Rejects draft, rejected, needs_review, and candidate_for_prototype_passed.
    """

    def require_prototype_passed(
        self, *, strategy_revision_id: str, lifecycle_state: str
    ) -> dict:
        """
        Require strategy lifecycle_state == prototype_passed for C admission.

        Args:
            strategy_revision_id: Strategy revision ID
            lifecycle_state: Current lifecycle state

        Returns:
            dict with admission_status="accepted"

        Raises:
            ValueError: If lifecycle_state is not prototype_passed
        """
        if lifecycle_state != "prototype_passed":
            raise ValueError(
                f"Strategy '{strategy_revision_id}' is not prototype_passed; "
                f"C module admission rejected for state '{lifecycle_state}'"
            )

        return {
            "strategy_revision_id": strategy_revision_id,
            "admission_status": "accepted",
        }
