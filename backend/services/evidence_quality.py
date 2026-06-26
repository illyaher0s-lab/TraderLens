"""
Evidence source-quality validator.

Deterministic rules (per A模块计划文档 §6):
- no_source_cannot_support_confirmation
- weak_source_cannot_be_strong_evidence
- expired_evidence_must_be_visible
- unresolved_conflict_blocks_auto_confirmation
- evidence_must_include_support_and_counter_evidence

Every rule is deterministic — no LLM involved in quality decisions.
"""

from __future__ import annotations

from datetime import date
from contracts.research import EvidenceItem
from backend.services.data_tools import DataToolResult


# ------------------------------------------------------------------
# Deterministic source mapping
# ------------------------------------------------------------------

SOURCE_MAPPING: dict[str, tuple[str, str]] = {
    "tushare_income": ("financial_report", "first_hand"),
    "tushare_anns": ("announcement", "first_hand"),
    "tushare_stock_basic": ("financial_report", "first_hand"),
    "tushare_daily_basic": ("financial_report", "first_hand"),
    "prospectus": ("prospectus", "first_hand"),
    "news": ("news", "second_hand"),
    "interaction_platform": ("interaction_platform", "weak"),
    "social_media": ("social_media", "weak"),
}

DEFAULT_MAPPING: tuple[str, str] = ("unknown", "weak")


def classify_source(source: str) -> tuple[str, str]:
    """
    Map a data tool source to (source_type, source_quality).

    Uses deterministic lookup — no LLM.
    """
    return SOURCE_MAPPING.get(source, DEFAULT_MAPPING)


class EvidenceQualityResult:
    """
    Result of evidence quality validation.

    All fields are populated by deterministic rules.
    LLM may read but not modify this result.
    """

    def __init__(self):
        self.has_support: bool = False
        self.has_counter_evidence: bool = False  # falsifying or conflict
        self.all_weak: bool = True
        self.any_no_source: bool = False
        self.any_expired: bool = False
        self.any_unresolved_conflict: bool = False
        self.weak_mapped_to_strong: list[str] = []
        self.blocking_reasons: list[str] = []
        self.warnings: list[str] = []
        self.gaps: list[str] = []

    @property
    def can_auto_confirm(self) -> bool:
        """Whether the evidence quality allows automatic confirmation."""
        if not self.has_support:
            return False
        return len(self.blocking_reasons) == 0


class EvidenceQualityValidator:
    """
    Validates evidence quality against deterministic rules.

    Rules (from A模块计划文档 §6 and §9.4):
    1. No source → cannot support confirmation
    2. weak source_quality → cannot map to 'strong' evidence_level
    3. All evidence is weak → blocked (conservative default)
    4. Expired evidence → gap/warning (must be visible)
    5. Unresolved conflict → blocks auto-confirmation
    6. Must have both support chain and counter-evidence chain
    """

    def __init__(self):
        pass

    def validate(
        self,
        supporting_evidence: list[EvidenceItem],
        falsifying_evidence: list[EvidenceItem],
        conflict_items_count: int,
        reference_date: date | None = None,
    ) -> EvidenceQualityResult:
        """
        Validate evidence quality.

        Args:
            supporting_evidence: List of supporting evidence items
            falsifying_evidence: List of falsifying evidence items
            conflict_items_count: Number of conflict items
            reference_date: Reference date for expiry checks (defaults to today)

        Returns:
            EvidenceQualityResult with blocking_reasons and warnings
        """
        if reference_date is None:
            reference_date = date.today()

        result = EvidenceQualityResult()

        # --- Rule 6: Must have both support and counter-evidence ---
        if len(supporting_evidence) > 0:
            result.has_support = True
        if len(falsifying_evidence) > 0 or conflict_items_count > 0:
            result.has_counter_evidence = True

        total_items = len(supporting_evidence) + len(falsifying_evidence)
        has_any_evidence = total_items > 0 or conflict_items_count > 0

        # Only enforce "must have support" when some evidence exists.
        # If there's no evidence at all, the state is 'unknown' / 'needs_evidence',
        # which is already handled by the evidence level system.
        if has_any_evidence and not result.has_support:
            result.blocking_reasons.append(
                "no_supporting_evidence: evidence exists but no supporting items; "
                "confirmation requires at least one supporting evidence item"
            )

        # --- Inspect all items ---
        all_evidence = list(supporting_evidence) + list(falsifying_evidence)

        for item in all_evidence:
            source_type = item.source_type or "unknown"
            source_quality = item.source_quality or "weak"

            # Rule 1: No source → block
            if source_type == "unknown":
                result.any_no_source = True

            # Rule 2: weak → cannot be strong
            if source_quality == "weak":
                result.weak_mapped_to_strong.append(item.source)
            elif source_quality in ("first_hand", "second_hand"):
                result.all_weak = False

            # Rule 4: expired evidence
            if item.published_at and item.expiry_days:
                days_since = (reference_date - item.published_at).days
                if days_since > item.expiry_days:
                    result.any_expired = True
                    result.gaps.append(
                        f"expired_evidence: {item.source} "
                        f"(published {item.published_at}, "
                        f"expired after {item.expiry_days} days)"
                    )
            if item.valid_until and item.valid_until < reference_date:
                result.any_expired = True
                result.gaps.append(
                    f"expired_evidence: {item.source} (valid_until {item.valid_until})"
                )

        # --- Rule 1: no source → block ---
        if result.any_no_source:
            result.blocking_reasons.append(
                "no_source: evidence items with source_type='unknown' cannot support confirmation"
            )

        # --- Rule 3: all weak → block (only when evidence exists) ---
        if result.all_weak and has_any_evidence and len(supporting_evidence) > 0:
            result.blocking_reasons.append(
                "all_weak_sources: all evidence is from weak sources; "
                "confirmation requires at least one first_hand or second_hand source"
            )

        # --- Rule 2: weak → strong ---
        if result.weak_mapped_to_strong:
            result.warnings.append(
                f"weak_sources_present: evidence items from weak sources "
                f"({', '.join(result.weak_mapped_to_strong)}) cannot produce "
                f"'strong' evidence_level"
            )

        # --- Rule 5: unresolved conflict → block ---
        if conflict_items_count > 0:
            result.any_unresolved_conflict = True
            result.blocking_reasons.append(
                f"unresolved_conflict: {conflict_items_count} conflict(s) "
                f"block auto-confirmation until resolved"
            )

        # --- Rule 4: expired (add to blocking if all-encompassing) ---
        if result.any_expired:
            result.warnings.append("expired_evidence_detected: some evidence has expired")

        # --- Rule 6: counter-evidence ---
        if has_any_evidence and not result.has_counter_evidence and result.has_support:
            result.warnings.append(
                "no_counter_evidence: evidence pack lacks falsifying or conflicting evidence; "
                "confirmation should consider both sides"
            )

        return result

    def evaluate_evidence_level(
        self,
        quality: EvidenceQualityResult,
        current_level: str,
        supporting_count: int,
        falsifying_count: int,
        conflict_count: int,
    ) -> str:
        """
        Compute evidence_level respecting quality rules.

        Weak sources cannot produce 'strong'. Conflicts produce 'conflicted'.
        Falsifying produces 'falsified'. Otherwise inherits the runner's level.
        """
        if conflict_count > 0:
            return "conflicted"
        if falsifying_count > 0:
            return "falsified"
        if supporting_count == 0:
            return "unknown"

        # Quality-capped evidence level
        if quality.all_weak:
            return "weak"
        if current_level == "strong" and quality.weak_mapped_to_strong:
            return "medium"  # downgraded: weak evidence can't be strong
        if current_level == "strong" and quality.any_no_source:
            return "medium"
        return current_level

    def map_tool_results_to_evidence(
        self,
        tool_results: list[DataToolResult],
        reference_date: date | None = None,
    ) -> list[EvidenceItem]:
        """
        Convert DataToolResult items to EvidenceItems with source classification.

        Each resulting EvidenceItem can be traced back to its tool and original data.
        Tool gaps/errors are preserved in the description.

        Args:
            tool_results: List of DataToolResult from data tools
            reference_date: Reference date for retrieved_at

        Returns:
            List of EvidenceItem with source_type and source_quality populated
        """
        from datetime import datetime
        now = datetime.now()
        if reference_date is None:
            reference_date = date.today()

        items: list[EvidenceItem] = []
        for result in tool_results:
            source_type, source_quality = classify_source(result.source)

            # Build a description that traces back to the tool and original data
            desc_parts = [f"Tool: {result.tool_name}"]
            if result.raw_data:
                desc_parts.append(f"Records: {len(result.raw_data)}")
            if result.gaps:
                desc_parts.append(f"Gaps: {', '.join(result.gaps)}")
            if result.errors:
                desc_parts.append(f"Errors: {', '.join(result.errors)}")

            item = EvidenceItem(
                source=result.tool_name,
                source_type=source_type,
                source_quality=source_quality,
                description="; ".join(desc_parts),
                retrieved_at=result.retrieved_at,
                supports=[],
                falsifies=[],
                conflicts=[],
            )
            items.append(item)

        return items
