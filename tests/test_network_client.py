# -*- coding: utf-8 -*-

"""
Unit tests for logic.network_client.NetworkClient.
Verifies URL scheme validation, CRLF sanitization, and security controls.
"""

import pytest
import asyncio
from logic.network_client import NetworkClient


class TestNetworkClientSecurity:
    """Security tests for NetworkClient."""

    def test_validate_url_valid_http_and_https(self):
        """Test that http:// and https:// URLs are accepted and cleaned."""
        client = NetworkClient()
        assert client._validate_url("http://localhost:1234/v1") == "http://localhost:1234/v1"
        assert client._validate_url("https://api.openai.com/v1\r\n") == "https://api.openai.com/v1"

    def test_validate_url_invalid_schemes(self):
        """Test that non-HTTP/HTTPS schemes (e.g. file://, ftp://) raise ValueError."""
        client = NetworkClient()
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            client._validate_url("file:///etc/passwd")

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            client._validate_url("ftp://example.com/resource")

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            client._validate_url("gopher://example.com")

    def test_validate_url_non_string(self):
        """Test non-string input rejection."""
        client = NetworkClient()
        with pytest.raises(ValueError, match="URL must be a string"):
            client._validate_url(12345)

    def test_make_sync_request_invalid_scheme(self):
        """Test make_sync_request returns ValueError dict for bad schemes."""
        client = NetworkClient()
        res = client.make_sync_request("file:///etc/passwd", {})
        assert res["success"] is False
        assert res["error_type"] == "ValueError"
        assert "Invalid URL scheme" in res["message"]

    @pytest.mark.asyncio
    async def test_stream_request_invalid_scheme(self):
        """Test stream_request yields error dict for bad schemes."""
        client = NetworkClient()
        results = []
        async for chunk in client.stream_request("file:///etc/passwd", {}):
            results.append(chunk)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error_type"] == "ValueError"
        assert "Invalid URL scheme" in results[0]["message"]
