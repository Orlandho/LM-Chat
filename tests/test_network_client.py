# -*- coding: utf-8 -*-

"""
Unit Tests for NetworkClient URL Scheme Validation and Security Controls.
"""

import unittest
import asyncio
from logic.network_client import NetworkClient


class TestNetworkClient(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient security and request handling."""

    def setUp(self):
        self.client = NetworkClient()

    def test_sync_request_invalid_scheme_rejected(self):
        """Test that non-HTTP/HTTPS schemes are securely rejected in sync requests."""
        invalid_urls = [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://malicious-server.com/resource",
            "gopher://evil.com",
            "javascript:alert(1)",
            "relative/path/to/resource",
            None,
            123,
        ]

        for url in invalid_urls:
            res = self.client.make_sync_request(url, {"test": "data"})
            self.assertFalse(res["success"])
            self.assertEqual(res["error_type"], "ValueError")
            self.assertIn("Security validation failed", res["message"])

    async def test_stream_request_invalid_scheme_rejected(self):
        """Test that non-HTTP/HTTPS schemes are securely rejected in streaming requests."""
        invalid_urls = [
            "file:///etc/passwd",
            "ftp://malicious-server.com/resource",
            "gopher://evil.com",
        ]

        for url in invalid_urls:
            chunks = []
            async for chunk in self.client.stream_request(url, {"test": "data"}):
                chunks.append(chunk)

            self.assertEqual(len(chunks), 1)
            self.assertFalse(chunks[0]["success"])
            self.assertEqual(chunks[0]["error_type"], "ValueError")
            self.assertIn("Security validation failed", chunks[0]["message"])


if __name__ == "__main__":
    unittest.main()
