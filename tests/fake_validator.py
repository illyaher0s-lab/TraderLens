"""
Fake validator for testing friend-stock flow.
"""


class FakeValidator:
    """Fake validator that passes all checks."""
    
    def validate(self, *args, **kwargs):
        """Always return success."""
        return {"valid": True}
    
    def check_hard_filters(self, *args, **kwargs):
        """Always return empty (no filters triggered)."""
        return []
