# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas de integración entre ChatModel y LocalChatHistoryManager.
Verifica persistencia automática, auto-titulado de sesiones, carga, eliminación,
cambio dinámico de proveedores/modelos por sesión y notificaciones a suscriptores.
"""

import pytest
from unittest.mock import MagicMock
from ui.models import ChatModel
from logic.chat_history import LocalChatHistoryManager
from core.interfaces import ChatMessage


class TestChatModelHistoryIntegration:
    """Pruebas de persistencia e interacción de sesiones en ChatModel."""

    def test_automatic_session_creation_on_first_message(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        assert model.current_session is None
        assert model.current_session_id is None

        # Al agregar el primer mensaje, debe auto-crearse la sesión
        model.add_message("user", "Hola, genera un cubo 3D")
        assert model.current_session is not None
        assert model.current_session_id is not None

        # El título debe haberse auto-generado a partir del prompt
        assert model.current_session.title == "Hola, genera un cubo 3D"
        assert len(model.messages) == 1

        # Verificar persistencia en el storage
        stored = mgr.get_session(model.current_session_id)
        assert stored is not None
        assert len(stored.messages) == 1
        assert stored.messages[0].content == "Hola, genera un cubo 3D"

    def test_new_session_creates_fresh_state(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.add_message("user", "Primera conversación")
        first_id = model.current_session_id

        # Iniciar nueva sesión
        new_sess = model.new_session(title="Segunda conversación")
        assert new_sess.session_id != first_id
        assert model.current_session_id == new_sess.session_id
        assert len(model.messages) == 0

        # Ambas sesiones existen en disco
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_load_session_restores_messages_and_metadata(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        # Crear sesión 1 con Ollama
        model.set_provider("Ollama")
        model.set_model("llama3:latest")
        model.add_message("user", "Mensaje en Ollama")
        model.add_message("assistant", "Respuesta desde Ollama")
        sess1_id = model.current_session_id

        # Crear sesión 2 con vLLM
        model.new_session(title="Sesión vLLM")
        model.set_provider("vLLM")
        model.add_message("user", "Mensaje en vLLM")
        sess2_id = model.current_session_id

        assert model.current_provider == "vLLM"
        assert len(model.messages) == 1

        # Cargar sesión 1
        loaded = model.load_session(sess1_id)
        assert loaded is True
        assert model.current_session_id == sess1_id
        assert len(model.messages) == 2
        assert model.messages[0].content == "Mensaje en Ollama"
        assert model.current_provider == "Ollama"

    def test_delete_session_cleans_storage_and_active_state(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.add_message("user", "Conversación efímera")
        sess_id = model.current_session_id

        assert len(mgr.list_sessions()) == 1

        deleted = model.delete_session(sess_id)
        assert deleted is True
        assert len(mgr.list_sessions()) == 0
        assert model.current_session is None
        assert len(model.messages) == 0

    def test_rename_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.add_message("user", "Texto inicial")
        sess_id = model.current_session_id

        renamed = model.rename_session(sess_id, "Nuevo Título Personalizado")
        assert renamed is True
        assert model.current_session_title == "Nuevo Título Personalizado"

        stored = mgr.get_session(sess_id)
        assert stored.title == "Nuevo Título Personalizado"

    def test_search_sessions_from_model(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.add_message("user", "Simular colisiones PhysX rígidas")
        model.new_session()
        model.add_message("user", "Generar shader de cristal translúcido")

        results = model.search_sessions("PhysX")
        assert len(results) == 1
        assert "PhysX" in results[0]["title"] or "PhysX" in results[0].get("matches", [""])[0]

    def test_export_and_import_session_from_model(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.add_message("user", "¿Cómo usar USD Composer?")
        model.add_message("assistant", "USD Composer es el visor nativo...")

        json_str = model.export_current_session()
        assert json_str is not None
        assert "USD Composer" in json_str

        # Importar en otro modelo
        mgr2 = LocalChatHistoryManager(storage_dir=str(tmp_path / "imported_store"))
        model2 = ChatModel(history_manager=mgr2)

        imported = model2.import_session(json_str, switch_to=True)
        assert imported is not None
        assert model2.current_session_id == imported.session_id
        assert len(model2.messages) == 2
        assert model2.messages[0].content == "¿Cómo usar USD Composer?"

    def test_subscribers_notified_on_session_events(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        listener = MagicMock()
        model.subscribe(listener)

        # Evento 1: New session
        model.new_session("Nueva")
        assert listener.call_count == 1

        # Evento 2: Add message
        model.add_message("user", "Hola")
        assert listener.call_count == 2

        # Evento 3: Clear messages
        model.clear_messages()
        assert listener.call_count == 3

    def test_load_session_casing_and_alias_tolerance(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s_ollama = mgr.create_session("Ollama Session", metadata={"provider": "ollama", "model": "llama3:latest"})
        s_cloud = mgr.create_session("Cloud Session", metadata={"provider": "cloud", "model": "gpt-4o"})

        model = ChatModel(history_manager=mgr)

        # Cargar sesión con 'ollama' en minúscula
        assert model.load_session(s_ollama.session_id) is True
        assert model.current_provider == "Ollama"
        assert model.current_model == "llama3:latest"

        # Cargar sesión con 'cloud' en minúscula
        assert model.load_session(s_cloud.session_id) is True
        assert model.current_provider == "Cloud APIs"
        assert model.current_model == "gpt-4o"

    def test_set_provider_casing_and_alias_tolerance(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        model = ChatModel(history_manager=mgr)

        model.set_provider("ollama")
        assert model.current_provider == "Ollama"

        model.set_provider("cloud")
        assert model.current_provider == "Cloud APIs"

        model.set_provider("lm_studio")
        assert model.current_provider == "LM Studio"
