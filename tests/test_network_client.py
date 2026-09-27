# -*- coding: utf-8 -*-

"""
Unit Tests for NetworkClient Security Validation.
"""

import unittest
import asyncio
from unittest.mock import patch, MagicMock

from logic.network_client import NetworkClient


class TestNetworkClientSecurity(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient input and scheme validation."""

    def setUp(self):
        self.client = NetworkClient()

    def test_sync_request_invalid_scheme_file(self):
        """Test that file:// scheme is rejected to prevent local file inclusion."""
        result = self.client.make_sync_request("file:///etc/passwd", {"prompt": "test"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", result["message"])

    def test_sync_request_invalid_scheme_ftp(self):
        """Test that ftp:// scheme is rejected."""
        result = self.client.make_sync_request("ftp://malicious.host/path", {"prompt": "test"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", result["message"])

    def test_sync_request_invalid_type(self):
        """Test that non-string URL is rejected."""
        result = self.client.make_sync_request(12345, {"prompt": "test"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", result["message"])

    async def test_stream_request_invalid_scheme_file(self):
        """Test that streaming request with file:// scheme is rejected."""
        chunks = []
        async for chunk in self.client.stream_request("file:///etc/passwd", {"prompt": "test"}):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", chunks[0]["message"])

    @patch("urllib.request.urlopen")
    def test_sync_request_valid_http(self, mock_urlopen):
        """Test that valid http:// URL proceeds to urllib request."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "ok"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = self.client.make_sync_request("http://localhost:1234/v1/chat", {"prompt": "test"})
        self.assertTrue(result["success"])
        self.assertEqual(result["data"], {"response": "ok"})


if __name__ == "__main__":
    unittest.main()
