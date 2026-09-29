# -*- coding: utf-8 -*-

"""
Unit Tests for NetworkClient (logic/network_client.py).
Tests URL validation, scheme restrictions, CRLF sanitization, and request handling.
"""

import unittest
from unittest.mock import patch, MagicMock
from logic.network_client import NetworkClient


class TestNetworkClient(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient security and request methods."""

    def setUp(self):
        self.client = NetworkClient()

    def test_invalid_url_input_types(self):
        """Test that non-string or empty URLs raise ValueError or return structured error."""
        res_none = self.client.make_sync_request(None, {})
        self.assertFalse(res_none["success"])
        self.assertEqual(res_none["error_type"], "ValueError")

        res_empty = self.client.make_sync_request("   ", {})
        self.assertFalse(res_empty["success"])
        self.assertEqual(res_empty["error_type"], "ValueError")

    def test_invalid_scheme_rejection(self):
        """Test that dangerous non-http/https schemes like file:// or ftp:// are rejected."""
        res_file = self.client.make_sync_request("file:///etc/passwd", {})
        self.assertFalse(res_file["success"])
        self.assertEqual(res_file["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", res_file["message"])

        res_ftp = self.client.make_sync_request("ftp://malicious.com/data", {})
        self.assertFalse(res_ftp["success"])
        self.assertEqual(res_ftp["error_type"], "ValueError")

    @patch("urllib.request.urlopen")
    def test_crlf_sanitization_and_successful_sync_request(self, mock_urlopen):
        """Test that CRLF in URL is sanitized and valid requests succeed."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # URL with CRLF injection attempt
        url_with_crlf = "http://localhost:1234/v1\r\nX-Injected-Header: bad"
        res = self.client.make_sync_request(url_with_crlf, {"key": "val"})

        self.assertTrue(res["success"])
        self.assertEqual(res["data"], {"status": "ok"})

        # Check that the URL passed to urllib Request had CRLF removed
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:1234/v1X-Injected-Header: bad")

    async def test_stream_request_invalid_scheme(self):
        """Test that stream_request handles invalid scheme and yields error chunk."""
        chunks = []
        async for chunk in self.client.stream_request("file:///etc/passwd", {}):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", chunks[0]["message"])


if __name__ == "__main__":
    unittest.main()
