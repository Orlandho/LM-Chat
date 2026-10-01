# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for new LLM providers in InferenceRouter:
OpenAI API, Claude API, and NVIDIA Spark.
"""

import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import aiohttp

from logic.inference_router import InferenceRouter


class TestInferenceRouterNewProviders(unittest.IsolatedAsyncioTestCase):
    """Pruebas exhaustivas para OpenAI, Claude y NVIDIA Spark en InferenceRouter."""

    async def test_openai_initialization_and_headers(self):
        """Verifica la inicialización por defecto y cabeceras para OpenAI."""
        router = InferenceRouter(provider="openai", api_key="sk-test-key-openai")
        self.assertEqual(router.provider, "openai")
        self.assertEqual(router.base_url, "https://api.openai.com/v1")
        self.assertEqual(router.model, "gpt-4o")

        headers = router.get_headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-test-key-openai")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")

        url = router.get_endpoint_url("/chat/completions")
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")

    async def test_claude_initialization_headers_and_endpoint(self):
        """Verifica que Claude use /messages y cabeceras x-api-key y anthropic-version."""
        router = InferenceRouter(provider="claude", api_key="sk-ant-test-key")
        self.assertEqual(router.provider, "claude")
        self.assertEqual(router.base_url, "https://api.anthropic.com/v1")
        self.assertEqual(router.model, "claude-3-7-sonnet-latest")

        headers = router.get_headers()
        self.assertEqual(headers["x-api-key"], "sk-ant-test-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", headers)

        # Debe redirigir automáticamente de /chat/completions al endpoint oficial /messages
        url = router.get_endpoint_url("/chat/completions")
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")

    async def test_claude_payload_preparation(self):
        """Verifica que los mensajes se adapten al formato requerido por Anthropic."""
        router = InferenceRouter(provider="claude")
        messages = [
            {"role": "system", "content": "Eres un asistente de OpenUSD."},
            {"role": "user", "content": "Crea una esfera en /World/Sphere."},
        ]

        payload = router._prepare_payload(messages, temperature=0.5, stream=False)
        self.assertEqual(payload["model"], "claude-3-7-sonnet-latest")
        self.assertEqual(payload["system"], "Eres un asistente de OpenUSD.")
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["messages"][0]["content"], "Crea una esfera en /World/Sphere.")
        self.assertEqual(payload["temperature"], 0.5)

    @patch("aiohttp.ClientSession.post")
    async def test_claude_non_streaming_response_translation(self, mock_post):
        """Verifica que la respuesta nativa de Claude se normalice al formato estándar."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = '''{
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Aquí tienes el código Python."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 20, "output_tokens": 15}
        }'''
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="claude", api_key="sk-ant-key")
        res = await router.chat_completions([{"role": "user", "content": "Hola"}])

        self.assertTrue(res["success"])
        self.assertIn("choices", res["data"])
        self.assertEqual(
            res["data"]["choices"][0]["message"]["content"],
            "Aquí tienes el código Python.",
        )
        self.assertEqual(res["data"]["choices"][0]["message"]["role"], "assistant")

    @patch("aiohttp.ClientSession.post")
    async def test_claude_streaming_sse_translation(self, mock_post):
        """Verifica que el stream SSE de Anthropic se transforme en delta chunks estándar."""
        async def mock_sse_stream():
            events = [
                b'event: message_start\n',
                b'data: {"type": "message_start", "message": {"id": "msg_1"}}\n',
                b'event: content_block_delta\n',
                b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hola "}}\n',
                b'event: content_block_delta\n',
                b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Omniverse!"}}\n',
                b'event: message_stop\n',
                b'data: {"type": "message_stop"}\n',
            ]
            for e in events:
                yield e

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content = mock_sse_stream()
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="claude", api_key="sk-ant-key")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0]["success"])
        self.assertEqual(chunks[0]["data"]["choices"][0]["delta"]["content"], "Hola ")
        self.assertEqual(chunks[1]["data"]["choices"][0]["delta"]["content"], "Omniverse!")

    async def test_nvidia_spark_initialization_and_headers(self):
        """Verifica la inicialización por defecto y cabeceras para NVIDIA Spark / NIM."""
        router = InferenceRouter(provider="nvidia_spark", api_key="nvapi-test-spark-key")
        self.assertEqual(router.provider, "nvidia_spark")
        self.assertEqual(router.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(router.model, "nvidia/llama-3.1-nemotron-70b-instruct")

        headers = router.get_headers()
        self.assertEqual(headers["Authorization"], "Bearer nvapi-test-spark-key")

        url = router.get_endpoint_url("/chat/completions")
        self.assertEqual(url, "https://integrate.api.nvidia.com/v1/chat/completions")

    async def test_env_var_fallback_for_api_keys(self):
        """Verifica que el router resuelva credenciales desde las variables de entorno correspondientes."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-env-openai",
            "ANTHROPIC_API_KEY": "sk-env-anthropic",
            "NVIDIA_API_KEY": "nvapi-env-nvidia",
        }):
            router_openai = InferenceRouter(provider="openai")
            self.assertEqual(router_openai.get_headers()["Authorization"], "Bearer sk-env-openai")

            router_claude = InferenceRouter(provider="claude")
            self.assertEqual(router_claude.get_headers()["x-api-key"], "sk-env-anthropic")

            router_nvidia = InferenceRouter(provider="nvidia_spark")
            self.assertEqual(router_nvidia.get_headers()["Authorization"], "Bearer nvapi-env-nvidia")

    @patch("aiohttp.ClientSession.post")
    async def test_sse_streaming_without_space_after_colon(self, mock_post):
        """Verifica que el router parsee correctamente streams SSE donde data: no tiene espacio posterior."""
        async def mock_sse_stream():
            events = [
                b'data:{"choices":[{"delta":{"content":"NVIDIA"}}]}\n',
                b'data:{"choices":[{"delta":{"content":" Spark"}}]}\n',
                b'data:[DONE]\n',
            ]
            for e in events:
                yield e

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content = mock_sse_stream()
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="nvidia_spark", api_key="test-key")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["data"]["choices"][0]["delta"]["content"], "NVIDIA")
        self.assertEqual(chunks[1]["data"]["choices"][0]["delta"]["content"], " Spark")


if __name__ == "__main__":
    unittest.main()
