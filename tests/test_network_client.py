# -*- coding: utf-8 -*-

"""
Unit Tests for NetworkClient Security and URL Validation.
"""

import unittest
import asyncio
from unittest.mock import patch, MagicMock
from logic.network_client import NetworkClient


class TestNetworkClient(unittest.IsolatedAsyncioTestCase):
    """Unit tests for NetworkClient security and request handling."""

    def setUp(self):
        self.client = NetworkClient()

    def test_validate_url_valid_schemes(self):
        """Test that http and https URLs are properly validated and returned."""
        self.assertEqual(self.client._validate_url("http://localhost:1234/v1"), "http://localhost:1234/v1")
        self.assertEqual(self.client._validate_url("https://api.openai.com/v1"), "https://api.openai.com/v1")

    def test_validate_url_crlf_sanitization(self):
        """Test that CRLF characters are stripped from URLs to prevent header injection."""
        url_with_crlf = "http://localhost:1234/v1\r\nX-Injected-Header: bad\n"
        cleaned = self.client._validate_url(url_with_crlf)
        self.assertEqual(cleaned, "http://localhost:1234/v1X-Injected-Header: bad")

    def test_validate_url_invalid_schemes_rejected(self):
        """Test that file://, ftp://, and other non-http/https schemes raise ValueError."""
        invalid_urls = [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://malicious.host/file",
            "gopher://localhost:70",
            "data:text/plain;base64,SGVsbG8=",
        ]
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                with self.assertRaises(ValueError):
                    self.client._validate_url(invalid_url)

    def test_validate_url_empty_or_invalid_types(self):
        """Test that empty strings and non-string inputs raise ValueError."""
        with self.assertRaises(ValueError):
            self.client._validate_url("")
        with self.assertRaises(ValueError):
            self.client._validate_url("   ")
        with self.assertRaises(ValueError):
            self.client._validate_url(None)

    def test_make_sync_request_invalid_scheme(self):
        """Test that make_sync_request returns structured ValueError for invalid URL scheme."""
        result = self.client.make_sync_request("file:///etc/passwd", {"prompt": "test"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", result["message"])

    async def test_stream_request_invalid_scheme(self):
        """Test that stream_request yields structured ValueError for invalid URL scheme."""
        chunks = []
        async for chunk in self.client.stream_request("file:///etc/passwd", {"prompt": "test"}):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ValueError")
        self.assertIn("Invalid URL scheme", chunks[0]["message"])


if __name__ == "__main__":
    unittest.main()
