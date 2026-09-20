# -*- coding: utf-8 -*-

import asyncio
import io
import json
import pytest
from unittest.mock import patch, MagicMock

from logic.network_client import NetworkClient


def test_make_sync_request_invalid_url_scheme():
    client = NetworkClient()

    # Test file:// protocol rejection
    res_file = client.make_sync_request("file:///etc/passwd", {"key": "val"})
    assert res_file["success"] is False
    assert res_file["error_type"] == "ValueError"
    assert "Invalid URL scheme" in res_file["message"]

    # Test ftp:// protocol rejection
    res_ftp = client.make_sync_request("ftp://example.com/test", {})
    assert res_ftp["success"] is False
    assert res_ftp["error_type"] == "ValueError"
    assert "Invalid URL scheme" in res_ftp["message"]

    # Test non-string input
    res_none = client.make_sync_request(None, {})
    assert res_none["success"] is False
    assert res_none["error_type"] == "ValueError"
    assert "string" in res_none["message"]


@pytest.mark.asyncio
async def test_stream_request_invalid_url_scheme():
    client = NetworkClient()

    chunks = []
    async for item in client.stream_request("file:///C:/Windows/system32/cmd.exe", {}):
        chunks.append(item)

    assert len(chunks) == 1
    assert chunks[0]["success"] is False
    assert chunks[0]["error_type"] == "ValueError"
    assert "Invalid URL scheme" in chunks[0]["message"]


def test_make_sync_request_valid_url_mocked():
    client = NetworkClient()
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "ok"}).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        res = client.make_sync_request("http://localhost:1234/v1/chat", {"prompt": "hello"})
        assert res["success"] is True
        assert res["data"] == {"response": "ok"}


@pytest.mark.asyncio
async def test_stream_request_valid_url_mocked():
    client = NetworkClient()

    fake_lines = [
        b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n',
        b'data: [DONE]\n'
    ]
    mock_response = MagicMock()
    mock_response.__iter__.return_value = iter(fake_lines)
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        chunks = []
        async for chunk in client.stream_request("https://api.example.com/v1/chat", {"prompt": "test"}):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["success"] is True
        assert chunks[0]["data"]["choices"][0]["delta"]["content"] == "Hello"
