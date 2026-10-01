# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas de integración entre LMChatExtension, historial de chats y sincronización con AgentManager.
"""

import pytest
from unittest.mock import MagicMock
from logic.chat_history import LocalChatHistoryManager
from extension import LMChatExtension


class TestExtensionHistoryIntegration:
    """Pruebas para el ciclo de vida y sincronización de sesiones en LMChatExtension."""

    def test_extension_startup_and_provider_sync(self, tmp_path, monkeypatch):
        # Configurar directorio de sesiones aislado
        monkeypatch.setenv("LM_CHAT_STORAGE_PATH", str(tmp_path))

        ext = LMChatExtension()
        ext.on_startup("test_ext_id")

        assert ext._history_manager is not None
        assert ext._agent_manager is not None
        assert ext._model is not None
        assert ext._chat_window is not None

        # Verificar que el router inicia con lm_studio
        assert ext._agent_manager.router.provider == "lm_studio"

        # Cambiar de proveedor en el modelo debe propagarse a AgentManager
        ext._model.set_provider("Ollama")
        assert ext._agent_manager.router.provider == "ollama"

        # Shutdown limpia las referencias
        ext.on_shutdown()
        assert ext._chat_window is None
        assert ext._agent_manager is None

    def test_extension_startup_restores_latest_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LM_CHAT_STORAGE_PATH", str(tmp_path))

        # Crear sesiones previas en disco
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        dummy = mgr.create_session("dummy")
        s = mgr.create_session("Sesión Previa", metadata={"provider": "vllm", "model": "Qwen/Qwen2.5-Coder-32B-Instruct"})
        from core.interfaces import ChatMessage
        s.messages = [
            ChatMessage(role="user", content="Pregunta guardada"),
            ChatMessage(role="assistant", content="Respuesta guardada"),
        ]
        mgr.save_session(s)

        ext = LMChatExtension()
        ext.on_startup("test_ext_id")

        # La extensión debe haber cargado la sesión más reciente
        assert ext._model.current_session_id == s.session_id
        assert len(ext._model.messages) == 2
        assert ext._model.messages[0].content == "Pregunta guardada"

        # AgentManager debe tener el contexto cargado
        assert len(ext._agent_manager._messages) == 3
        assert ext._agent_manager._messages[1]["content"] == "Pregunta guardada"
        assert ext._agent_manager.router.provider == "vllm"

        ext.on_shutdown()
