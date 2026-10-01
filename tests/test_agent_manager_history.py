# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas de sincronización de contexto conversacional para AgentManager.
Verifica que las sesiones cargadas actualizan la memoria del LLM reteniendo el system prompt.
"""

import pytest
from core.interfaces import ChatMessage
from logic.agent_manager import AgentManager


class TestAgentManagerHistorySync:
    """Pruebas de contexto para AgentManager."""

    def test_load_session_messages_preserves_system_prompt(self):
        manager = AgentManager()
        assert len(manager._messages) == 1
        assert manager._messages[0]["role"] == "system"

        messages = [
            ChatMessage(role="user", content="Hola, soy un diseñador 3D"),
            ChatMessage(role="assistant", content="¡Hola! ¿En qué puedo asistirte en Omniverse?"),
            ChatMessage(role="user", content="Necesito crear un robot"),
        ]

        manager.load_session_messages(messages)

        assert len(manager._messages) == 4
        assert manager._messages[0]["role"] == "system"
        assert manager._messages[1]["role"] == "user"
        assert manager._messages[1]["content"] == "Hola, soy un diseñador 3D"
        assert manager._messages[2]["role"] == "assistant"
        assert manager._messages[3]["role"] == "user"

    def test_load_session_messages_with_dicts(self):
        manager = AgentManager()
        raw_msgs = [
            {"role": "user", "content": "Pregunta rápida"},
            {"role": "assistant", "content": "Respuesta directa"},
        ]
        manager.load_session_messages(raw_msgs)
        assert len(manager._messages) == 3
        assert manager._messages[0]["role"] == "system"
        assert manager._messages[1]["content"] == "Pregunta rápida"

    def test_reset_conversation_clears_history_retaining_prompt(self):
        manager = AgentManager()
        manager.load_session_messages([
            ChatMessage(role="user", content="Mensaje previo"),
            ChatMessage(role="assistant", content="Respuesta previa"),
        ])
        assert len(manager._messages) == 3

        manager.reset_conversation()
        assert len(manager._messages) == 1
        assert manager._messages[0]["role"] == "system"

    def test_load_session_messages_handles_system_prompt_without_duplication(self):
        manager = AgentManager()
        # Mensajes que contienen rol system con el prompt por defecto
        messages = [
            ChatMessage(role="system", content=manager._system_prompt),
            ChatMessage(role="user", content="Prompt 1"),
        ]
        manager.load_session_messages(messages)
        # No debe duplicar el system prompt
        assert len(manager._messages) == 2
        assert manager._messages[0]["role"] == "system"
        assert manager._messages[1]["role"] == "user"

        # Mensajes con prompt del sistema personalizado
        custom_system = "Prompt personalizado especializado"
        manager.load_session_messages([
            ChatMessage(role="system", content=custom_system),
            ChatMessage(role="user", content="Prompt 2"),
        ])
        assert len(manager._messages) == 2
        assert manager._messages[0]["content"] == custom_system
