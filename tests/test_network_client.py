# -*- coding: utf-8 -*-

"""Unit tests for NetworkClient URL validation and security controls."""

import pytest
from logic.network_client import NetworkClient


def test_network_client_valid_url_schemes():
    client = NetworkClient()
    assert client._validate_url("http://localhost:1234/v1/chat") == "http://localhost:1234/v1/chat"
    assert client._validate_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_network_client_rejects_non_http_schemes():
    client = NetworkClient()

    invalid_urls = [
        "file:///etc/passwd",
        "file:///C:/Windows/system.ini",
        "ftp://example.com/file",
        "gopher://example.com",
        "javascript:alert(1)",
        "invalid_scheme",
    ]

    for url in invalid_urls:
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            client._validate_url(url)


def test_make_sync_request_returns_value_error_dict():
    client = NetworkClient()
    result = client.make_sync_request("file:///etc/passwd", {"prompt": "test"})
    assert result["success"] is False
    assert result["error_type"] == "ValueError"
    assert "Invalid URL scheme" in result["message"]


@pytest.mark.asyncio
async def test_stream_request_returns_value_error_dict():
    client = NetworkClient()
    results = []
    async for chunk in client.stream_request("file:///etc/passwd", {"prompt": "test"}):
        results.append(chunk)

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["error_type"] == "ValueError"
    assert "Invalid URL scheme" in results[0]["message"]
