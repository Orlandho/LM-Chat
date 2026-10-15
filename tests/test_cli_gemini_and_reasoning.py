# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas para integración de Gemini, modelos de razonamiento y comandos ampliados en CLI.
"""

import sys
import pytest
from unittest.mock import patch, AsyncMock
from cli.omni_harness import parse_arguments, LMChatCLI
from logic.inference_router import InferenceRouter, is_reasoning_model
from logic.chat_history import LocalChatHistoryManager


class TestCLIGeminiAndReasoning:
    """Verifica compatibilidad de proveedores y modelos de razonamiento en CLI."""

    def test_parse_arguments_supports_gemini_and_providers(self):
        """Verifica que -p acepte gemini, google, cluster, local_cluster y cloud."""
        test_args = [
            "lmchat_cli.py",
            "-p", "gemini",
            "-m", "gemini-3.8-flash",
            "-k", "AQ.test_key_123",
            "--prompt", "Hola Gemini"
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.provider == "gemini"
            assert args.model == "gemini-3.8-flash"
            assert args.api_key == "AQ.test_key_123"
            assert args.prompt == "Hola Gemini"

    def test_parse_arguments_supports_cluster_providers(self):
        """Verifica que el parser acepte cluster y local_cluster."""
        with patch.object(sys, "argv", ["lmchat_cli.py", "-p", "cluster"]):
            args = parse_arguments()
            assert args.provider == "cluster"

        with patch.object(sys, "argv", ["lmchat_cli.py", "-p", "local_cluster"]):
            args = parse_arguments()
            assert args.provider == "local_cluster"

    def test_gemini_reasoning_model_detection(self):
        """Verifica que la familia Gemini 3 sea detectada como modelo con razonamiento."""
        assert is_reasoning_model("gemini-3.8-flash") is True
        assert is_reasoning_model("gemini-3.7-flash") is True
        assert is_reasoning_model("gemini-3-flash-preview") is True
        assert is_reasoning_model("gemini-2.0-flash") is False

    @pytest.mark.asyncio
    async def test_cli_execute_prompt_streams_reasoning_and_content(self, tmp_path, capsys):
        """Verifica que execute_prompt transmita chunks de pensamiento y de respuesta."""
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        router = InferenceRouter(provider="gemini", model="gemini-3.8-flash")

        async def mock_stream(messages):
            yield {
                "success": True,
                "data": {
                    "choices": [
                        {"delta": {"content": "", "reasoning_content": "Pensando en la jerarquía USD..."}}
                    ]
                },
            }
            yield {
                "success": True,
                "data": {
                    "choices": [
                        {"delta": {"content": "Aquí está el prim /World/Mesh"}}
                    ]
                },
            }

        router.stream_chat_completions = mock_stream
        cli = LMChatCLI(router=router, system_prompt="Test Prompt", history_manager=mgr)

        full_resp = await cli.execute_prompt("Crea un prim")
        assert full_resp == "Aquí está el prim /World/Mesh"
        captured = capsys.readouterr()
        assert "Pensando en la jerarquía USD..." in captured.out
        assert "Aquí está el prim /World/Mesh" in captured.out

    @pytest.mark.asyncio
    async def test_inference_router_retries_transient_503(self):
        """Verifica que un fallo 503 transitorio sea reintentado y se recupere."""
        router = InferenceRouter(provider="gemini", model="gemini-3.8-flash")

        resp_503 = AsyncMock()
        resp_503.status = 503
        resp_503.text.return_value = '{"error": {"code": 503, "message": "High demand spike"}}'

        resp_200 = AsyncMock()
        resp_200.status = 200
        resp_200.text.return_value = '{"choices": [{"message": {"role": "assistant", "content": "PONG"}}]}'

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.side_effect = [resp_503, resp_200]
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await router.chat_completions([{"role": "user", "content": "PING"}])
                assert result["success"] is True
                assert result["data"]["choices"][0]["message"]["content"] == "PONG"
                assert mock_sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_stream_gracefully_handles_server_disconnect_after_tokens(self):
        """Verifica que si el servidor cierra la conexión SSE tras enviar tokens, se complete limpiamente."""
        import aiohttp
        router = InferenceRouter(provider="gemini", model="gemini-3.8-flash")

        class MockDisconnectingStream:
            def __init__(self):
                self.items = [
                    b'data: {"choices": [{"delta": {"content": "Hola"}}]}\n\n',
                    b'data: {"choices": [{"delta": {"content": " mundo"}}]}\n\n'
                ]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index < len(self.items):
                    item = self.items[self.index]
                    self.index += 1
                    return item
                raise aiohttp.ClientConnectionError("Connection closed unexpectedly by peer")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content = MockDisconnectingStream()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            tokens = []
            async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
                if chunk.get("success"):
                    tokens.append(chunk["data"]["choices"][0]["delta"].get("content", ""))
                else:
                    pytest.fail(f"Stream yielded failure unexpectedly: {chunk}")
            assert "".join(tokens) == "Hola mundo"

    @pytest.mark.asyncio
    async def test_stream_retries_transient_connection_error_if_zero_tokens(self):
        """Verifica que si la conexión se cae antes de recibir tokens, se reintente con backoff."""
        import aiohttp
        router = InferenceRouter(provider="gemini", model="gemini-3.8-flash")

        class MockFailingFirstStream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise aiohttp.ClientConnectionError("Connection reset by peer before headers/payload")

        class MockSuccessfulStream:
            def __init__(self):
                self.items = [
                    b'data: {"choices": [{"delta": {"content": "Recuperado"}}]}\n\n',
                    b'data: [DONE]\n\n'
                ]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index < len(self.items):
                    item = self.items[self.index]
                    self.index += 1
                    return item
                raise StopAsyncIteration

        resp_fail = AsyncMock()
        resp_fail.status = 200
        resp_fail.content = MockFailingFirstStream()

        resp_ok = AsyncMock()
        resp_ok.status = 200
        resp_ok.content = MockSuccessfulStream()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.side_effect = [resp_fail, resp_ok]
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                tokens = []
                async for chunk in router.stream_chat_completions([{"role": "user", "content": "Hola"}]):
                    if chunk.get("success"):
                        tokens.append(chunk["data"]["choices"][0]["delta"].get("content", ""))
                assert "".join(tokens) == "Recuperado"
                assert mock_sleep.await_count == 1


    def test_nvidia_omniverse_skills_integrity(self):
        """Verifica que los skills oficiales de NVIDIA para Omniverse estén presentes y tengan SKILL.md válido."""
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skills_dir = os.path.join(repo_root, "skills")
        expected_skills = [
            "isaac-mission-control-showcase",
            "omniverse-cad-to-simready",
            "omniverse-realtime-viewer",
            "omniverse-usd-performance-tuning",
            "rtx-remix-modding",
        ]
        assert os.path.exists(skills_dir), "El directorio skills/ debe existir en la raíz"
        for skill_name in expected_skills:
            skill_path = os.path.join(skills_dir, skill_name, "SKILL.md")
            assert os.path.exists(skill_path), f"El skill {skill_name} debe contener SKILL.md"
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert content.startswith("---"), f"{skill_name} debe contener frontmatter YAML"
                assert "name: " in content, f"{skill_name} debe definir un campo name en frontmatter"
                assert "description: " in content, f"{skill_name} debe definir description en frontmatter"

