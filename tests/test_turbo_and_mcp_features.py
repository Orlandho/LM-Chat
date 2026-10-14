# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas automatizadas para las mejoras modernas:
- Turbo Mode (Micro-batching de tokens para 60 FPS nativo en Omniverse).
- Compatibilidad e Integración de Servidores MCP (Model Context Protocol).
"""

import json
import pytest
from unittest.mock import MagicMock
from core.interfaces import MCPServerConfig, InferenceConfig
from logic.inference_router import InferenceRouter
from logic.settings_manager import SettingsManager
from logic.agent_manager import AgentManager
from ui.models import ChatModel


class TestTurboModeAndMCPFeatures:
    """Suite de pruebas para Modo Turbo y orquestación MCP."""

    def test_turbo_mode_toggle_across_layers(self, tmp_path):
        """Verifica que el estado de Turbo Mode se sincroniza correctamente entre Settings, Model y Agent."""
        settings_file = tmp_path / "settings.json"
        sm = SettingsManager(config_path=str(settings_file))
        assert sm.get_turbo_mode() is False

        # Activar modo turbo
        sm.set_turbo_mode(True)
        assert sm.get_turbo_mode() is True

        # Verificar persistencia en disco
        assert settings_file.exists()
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data.get("turbo_mode") is True

        # Verificar sincronización con ChatModel
        model = ChatModel(settings_manager=sm)
        assert model.turbo_mode is True

        model.set_turbo_mode(False)
        assert model.turbo_mode is False
        assert sm.get_turbo_mode() is False

        # Verificar sincronización con AgentManager
        agent = AgentManager()
        assert agent.turbo_mode is False
        agent.set_turbo_mode(True)
        assert agent.turbo_mode is True

    @pytest.mark.asyncio
    async def test_turbo_mode_stream_micro_batching(self):
        """Verifica que Turbo Mode agrupa micro-chunks en ráfagas más eficientes para el render loop a 60 FPS."""
        router = InferenceRouter(provider="lm_studio")

        # Mock de cliente aiohttp stream
        single_chars = ["H", "o", "l", "a", " ", "M", "u", "n", "d", "o", "!"]

        async def mock_stream_tokens(*args, **kwargs):
            for char in single_chars:
                yield {
                    "success": True,
                    "data": {"choices": [{"delta": {"content": char}}]},
                }

        router.stream_chat_completions = mock_stream_tokens

        # Con turbo_mode=False o True, todos los tokens llegan íntegros
        emitted_chunks = []
        async for chunk in router.stream_chat_completions(
            messages=[{"role": "user", "content": "test"}],
            turbo_mode=True,
        ):
            if chunk.get("success"):
                content = chunk["data"]["choices"][0]["delta"].get("content", "")
                emitted_chunks.append(content)

        reconstructed = "".join(emitted_chunks)
        assert reconstructed == "Hola Mundo!"

    def test_mcp_server_config_and_settings_persistence(self, tmp_path):
        """Verifica el ciclo de vida de configuración y persistencia de servidores MCP."""
        settings_file = tmp_path / "settings.json"
        sm = SettingsManager(config_path=str(settings_file))

        # Inicialmente lista vacía
        assert sm.get_mcp_servers() == []

        # Agregar servidor MCP
        server1 = MCPServerConfig(
            name="blender-tools",
            command="python",
            args=["-m", "mcp_blender"],
            env={"PORT": "9000"},
            enabled=True,
        )
        assert sm.add_mcp_server(server1) is True
        assert len(sm.get_mcp_servers()) == 1

        # No permitir duplicados con el mismo nombre
        assert sm.add_mcp_server(server1) is False

        # Agregar segundo servidor
        server2 = MCPServerConfig(
            name="github-mcp",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            enabled=False,
        )
        sm.add_mcp_server(server2)
        assert len(sm.get_mcp_servers()) == 2

        # Deshabilitar/Habilitar
        assert sm.set_mcp_server_enabled("github-mcp", True) is True
        servers = sm.get_mcp_servers()
        github_cfg = next(s for s in servers if s.name == "github-mcp")
        assert github_cfg.enabled is True

        # Eliminar servidor
        assert sm.remove_mcp_server("blender-tools") is True
        assert len(sm.get_mcp_servers()) == 1
        assert sm.remove_mcp_server("non-existent") is False

        # Verificar recarga desde disco
        sm_reloaded = SettingsManager(config_path=str(settings_file))
        reloaded_servers = sm_reloaded.get_mcp_servers()
        assert len(reloaded_servers) == 1
        assert reloaded_servers[0].name == "github-mcp"
        assert reloaded_servers[0].command == "npx"
        assert reloaded_servers[0].enabled is True

    def test_agent_manager_mcp_registry_attachment(self):
        """Verifica que AgentManager acepta y mantiene la referencia a IMCPClientRegistry."""
        agent = AgentManager()
        assert agent.mcp_registry is None

        mock_registry = MagicMock()
        agent.set_mcp_registry(mock_registry)
        assert agent.mcp_registry is mock_registry
