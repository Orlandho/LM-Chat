# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas de la interfaz gráfica ChatWindow y el delegado ChatDelegate
en relación con la barra de sesiones y persistencia del historial local.
"""

import pytest
from unittest.mock import MagicMock
from core.interfaces import ChatSession, ChatMessage
from ui.models import ChatModel
from ui.chat_window import ChatWindow, ChatDelegate
from logic.chat_history import LocalChatHistoryManager


class TestChatWindowHistoryIntegration:
    """Pruebas para ChatWindow y ChatDelegate con historial local."""

    def test_delegate_session_lifecycle_callbacks(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        delegate = ChatDelegate(model=model)

        session_changed_mock = MagicMock()
        delegate.set_session_changed_callback(session_changed_mock)

        # Crear nueva sesión
        sess1 = delegate.on_new_session(title="Sesión Alfa")
        assert sess1 is not None
        session_changed_mock.assert_called_once_with(sess1)

        # Agregar mensaje a sesión 1
        model.add_message("user", "Prompt en Alfa")

        # Crear segunda sesión
        session_changed_mock.reset_mock()
        sess2 = delegate.on_new_session(title="Sesión Beta")
        assert sess2.session_id != sess1.session_id
        session_changed_mock.assert_called_once_with(sess2)

        # Cambiar de vuelta a sesión 1
        session_changed_mock.reset_mock()
        switched = delegate.on_session_changed(sess1.session_id)
        assert switched is True
        session_changed_mock.assert_called_once()
        loaded_sess = session_changed_mock.call_args[0][0]
        assert loaded_sess.session_id == sess1.session_id
        assert len(loaded_sess.messages) == 1

        # Eliminar sesión 1
        session_changed_mock.reset_mock()
        deleted = delegate.on_delete_session(sess1.session_id)
        assert deleted is True
        session_changed_mock.assert_called_once()

    def test_chat_window_rebuild_messages_ui(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        window = ChatWindow(model=model)

        # Agregar mensajes al modelo
        model.add_message("user", "Pregunta 1")
        model.add_message("assistant", "Respuesta 1")

        # Reconstruir la UI
        window.rebuild_messages_ui()
        assert len(window._model.messages) == 2

    def test_finalize_last_assistant_message_avoids_duplication(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        window = ChatWindow(model=model)

        # Simular envío de usuario
        model.add_message("user", "Crea una escena")
        assert len(model.messages) == 1

        # Finalizar respuesta del asistente
        window.finalize_last_assistant_message("Escena creada con éxito.")
        assert len(model.messages) == 2
        assert model.messages[-1].role == "assistant"
        assert model.messages[-1].content == "Escena creada con éxito."

        # Llamar de nuevo con el mismo texto no debe duplicar el mensaje
        window.finalize_last_assistant_message("Escena creada con éxito.")
        assert len(model.messages) == 2

    def test_window_session_actions_triggers_rebuild(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        window = ChatWindow(model=model)

        # Crear mensaje
        model.add_message("user", "Test mensaje")
        assert len(model.messages) == 1

        # Clic en Nuevo Chat
        window._handle_new_session_clicked()
        assert len(model.messages) == 0

        # Clic en Limpiar
        model.add_message("user", "Otro mensaje")
        assert len(model.messages) == 1
        window._handle_clear_session_clicked()
        assert len(model.messages) == 0

    def test_delete_inactive_session_preserves_active_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        delegate = ChatDelegate(model=model)

        s_active = model.new_session("Sesión Activa")
        model.add_message("user", "Mensaje que debe preservarse")
        s_other = mgr.create_session("Sesión Secundaria")

        # Eliminar s_other no debe alterar s_active
        success = delegate.on_delete_session(s_other.session_id)
        assert success is True
        assert model.current_session_id == s_active.session_id
        assert len(model.messages) == 1
        assert model.messages[0].content == "Mensaje que debe preservarse"

    def test_clear_session_triggers_sync_callback(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)
        window = ChatWindow(model=model)

        sync_mock = MagicMock()
        window.set_session_changed_callback(sync_mock)

        model.add_message("user", "Texto a borrar")
        window._handle_clear_session_clicked()

        assert sync_mock.called
        cleared_sess = sync_mock.call_args[0][0]
        assert len(cleared_sess.messages) == 0
