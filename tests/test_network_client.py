# -*- coding: utf-8 -*-

"""
Unit tests for NetworkClient URL scheme validation and network requests.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

from logic.network_client import NetworkClient


class TestNetworkClient(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient security and request handling."""

    def setUp(self):
        self.client = NetworkClient()

    def test_sync_request_invalid_scheme_rejected(self):
        """Test that non-http/https URL schemes are rejected by make_sync_request."""
        invalid_urls = [
            "file:///etc/passwd",
            "ftp://malicious.host/file",
            "gopher://example.com",
            "data:text/html,<script>alert(1)</script>",
        ]
        for url in invalid_urls:
            res = self.client.make_sync_request(url, {"test": "payload"})
            self.assertFalse(res["success"])
            self.assertEqual(res["error_type"], "ValueError")
            self.assertIn("Invalid URL scheme", res["message"])

    async def test_stream_request_invalid_scheme_rejected(self):
        """Test that non-http/https URL schemes are rejected by stream_request."""
        invalid_url = "file:///etc/shadow"
        chunks = []
        async for chunk in self.client.stream_request(invalid_url, {"test": "payload"}):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", chunks[0]["message"])

    @patch("urllib.request.urlopen")
    def test_sync_request_valid_url_success(self, mock_urlopen):
        """Test that valid http and https URLs are accepted and processed."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = self.client.make_sync_request("http://localhost:1234/v1/chat", {"test": "payload"})
        self.assertTrue(res["success"])
        self.assertEqual(res["data"], {"result": "ok"})


if __name__ == "__main__":
    unittest.main()
