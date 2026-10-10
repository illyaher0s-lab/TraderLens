"""
V2 Task 2 — Deterministic tests for finite request-timeout propagation
and fast-failure on the LLM and Tushare HTTP clients.

These tests run fully offline (no real cc-vibe.com / Tushare calls):
- Propagation is verified by inspecting the configured timeout values.
- Fast-failure is verified against a local stdlib HTTP server that accepts
  the connection but never responds, so the SDK's OWN timeout fires. The
  server is a self-contained test fixture (daemon thread, torn down per
  test) — NOT a production background task, retry loop, or parallel client.
"""

import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import tushare as ts

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from backend.services.llm_client import LLMClient


class _HangingHandler(BaseHTTPRequestHandler):
    """Accepts any POST but never sends a response — forces a read timeout."""

    def do_POST(self):
        # Never respond; let the client's read timeout fire.
        time.sleep(60)

    def log_message(self, *args):  # silence test noise
        pass


class TestLLMClientTimeout(unittest.TestCase):
    def test_default_timeout_is_30s(self):
        """Default request timeout is 30s, matching serenity_executor.py."""
        client = LLMClient(api_key="dummy-test-key")
        self.assertEqual(client.timeout, 30.0)
        # Propagated into the underlying Anthropic SDK client.
        self.assertEqual(client.client.timeout, 30.0)
        # No silent retry loop — a hang fails once, not N times.
        self.assertEqual(client.client.max_retries, 0)

    def test_custom_timeout_propagates(self):
        """An explicit timeout flows through to the SDK client."""
        client = LLMClient(api_key="dummy-test-key", timeout=7.5)
        self.assertEqual(client.timeout, 7.5)
        self.assertEqual(client.client.timeout, 7.5)

    def test_fast_failure_on_hung_upstream(self):
        """A hung upstream must fail within the finite timeout, not block forever."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _HangingHandler)
        server.daemon_threads = True
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            client = LLMClient(
                api_key="dummy-test-key",
                base_url=f"http://127.0.0.1:{port}",
                timeout=2.0,
            )
            t0 = time.time()
            with self.assertRaises(ValueError) as ctx:
                client.create_message(messages=[{"role": "user", "content": "ping"}])
            elapsed = time.time() - t0
            # Fast-failure: far below the 60s hang, bounded by the 2s timeout.
            self.assertLess(elapsed, 15.0)
            self.assertIn("LLM API call failed", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()


class TestTushareClientTimeout(unittest.TestCase):
    def test_config_default_timeout_is_30s(self):
        """TushareConfig ships a finite 30s default request timeout."""
        self.assertEqual(TushareConfig().request_timeout_seconds, 30.0)

    def test_client_propagates_timeout_to_pro_api(self):
        """TushareClient must pass request_timeout_seconds into ts.pro_api(timeout=...)."""
        captured = {}
        config = TushareConfig(token="dummy-tushare-token")

        def fake_pro_api(token="", timeout=30):
            captured["token"] = token
            captured["timeout"] = timeout

            class _FakePro:
                _DataApi__http_url = ""

            return _FakePro()

        with patch.object(ts, "pro_api", side_effect=fake_pro_api):
            TushareClient(config)

        self.assertIn("timeout", captured)
        self.assertEqual(captured["timeout"], 30.0)
        self.assertEqual(captured["token"], "dummy-tushare-token")


if __name__ == "__main__":
    unittest.main()
