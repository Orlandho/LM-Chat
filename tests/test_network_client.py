# -*- coding: utf-8 -*-

"""
Unit tests for NetworkClient, verifying URL scheme validation and SSRF protection.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from logic.network_client import NetworkClient


class TestNetworkClientSecurity:
    """Test suite for NetworkClient security validation and behavior."""

    @pytest.fixture
    def client(self):
        return NetworkClient()

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/file.txt",
            "gopher://localhost:70",
            "data:text/plain;base64,SGVsbG8=",
            "javascript:alert(1)",
            "///etc/passwd",
            "relative/path/to/resource",
            "",
            "   ",
            None,
            12345,
        ],
    )
    def test_sync_request_rejects_invalid_urls(self, client, invalid_url):
        """Ensures non-http/https schemes and malformed inputs are rejected cleanly."""
        res = client.make_sync_request(invalid_url, {"key": "value"})
        assert res["success"] is False
        assert res["error_type"] == "ValueError"
        assert "Invalid URL scheme" in res["message"] or "non-empty string" in res["message"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_url",
        [
            "file:///etc/passwd",
            "ftp://example.com/file.txt",
            "gopher://localhost:70",
            "",
        ],
    )
    async def test_stream_request_rejects_invalid_urls(self, client, invalid_url):
        """Ensures streaming requests reject non-http/https schemes."""
        results = []
        async for chunk in client.stream_request(invalid_url, {"key": "value"}):
            results.append(chunk)

        assert len(results) == 1
        res = results[0]
        assert res["success"] is False
        assert res["error_type"] == "ValueError"
        assert "Invalid URL scheme" in res["message"] or "non-empty string" in res["message"]

    @patch("urllib.request.urlopen")
    def test_sync_request_success_with_valid_url(self, mock_urlopen, client):
        """Ensures http/https URLs are processed successfully when urlopen succeeds."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "ok"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = client.make_sync_request("https://localhost:8080/v1/chat", {"prompt": "hello"})
        assert res["success"] is True
        assert res["data"] == {"response": "ok"}
