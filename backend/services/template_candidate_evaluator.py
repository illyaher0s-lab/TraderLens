"""
Template Candidate Evaluator

Evaluates candidate templates (never approved, stored separately).

Red line 3: Candidate is never approved template.
"""

from contracts.strategy_idea import CandidateTemplateEvaluation


class TemplateCandidateEvaluator:
    """
    Evaluates candidate templates.
    
    Red line 3: Candidates never enter live template library.
    """

    def evaluate_candidate(self, candidate: CandidateTemplateEvaluation) -> dict:
        """
        Evaluate candidate template.
        
        Returns evaluation result (never promotes to approved).
        """
        # Evaluation logic (placeholder)
        return {
            "candidate_id": candidate.candidate_id,
            "is_approved": False,  # Always False
            "stored_separately": True,
            "evaluation_status": candidate.evaluation_status,
        }
