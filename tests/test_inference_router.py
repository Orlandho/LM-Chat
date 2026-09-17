# -*- coding: utf-8 -*-

"""
Unit Tests for InferenceRouter and Multi-Provider LLM Integration.
"""

import sys
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import aiohttp

from logic.inference_router import InferenceRouter
from logic.agent_manager import AgentManager


class TestInferenceRouter(unittest.IsolatedAsyncioTestCase):
    """Exhaustive Unit Tests for InferenceRouter."""

    async def asyncSetUp(self):
        self.router_lm = InferenceRouter(provider="lm_studio")
        self.router_ollama = InferenceRouter(provider="ollama")
        self.router_vllm = InferenceRouter(provider="vllm")
        self.router_cloud = InferenceRouter(
            provider="cloud",
            api_key="sk-test-key-12345",
            model="gpt-4o-mini",
            base_url="https://api.custom-cloud.com/v1",
        )

    def test_provider_initialization_defaults(self):
        """Test default URLs and models for each supported provider."""
        # LM Studio
        self.assertEqual(self.router_lm.provider, "lm_studio")
        self.assertEqual(self.router_lm.base_url, "http://localhost:1234/v1")
        self.assertEqual(self.router_lm.model, "local-model")
        self.assertIsNone(self.router_lm.api_key)

        # Ollama
        self.assertEqual(self.router_ollama.provider, "ollama")
        self.assertEqual(self.router_ollama.base_url, "http://localhost:11434/v1")
        self.assertEqual(self.router_ollama.model, "llama3")

        # vLLM (Enterprise Nemotron)
        self.assertEqual(self.router_vllm.provider, "vllm")
        self.assertEqual(self.router_vllm.base_url, "http://localhost:8000/v1")
        self.assertEqual(self.router_vllm.model, "nvidia/nemotron-4-70b-instruct")

        # Cloud with custom overrides
        self.assertEqual(self.router_cloud.provider, "cloud")
        self.assertEqual(self.router_cloud.base_url, "https://api.custom-cloud.com/v1")
        self.assertEqual(self.router_cloud.model, "gpt-4o-mini")
        self.assertEqual(self.router_cloud.api_key, "sk-test-key-12345")

    def test_endpoint_url_and_headers_generation(self):
        """Test constructing endpoint URLs and Authorization headers."""
        # Endpoint URL
        url_lm = self.router_lm.get_endpoint_url("/chat/completions")
        self.assertEqual(url_lm, "http://localhost:1234/v1/chat/completions")

        url_cloud = self.router_cloud.get_endpoint_url("chat/completions")
        self.assertEqual(url_cloud, "https://api.custom-cloud.com/v1/chat/completions")

        # Headers without API Key
        headers_lm = self.router_lm.get_headers()
        self.assertEqual(headers_lm.get("Content-Type"), "application/json; charset=utf-8")
        self.assertNotIn("Authorization", headers_lm)

        # Headers with API Key
        headers_cloud = self.router_cloud.get_headers()
        self.assertEqual(headers_cloud.get("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(headers_cloud.get("Authorization"), "Bearer sk-test-key-12345")

    def test_set_provider_dynamic_switch(self):
        """Test dynamically switching providers on an existing router."""
        router = InferenceRouter(provider="lm_studio")
        self.assertEqual(router.provider, "lm_studio")

        router.set_provider("ollama", model="qwen2.5-coder")
        self.assertEqual(router.provider, "ollama")
        self.assertEqual(router.base_url, "http://localhost:11434/v1")
        self.assertEqual(router.model, "qwen2.5-coder")

    def test_set_provider_invalid_url_scheme(self):
        """Test that non-HTTP/HTTPS base URLs are rejected for security (SSRF/LFI prevention)."""
        with self.assertRaises(ValueError):
            InferenceRouter(provider="cloud", base_url="file:///etc/passwd")

        router = InferenceRouter(provider="lm_studio")
        with self.assertRaises(ValueError):
            router.set_provider("cloud", base_url="ftp://malicious.host/v1")

    @patch("aiohttp.ClientSession.post")
    async def test_chat_completions_success(self, mock_post):
        """Test successful non-streaming chat completion request."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = '{"choices": [{"message": {"content": "Hello Omniverse!"}}]}'
        mock_post.return_value.__aenter__.return_value = mock_response

        messages = [{"role": "user", "content": "Hola"}]
        result = await self.router_lm.chat_completions(messages)

        self.assertTrue(result["success"])
        self.assertEqual(
            result["data"]["choices"][0]["message"]["content"], "Hello Omniverse!"
        )

    @patch("aiohttp.ClientSession.post")
    async def test_chat_completions_http_error(self, mock_post):
        """Test non-streaming completion when server returns HTTP error status."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"
        mock_post.return_value.__aenter__.return_value = mock_response

        messages = [{"role": "user", "content": "Hola"}]
        result = await self.router_lm.chat_completions(messages)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "HTTPError")
        self.assertEqual(result["status"], 500)

    @patch("aiohttp.ClientSession.post")
    async def test_chat_completions_connection_refused(self, mock_post):
        """Test fault tolerance when local server is offline (connection refused)."""
        mock_post.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        messages = [{"role": "user", "content": "Hola"}]
        result = await self.router_lm.chat_completions(messages)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "ConnectionError")
        self.assertIn("Conexión rehusada", result["message"])

    @patch("aiohttp.ClientSession.post")
    async def test_chat_completions_timeout(self, mock_post):
        """Test timeout handling when local server takes too long."""
        mock_post.side_effect = asyncio.TimeoutError()

        messages = [{"role": "user", "content": "Hola"}]
        result = await self.router_lm.chat_completions(messages)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "TimeoutError")
        self.assertIn("Tiempo de espera agotado", result["message"])

    @patch("aiohttp.ClientSession.post")
    async def test_stream_chat_completions_success(self, mock_post):
        """Test streaming chat completion yields parsed SSE chunks."""
        async def mock_async_iter():
            lines = [
                b'data: {"choices": [{"delta": {"content": "Hola "}}]}\n',
                b'data: {"choices": [{"delta": {"content": "Omniverse!"}}]}\n',
                b'data: [DONE]\n',
            ]
            for line in lines:
                yield line

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content = mock_async_iter()
        mock_post.return_value.__aenter__.return_value = mock_response

        messages = [{"role": "user", "content": "Hola"}]
        chunks = []
        async for chunk in self.router_lm.stream_chat_completions(messages):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0]["success"])
        self.assertEqual(
            chunks[0]["data"]["choices"][0]["delta"]["content"], "Hola "
        )
        self.assertEqual(
            chunks[1]["data"]["choices"][0]["delta"]["content"], "Omniverse!"
        )

    @patch("aiohttp.ClientSession.post")
    async def test_stream_chat_completions_connection_failure(self, mock_post):
        """Test streaming when local server connection fails."""
        mock_post.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        messages = [{"role": "user", "content": "Hola"}]
        chunks = []
        async for chunk in self.router_lm.stream_chat_completions(messages):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertFalse(chunks[0]["success"])
        self.assertEqual(chunks[0]["error_type"], "ConnectionError")


class TestAgentManagerIntegration(unittest.IsolatedAsyncioTestCase):
    """Tests for AgentManager integration with InferenceRouter."""

    async def test_agent_manager_with_inference_router(self):
        """Test AgentManager uses InferenceRouter and allows provider switching."""
        router = InferenceRouter(provider="ollama")
        agent_mgr = AgentManager(router=router)

        self.assertEqual(agent_mgr.router.provider, "ollama")

        # Switch provider
        agent_mgr.set_provider("vllm", model="nvidia/nemotron-70b")
        self.assertEqual(agent_mgr.router.provider, "vllm")
        self.assertEqual(agent_mgr.router.model, "nvidia/nemotron-70b")


if __name__ == "__main__":
    unittest.main()
