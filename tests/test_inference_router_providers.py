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

    @patch("aiohttp.ClientSession.post")
    async def test_stream_http_error_diagnostics(self, mock_post):
        """Verifica que un error HTTP durante streaming produzca un diagnóstico estructurado."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text.return_value = '{"error": {"message": "Invalid API key"}}'
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="openai", api_key="bad-key")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        err_chunk = chunks[0]
        self.assertFalse(err_chunk["success"])
        self.assertEqual(err_chunk["status"], 401)
        self.assertIn("diagnostic", err_chunk)
        self.assertIn("diagnostic_md", err_chunk)
        self.assertIn("### ⚠️ Diagnóstico LM-Chat:", err_chunk["diagnostic_md"])
        self.assertIn("OPENAI_API_KEY", err_chunk["diagnostic_md"])

    @patch("aiohttp.ClientSession.post")
    async def test_stream_connection_refused_diagnostics(self, mock_post):
        """Verifica que una falla de conexión en streaming genere diagnóstico accionable."""
        mock_post.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        router = InferenceRouter(provider="ollama")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        err_chunk = chunks[0]
        self.assertFalse(err_chunk["success"])
        self.assertEqual(err_chunk["error_type"], "ConnectionError")
        self.assertIn("diagnostic_md", err_chunk)
        self.assertIn("ollama serve", err_chunk["diagnostic_md"])

    async def test_google_gemini_provider_configuration(self):
        """Verifica la configuración del endpoint compatible de Google Gemini."""
        router = InferenceRouter(provider="gemini", api_key="test-gemini-key")
        self.assertEqual(router.provider, "gemini")
        self.assertEqual(router.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertEqual(router.model, "gemini-3.8-flash")

        headers = router.get_headers()
        self.assertEqual(headers["Authorization"], "Bearer test-gemini-key")
        self.assertEqual(
            router.get_endpoint_url("/chat/completions"),
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )

    async def test_display_name_provider_resolution(self):
        """Verifica que los nombres de la UI (OpenAI API, Claude API, etc.) resuelvan URLs y modelos correctos."""
        # Google Gemini API
        r_gem = InferenceRouter(provider="Google Gemini API")
        self.assertEqual(r_gem.provider, "gemini")
        self.assertEqual(r_gem.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertEqual(r_gem.model, "gemini-3.8-flash")

        # OpenAI API
        r_oai = InferenceRouter(provider="OpenAI API")
        self.assertEqual(r_oai.provider, "openai")
        self.assertEqual(r_oai.base_url, "https://api.openai.com/v1")
        self.assertEqual(r_oai.model, "gpt-4o")

        # Claude API
        r_cld = InferenceRouter(provider="Claude API")
        self.assertEqual(r_cld.provider, "claude")
        self.assertEqual(r_cld.base_url, "https://api.anthropic.com/v1")
        self.assertEqual(r_cld.model, "claude-3-7-sonnet-latest")
        self.assertTrue(r_cld._is_anthropic_direct())

        # NVIDIA Spark
        r_spk = InferenceRouter(provider="NVIDIA Spark")
        self.assertEqual(r_spk.provider, "nvidia_spark")
        self.assertEqual(r_spk.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(r_spk.model, "nvidia/llama-3.1-nemotron-70b-instruct")

    async def test_openai_reasoning_models_payload_adaptation(self):
        """Verifica que o1 y o3-mini no incluyan 'temperature' y transformen max_tokens a max_completion_tokens."""
        for m in ["o1", "o3-mini", "o1-mini", "o1-preview"]:
            router = InferenceRouter(provider="openai", model=m)
            payload = router._prepare_payload(
                messages=[{"role": "user", "content": "Razona esto"}],
                temperature=0.8,
                max_tokens=2048,
            )
            self.assertNotIn("temperature", payload, f"Modelo {m} no debe incluir temperature en payload")
            self.assertEqual(payload.get("max_completion_tokens"), 2048)
            self.assertNotIn("max_tokens", payload)

    async def test_anthropic_alternating_messages_sanitization(self):
        """Verifica que Claude fusione mensajes consecutivos del mismo rol y omita vacíos."""
        router = InferenceRouter(provider="claude")
        msgs = [
            {"role": "user", "content": "Primera parte"},
            {"role": "user", "content": "Segunda parte"},
            {"role": "assistant", "content": " "},  # Mensaje vacío debe descartarse
            {"role": "user", "content": "Tercera parte"},
        ]
        payload = router._prepare_payload(msgs)
        prepared_msgs = payload["messages"]
        self.assertEqual(len(prepared_msgs), 1)
        self.assertEqual(prepared_msgs[0]["role"], "user")
        self.assertEqual(prepared_msgs[0]["content"], "Primera parte\n\nSegunda parte\n\nTercera parte")

    @patch("aiohttp.ClientSession.post")
    async def test_claude_37_thinking_delta_streaming(self, mock_post):
        """Verifica que los chunks de tipo thinking_delta de Claude 3.7 Sonnet se procesen sin error."""
        async def mock_sse_stream():
            lines = [
                b'event: content_block_delta\n',
                b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Pensando la solucion..."}}\n',
                b'event: content_block_delta\n',
                b'data: {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Resultado final."}}\n',
                b'data: [DONE]\n',
            ]
            for line in lines:
                yield line

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content = mock_sse_stream()
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="claude")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Prueba thinking"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        # Primer chunk debe tener reasoning_content
        self.assertEqual(chunks[0]["data"]["choices"][0]["delta"].get("reasoning_content"), "Pensando la solucion...")
        # Segundo chunk debe tener content
        self.assertEqual(chunks[1]["data"]["choices"][0]["delta"].get("content"), "Resultado final.")

    @patch("aiohttp.ClientSession.post")
    async def test_deepseek_r1_null_content_streaming(self, mock_post):
        """Verifica que deltas con content=null en DeepSeek-R1 se normalicen a cadena vacía sin fallar."""
        async def mock_sse_stream():
            lines = [
                b'data: {"choices": [{"delta": {"content": null, "reasoning_content": "Paso 1..."}}]}\n',
                b'data: {"choices": [{"delta": {"content": "Respuesta definitiva."}}]}\n',
                b'data: [DONE]\n',
            ]
            for line in lines:
                yield line

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content = mock_sse_stream()
        mock_post.return_value.__aenter__.return_value = mock_response

        router = InferenceRouter(provider="ollama", model="deepseek-r1:8b")
        chunks = []
        async for chunk in router.stream_chat_completions([{"role": "user", "content": "Prueba R1"}]):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["data"]["choices"][0]["delta"]["content"], "")
        self.assertEqual(chunks[1]["data"]["choices"][0]["delta"]["content"], "Respuesta definitiva.")


if __name__ == "__main__":
    unittest.main()
