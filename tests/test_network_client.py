# -*- coding: utf-8 -*-

"""
Unit Tests for NetworkClient Security and Request Handling.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
from logic.network_client import NetworkClient


class TestNetworkClient(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient security and functionality."""

    def setUp(self):
        self.client = NetworkClient()

    def test_validate_and_sanitize_url_valid(self):
        """Test valid HTTP and HTTPS URLs pass validation."""
        url_http = "http://localhost:1234/v1/chat/completions"
        self.assertEqual(self.client._validate_and_sanitize_url(url_http), url_http)

        url_https = "https://api.openai.com/v1/chat/completions"
        self.assertEqual(self.client._validate_and_sanitize_url(url_https), url_https)

    def test_validate_and_sanitize_url_invalid_schemes(self):
        """Test non-HTTP/HTTPS schemes (file://, ftp://, gopher://) are rejected."""
        invalid_urls = [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/file.txt",
            "gopher://evil.com/payload",
            "javascript:alert(1)",
        ]
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                with self.assertRaises(ValueError) as ctx:
                    self.client._validate_and_sanitize_url(invalid_url)
                self.assertIn("Invalid URL scheme", str(ctx.exception))

    def test_validate_and_sanitize_url_crlf_sanitization(self):
        """Test CRLF characters are stripped to prevent HTTP header/request injection."""
        injected_url = "http://localhost:1234/v1\r\nX-Injected-Header: evil\n"
        clean_url = self.client._validate_and_sanitize_url(injected_url)
        self.assertEqual(clean_url, "http://localhost:1234/v1X-Injected-Header: evil")
        self.assertNotIn("\r", clean_url)
        self.assertNotIn("\n", clean_url)

    def test_validate_and_sanitize_url_empty(self):
        """Test empty or whitespace URLs raise ValueError."""
        for empty_url in ["", "   ", None]:
            with self.subTest(url=empty_url):
                with self.assertRaises(ValueError):
                    self.client._validate_and_sanitize_url(empty_url)

    def test_make_sync_request_invalid_scheme_handling(self):
        """Test make_sync_request returns structured error when invalid URL scheme is provided."""
        res = self.client.make_sync_request("file:///etc/passwd", {"test": "data"})
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", res["message"])

    @patch("urllib.request.urlopen")
    def test_make_sync_request_success(self, mock_urlopen):
        """Test successful sync request returning JSON data."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok", "result": 42}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = self.client.make_sync_request("http://localhost:1234/v1", {"ping": "pong"})
        self.assertTrue(res["success"])
        self.assertEqual(res["data"], {"status": "ok", "result": 42})

    async def test_stream_request_invalid_scheme_handling(self):
        """Test stream_request yields structured error for invalid URL scheme."""
        chunks = []
        async for chunk in self.client.stream_request("ftp://localhost:21/data", {"prompt": "hi"}):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", chunks[0]["message"])


if __name__ == "__main__":
    unittest.main()
