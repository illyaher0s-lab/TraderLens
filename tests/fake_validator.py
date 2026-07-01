"""
Fake validator for testing friend-stock flow.
"""


class FakeValidator:
    """Fake validator that passes all checks."""
    
    def __init__(self):
        """Initialize fake validator with tushare_client stub."""
        self.tushare_client = None  # Stub for compatibility
    
    def validate(self, *args, **kwargs):
        """Always return success."""
        return {"valid": True}
    
    def check_hard_filters(self, *args, **kwargs):
        """Always return empty (no filters triggered)."""
        return []
