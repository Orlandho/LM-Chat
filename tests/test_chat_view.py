# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas unitarias automatizadas para la interfaz IChatView y el modelo ChatModel (ui/chat_window.py y ui/models.py).
Utiliza los mocks de omni.ui definidos en tests/conftest.py.
"""

import pytest
from unittest.mock import MagicMock
from core.interfaces import IChatView
from ui.models import ChatModel
from ui.chat_window import ChatWindow, ChatDelegate


class TestChatModel:
    """Pruebas unitarias para el modelo de estado ChatModel."""

    def test_model_initialization(self):
        model = ChatModel()
        assert model.current_provider == "LM Studio"
        assert model.current_model == "local-model"
        assert model.status == "Listo"
        assert not model.is_loading
        assert len(model.messages) == 0

    def test_add_and_clear_messages(self):
        model = ChatModel()
        msg = model.add_message("user", "Hola Agente")
        assert len(model.messages) == 1
        assert msg.role == "user"
        assert msg.content == "Hola Agente"

        model.add_message("assistant", "Hola Usuario")
        assert len(model.messages) == 2

        model.clear_messages()
        assert len(model.messages) == 0

    def test_provider_and_model_switching(self):
        model = ChatModel()
        model.set_provider("Ollama")
        assert model.current_provider == "Ollama"
        assert model.current_model == "llama3:latest"

        model.set_model("codellama:7b")
        assert model.current_model == "codellama:7b"

    def test_status_update(self):
        model = ChatModel()
        model.set_status("Generando...", is_loading=True)
        assert model.status == "Generando..."
        assert model.is_loading

        model.set_status("Auto-corrigiendo", is_loading=True)
        assert model.status == "Auto-corrigiendo"

        model.set_status("Listo", is_loading=False)
        assert model.status == "Listo"
        assert not model.is_loading

    def test_listeners_subscription(self):
        model = ChatModel()
        listener_mock = MagicMock()
        model.subscribe(listener_mock)

        model.add_message("user", "Test")
        listener_mock.assert_called_once()

        model.unsubscribe(listener_mock)
        model.set_status("Generando...")
        assert listener_mock.call_count == 1


class TestChatView:
    """Pruebas unitarias para ChatWindow e IChatView."""

    def test_chat_window_implements_ichat_view(self):
        window = ChatWindow()
        assert isinstance(window, IChatView)

    def test_set_submit_callback_registration_and_trigger(self):
        callback_mock = MagicMock()
        window = ChatWindow()
        window.set_submit_callback(callback_mock)

        # Simular envío a través del delegado
        window._delegate.on_submit("Crear un cubo 3D")
        callback_mock.assert_called_once_with("Crear un cubo 3D")

    def test_append_message(self):
        window = ChatWindow()
        window.append_message("user", "Hola desde test")
        assert len(window._model.messages) == 1
        assert window._model.messages[0].content == "Hola desde test"

        window.append_message("assistant", "Respuesta simulada")
        assert len(window._model.messages) == 2
        assert window._model.messages[1].role == "assistant"

    def test_update_status_and_badges(self):
        window = ChatWindow()

        # Probar cambio a estado Generando
        window.update_status("Generando...", is_loading=True)
        assert window._model.status == "Generando..."
        assert window._model.is_loading

        # Probar cambio a estado Auto-corrigiendo
        window.update_status("Auto-corrigiendo", is_loading=True)
        assert window._model.status == "Auto-corrigiendo"

        # Probar retorno a estado Listo
        window.update_status("Listo", is_loading=False)
        assert window._model.status == "Listo"

    def test_markdown_code_parsing(self):
        window = ChatWindow()
        text_with_code = "Aquí tienes el código:\n```python\nimport omni.usd\nprint('Hello')\n```\nFin del script."
        blocks = window._parse_markdown(text_with_code)

        assert len(blocks) == 3
        assert blocks[0][0] == "text"
        assert blocks[1][0] == "code"
        assert "[python]" in blocks[1][1]
        assert "import omni.usd" in blocks[1][1]
        assert blocks[2][0] == "text"

    def test_streaming_append_to_last_message(self):
        window = ChatWindow()
        window.append_message("assistant", "Inicio de la respuesta")

        label_mock = MagicMock()
        label_mock.text = "Inicio de la respuesta"
        window._message_labels.append(label_mock)

        window.append_to_last_message(" y continuación del stream.")
        assert label_mock.text == "Inicio de la respuesta y continuación del stream."

    def test_destroy_cleanup(self):
        window = ChatWindow()
        window.destroy()
        assert window._window is None
