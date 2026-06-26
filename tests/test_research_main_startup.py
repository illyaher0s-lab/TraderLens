"""Integration tests for the real Research API startup path."""

import io
import os
import unittest
from contextlib import redirect_stdout

from fastapi.testclient import TestClient

from backend.app.main import app


class TestResearchMainStartup(unittest.TestCase):
    """The unified backend must expose Research API routes on Windows."""

    def test_deterministic_startup_uses_ascii_output_and_standard_routes(self):
        """Startup must not fail on legacy Windows consoles or double-prefix routes."""
        ascii_stdout = io.TextIOWrapper(io.BytesIO(), encoding="ascii")

        # Direct set/pop instead of patch.dict to avoid hitting the Windows
        # os.environ 32767-char limit on PATH values during teardown.
        old_mode = os.environ.get("RESEARCH_CONVERSATION_MODE")
        os.environ["RESEARCH_CONVERSATION_MODE"] = "deterministic"
        try:
            with redirect_stdout(ascii_stdout):
                with TestClient(app) as client:
                    response = client.get("/api/research/themes")
                    doubled = client.get("/api/research/api/research/themes")
        finally:
            if old_mode is not None:
                os.environ["RESEARCH_CONVERSATION_MODE"] = old_mode
            else:
                os.environ.pop("RESEARCH_CONVERSATION_MODE", None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(doubled.status_code, 404)


if __name__ == "__main__":
    unittest.main()
