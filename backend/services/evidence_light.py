"""
Evidence light-check runner.

Deterministic Evidence runner that accepts candidates and validation results.

Outputs:
- kill_criteria_hash
- supporting_evidence
- falsifying_evidence
- conflict_items
- evidence_level
- blocking_issues
- evidence_gaps
- tool_trace

Evidence items include expiry data through expiry_days or valid_until.

Kill criteria handling:
- V1 light-check uses the baseline kill criteria snapshot
- V1 still computes and stores kill_criteria_hash
- Evidence must not run if the baseline kill criteria snapshot cannot be resolved
- Full editable kill_criteria_snapshot and criteria_validator can be implemented later behind the same hash field

Key behaviors:
- clean candidate gets no blocking issues
- hard-filter flags become blocking issues
- unknown evidence stays 'unknown'
- falsifying evidence can lower level to 'falsified'
- conflicting evidence becomes 'conflicted'
- 'conflicted' does not become blocking_issues
- expired evidence is detectable
- tool trace records deterministic steps
"""

import hashlib
from datetime import date, datetime, timedelta
from contracts.research import (
    EvidenceOutput,
    EvidenceItem,
    ConflictItem,
)
from backend.services.research_validation import ValidationResult
from backend.services.evidence_quality import EvidenceQualityValidator


# Baseline kill criteria snapshot (V1)
BASELINE_KILL_CRITERIA = {
    "version": "v1_baseline",
    "rules": [
        "ST 或 *ST 股票",
        "停牌股票",
        "低流动性股票（日均成交额 < 100万）",
        "未上市或退市股票",
    ],
}


class EvidenceLightRunner:
    """
    Evidence light-check runner.
    
    V1 implementation uses baseline kill criteria and deterministic validation.
    Future versions can add external evidence sources behind the same contract.
    """

    def __init__(self):
        """Initialize evidence runner."""
        self.baseline_criteria = BASELINE_KILL_CRITERIA

    def run_light_check(
        self,
        candidate_id: str,
        symbol: str,
        validation_result: ValidationResult,
        inject_supporting_evidence: list[dict] | None = None,
        inject_falsifying_evidence: list[dict] | None = None,
        inject_conflict: list[dict] | None = None,
        inject_missing_baseline: bool = False,
        hard_filter_metadata: dict | None = None,
    ) -> EvidenceOutput:
        """
        Run light-check evidence analysis.
        
        Args:
            candidate_id: Candidate ID
            symbol: Stock symbol
            validation_result: Validation result with flags
            inject_supporting_evidence: Test injection for supporting evidence
            inject_falsifying_evidence: Test injection for falsifying evidence
            inject_conflict: Test injection for conflicting evidence
            inject_missing_baseline: Test injection to simulate missing baseline
        
        Returns:
            EvidenceOutput with evidence level and items
        
        Raises:
            ValueError: If baseline kill criteria snapshot is not available
        """
        if inject_missing_baseline:
            raise ValueError("Baseline kill criteria snapshot not available")

        now = datetime.now()

        # Compute kill criteria hash
        kill_criteria_hash = self._compute_kill_criteria_hash()

        # Convert hard filter flags to blocking issues
        blocking_issues = list(validation_result.flags)

        # Initialize evidence lists
        supporting_evidence = []
        falsifying_evidence = []
        conflict_items = []

        # Inject test evidence if provided
        if inject_supporting_evidence:
            for item in inject_supporting_evidence:
                evidence = EvidenceItem(
                    source=item["source"],
                    source_type=item.get("source_type", "unknown"),
                    source_quality=item.get("source_quality", "weak"),
                    description=item["description"],
                    published_at=item.get("published_at"),
                    retrieved_at=now,
                    expiry_days=item.get("expiry_days"),
                    valid_until=item.get("valid_until"),
                    supports=item.get("supports", []),
                    falsifies=item.get("falsifies", []),
                    conflicts=item.get("conflicts", []),
                )
                supporting_evidence.append(evidence)

        if inject_falsifying_evidence:
            for item in inject_falsifying_evidence:
                evidence = EvidenceItem(
                    source=item["source"],
                    source_type=item.get("source_type", "unknown"),
                    source_quality=item.get("source_quality", "weak"),
                    description=item["description"],
                    published_at=item.get("published_at"),
                    retrieved_at=now,
                    expiry_days=item.get("expiry_days"),
                    valid_until=item.get("valid_until"),
                    supports=item.get("supports", []),
                    falsifies=item.get("falsifies", []),
                    conflicts=item.get("conflicts", []),
                )
                falsifying_evidence.append(evidence)

        if inject_conflict:
            for item in inject_conflict:
                conflict = ConflictItem(
                    source_a=item["source_a"],
                    source_b=item["source_b"],
                    conflict_type=item["conflict_type"],
                    description=item["description"],
                )
                conflict_items.append(conflict)

        # === Source quality validation (deterministic) ===
        quality_validator = EvidenceQualityValidator()
        quality = quality_validator.validate(
            supporting_evidence=supporting_evidence,
            falsifying_evidence=falsifying_evidence,
            conflict_items_count=len(conflict_items),
            reference_date=date.today(),
        )

        # Add quality blocking reasons to blocking_issues
        blocking_issues.extend(quality.blocking_reasons)

        # Determine evidence level respecting quality rules
        evidence_level = quality_validator.evaluate_evidence_level(
            quality=quality,
            current_level=(
                "conflicted" if len(conflict_items) > 0
                else "falsified" if len(falsifying_evidence) > 0
                else "medium" if len(supporting_evidence) > 0
                else "unknown"
            ),
            supporting_count=len(supporting_evidence),
            falsifying_count=len(falsifying_evidence),
            conflict_count=len(conflict_items),
        )

        # Evidence gaps: hard-filter gaps + quality gaps/warnings
        evidence_gaps = []
        if hard_filter_metadata:
            evidence_gaps.extend(hard_filter_metadata.get("gaps", []))
        evidence_gaps.extend(quality.gaps)
        evidence_gaps.extend(quality.warnings)
        for evidence in supporting_evidence:
            if evidence.expiry_days and evidence.published_at:
                days_since_published = (date.today() - evidence.published_at).days
                if days_since_published > evidence.expiry_days:
                    evidence_gaps.append(f"证据已过期: {evidence.source} ({evidence.description})")

        # Tool trace
        tool_trace = [
            {
                "step": "validation",
                "action": "check_hard_filters",
                "result": {
                    "flags": validation_result.flags,
                    "is_valid": validation_result.is_valid,
                    "metadata": hard_filter_metadata or {},
                },
                "timestamp": now.isoformat(),
            },
            {
                "step": "evidence_aggregation",
                "action": "collect_evidence",
                "result": {
                    "supporting_count": len(supporting_evidence),
                    "falsifying_count": len(falsifying_evidence),
                    "conflict_count": len(conflict_items),
                },
                "timestamp": now.isoformat(),
            },
            {
                "step": "level_determination",
                "action": "compute_evidence_level",
                "result": {"evidence_level": evidence_level},
                "timestamp": now.isoformat(),
            },
        ]

        return EvidenceOutput(
            candidate_id=candidate_id,
            kill_criteria_hash=kill_criteria_hash,
            evidence_level=evidence_level,
            supporting_evidence=supporting_evidence,
            falsifying_evidence=falsifying_evidence,
            conflict_items=conflict_items,
            blocking_issues=blocking_issues,
            evidence_gaps=evidence_gaps,
            tool_trace=tool_trace,
            created_at=now,
        )

    def _compute_kill_criteria_hash(self) -> str:
        """
        Compute kill criteria hash from baseline snapshot.
        
        Returns:
            SHA256 hash of baseline kill criteria
        """
        criteria_json = str(self.baseline_criteria)
        return hashlib.sha256(criteria_json.encode()).hexdigest()
