# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas exhaustivas para el Gestor de Historial de Chats Local (LocalChatHistoryManager).
Valida persistencia atómica en disco (JSON), sanitización, búsqueda, exportación/importación
y tolerancia a fallos/archivos corruptos.
"""

import os
import json
import pytest
from core.interfaces import ChatSession, ChatMessage, IChatHistoryManager
from logic.chat_history import LocalChatHistoryManager


class TestLocalChatHistoryManager:
    """Pruebas unitarias para LocalChatHistoryManager."""

    def test_implements_interface(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        assert isinstance(mgr, IChatHistoryManager)

    def test_creates_storage_directory(self, tmp_path):
        target_dir = tmp_path / "nested" / "history_store"
        assert not target_dir.exists()
        mgr = LocalChatHistoryManager(storage_dir=str(target_dir))
        assert target_dir.exists()
        assert mgr.storage_dir == str(target_dir)

    def test_create_session_defaults(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        session = mgr.create_session()

        assert session is not None
        assert session.session_id
        assert session.title == LocalChatHistoryManager.DEFAULT_TITLE
        assert session.messages == []
        assert session.created_at
        assert session.updated_at
        assert session.created_at == session.updated_at

        # Verificar persistencia en disco
        file_path = tmp_path / f"{session.session_id}.json"
        assert file_path.exists()

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["session_id"] == session.session_id
        assert data["title"] == LocalChatHistoryManager.DEFAULT_TITLE

    def test_create_session_with_custom_title_and_metadata(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        meta = {"provider": "Ollama", "model": "llama3:latest", "tags": ["robotics", "usd"]}
        session = mgr.create_session(title="Control de Brazo Robótico", metadata=meta)

        assert session.title == "Control de Brazo Robótico"
        assert session.metadata == meta

        retrieved = mgr.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.title == "Control de Brazo Robótico"
        assert retrieved.metadata["provider"] == "Ollama"
        assert retrieved.metadata["tags"] == ["robotics", "usd"]

    def test_get_session_non_existent(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        assert mgr.get_session("non_existent_id") is None
        assert mgr.get_session("") is None

    def test_save_and_retrieve_session_with_unicode_and_messages(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        session = mgr.create_session(title="Simulación Espacial ✨")

        msg1 = ChatMessage(role="user", content="Crea una esfera de radio 5.0 con material 'Oro Puro' 🪙")
        msg2 = ChatMessage(role="assistant", content="```python\nimport omni.usd\n# Crear esfera dorada\n```")
        session.messages.extend([msg1, msg2])

        saved = mgr.save_session(session)
        assert saved is True

        retrieved = mgr.get_session(session.session_id)
        assert retrieved is not None
        assert len(retrieved.messages) == 2
        assert retrieved.messages[0].role == "user"
        assert "Oro Puro" in retrieved.messages[0].content
        assert "🪙" in retrieved.messages[0].content
        assert retrieved.messages[1].role == "assistant"
        assert "import omni.usd" in retrieved.messages[1].content

    def test_list_sessions_sorted_chronologically(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))

        s1 = mgr.create_session(title="Sesión 1")
        s2 = mgr.create_session(title="Sesión 2")
        s3 = mgr.create_session(title="Sesión 3")

        # Modificar updated_at manualmente para verificar ordenación
        s1.updated_at = "2026-09-01T10:00:00+00:00"
        s2.updated_at = "2026-09-03T10:00:00+00:00"
        s3.updated_at = "2026-09-02T10:00:00+00:00"

        mgr.save_session(s1)
        mgr.save_session(s2)
        mgr.save_session(s3)

        sessions = mgr.list_sessions()
        assert len(sessions) == 3
        # Debe estar en orden s2, s3, s1 (más reciente a más antiguo)
        assert sessions[0]["session_id"] == s2.session_id
        assert sessions[1]["session_id"] == s3.session_id
        assert sessions[2]["session_id"] == s1.session_id

    def test_list_sessions_skips_corrupted_files(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))

        s1 = mgr.create_session(title="Sesión Válida")

        # Crear un archivo corrupto que no es JSON válido
        corrupt_file = tmp_path / "corrupted_session.json"
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content :::")

        # Crear un archivo no JSON que deba ser ignorado
        non_json = tmp_path / "notes.txt"
        with open(non_json, "w", encoding="utf-8") as f:
            f.write("Some notes")

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == s1.session_id

    def test_delete_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        session = mgr.create_session(title="Por borrar")
        sid = session.session_id

        assert mgr.get_session(sid) is not None
        deleted = mgr.delete_session(sid)
        assert deleted is True
        assert mgr.get_session(sid) is None

        # Intentar borrar de nuevo debe retornar False
        assert mgr.delete_session(sid) is False

    def test_clear_all_sessions(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        mgr.create_session(title="A")
        mgr.create_session(title="B")
        mgr.create_session(title="C")

        assert len(mgr.list_sessions()) == 3
        cleared = mgr.clear_all_sessions()
        assert cleared is True
        assert len(mgr.list_sessions()) == 0

    def test_search_sessions_by_title_and_message_content(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))

        s1 = mgr.create_session(title="Física e Inercia de Vehículos")
        s1.messages.append(ChatMessage(role="user", content="Calcula la masa de las ruedas"))
        mgr.save_session(s1)

        s2 = mgr.create_session(title="Iluminación de Estudio")
        s2.messages.append(ChatMessage(role="user", content="Agrega un domelight HDR"))
        s2.messages.append(ChatMessage(role="assistant", content="Luz domo configurada con intensidad 1500"))
        mgr.save_session(s2)

        # Búsqueda por título
        res_vehiculos = mgr.search_sessions("vehículos")
        assert len(res_vehiculos) == 1
        assert res_vehiculos[0]["session_id"] == s1.session_id

        # Búsqueda por contenido en mensaje de asistente
        res_domelight = mgr.search_sessions("intensidad 1500")
        assert len(res_domelight) == 1
        assert res_domelight[0]["session_id"] == s2.session_id

        # Búsqueda que no coincide
        assert len(mgr.search_sessions("inexistente_query_xyz")) == 0

        # Búsqueda vacía retorna todas
        assert len(mgr.search_sessions("")) == 2

    def test_export_and_import_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        session = mgr.create_session(title="Exportable Session")
        session.messages.append(ChatMessage(role="user", content="Pregunta 1"))
        session.messages.append(ChatMessage(role="assistant", content="Respuesta 1"))
        mgr.save_session(session)

        exported_json = mgr.export_session_json(session.session_id)
        assert exported_json is not None
        assert "Exportable Session" in exported_json
        assert "Respuesta 1" in exported_json

        # Importar en un segundo manager aislado
        import_dir = tmp_path / "imported"
        mgr2 = LocalChatHistoryManager(storage_dir=str(import_dir))

        imported_session = mgr2.import_session_json(exported_json)
        assert imported_session is not None
        assert imported_session.title == "Exportable Session"
        assert len(imported_session.messages) == 2
        assert imported_session.messages[1].content == "Respuesta 1"

        # Verificar que mgr2 ahora lo lista
        listed = mgr2.list_sessions()
        assert len(listed) == 1
        assert listed[0]["title"] == "Exportable Session"

    def test_sanitization_prevents_directory_traversal(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))

        malicious_id = "../../../etc/passwd"
        safe_path = mgr._get_session_path(malicious_id)

        # Debe estar confinado dentro del directorio de almacenamiento
        assert os.path.dirname(safe_path) == str(tmp_path)
        assert ".." not in safe_path
        assert "passwd" in safe_path or len(os.path.basename(safe_path)) > 5

    def test_generate_title_from_prompt(self):
        # Prompt normal corto
        assert LocalChatHistoryManager.generate_title_from_prompt("Crear un cubo") == "Crear un cubo"

        # Prompt largo truncado a max_chars
        long_prompt = "Genera un escenario de simulación industrial con tres brazos robóticos KUKA y bandas transportadoras activas"
        title = LocalChatHistoryManager.generate_title_from_prompt(long_prompt, max_chars=40)
        assert len(title) <= 43  # 40 + '...'
        assert title.endswith("...")

        # Prompt con saltos de línea y espacios
        multiline = "Hola Agente,\n\n  ¿Cómo estás hoy?  \n"
        assert LocalChatHistoryManager.generate_title_from_prompt(multiline) == "Hola Agente, ¿Cómo estás hoy?"

        # Prompt que empieza con bloques de código
        code_prompt = "```python\nimport omni.usd\n```\nExplica este código"
        assert "Explica este código" in LocalChatHistoryManager.generate_title_from_prompt(code_prompt)

        # Prompt nulo o no string
        assert LocalChatHistoryManager.generate_title_from_prompt(None) == LocalChatHistoryManager.DEFAULT_TITLE
        assert LocalChatHistoryManager.generate_title_from_prompt("") == LocalChatHistoryManager.DEFAULT_TITLE

    def test_list_and_get_session_skips_non_dict_json(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s1 = mgr.create_session(title="Sesión Válida")

        # Archivo JSON con lista
        (tmp_path / "array.json").write_text("[]", encoding="utf-8")
        # Archivo JSON con número
        (tmp_path / "number.json").write_text("12345", encoding="utf-8")
        # Archivo JSON con string
        (tmp_path / "string.json").write_text('"texto"', encoding="utf-8")

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == s1.session_id

        # get_session en archivos que no son diccionarios debe retornar None sin excepción
        assert mgr.get_session("array") is None
        assert mgr.get_session("number") is None
        assert mgr.get_session("string") is None

    def test_chat_session_dict_polymorphism_and_robustness(self):
        # to_dict con mensajes en formato dict
        sess = ChatSession(
            session_id="poly_1",
            title="Polymorphic Messages",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            messages=[{"role": "user", "content": "Hola desde dict"}],
        )
        d = sess.to_dict()
        assert len(d["messages"]) == 1
        assert d["messages"][0]["role"] == "user"
        assert d["messages"][0]["content"] == "Hola desde dict"

        # from_dict con mensajes que ya son ChatMessage y con datos no-dict
        restored = ChatSession.from_dict({
            "session_id": "poly_2",
            "messages": [ChatMessage(role="assistant", content="Respuesta objeto")],
        })
        assert len(restored.messages) == 1
        assert restored.messages[0].role == "assistant"
        assert restored.messages[0].content == "Respuesta objeto"

        # from_dict con entrada inválida no-dict
        fallback = ChatSession.from_dict("invalid non-dict")
        assert fallback is not None
        assert fallback.session_id != ""

    def test_search_sessions_in_metadata_tags_and_null_content(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s1 = mgr.create_session(
            title="Generación Robótica",
            metadata={"provider": "Ollama", "model": "nemotron:latest", "tags": ["simulación", "omniverse"]},
        )
        # Mensaje con contenido None o vacío
        s1.messages.append(ChatMessage(role="user", content="Prompt normal"))
        s1.messages.append(ChatMessage(role="assistant", content=""))
        mgr.save_session(s1)

        # Búsqueda por tag en metadata
        res_tag = mgr.search_sessions("simulación")
        assert len(res_tag) == 1
        assert res_tag[0]["session_id"] == s1.session_id

        # Búsqueda por modelo en metadata
        res_model = mgr.search_sessions("nemotron")
        assert len(res_model) == 1
        assert res_model[0]["session_id"] == s1.session_id

    def test_import_session_json_sanitizes_path_traversal_session_id(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        malicious_json = json.dumps({
            "session_id": "../../../etc/passwd",
            "title": "Malicious Import",
            "messages": [{"role": "user", "content": "Hello"}]
        })

        session = mgr.import_session_json(malicious_json)
        assert session is not None
        assert ".." not in session.session_id
        assert "/" not in session.session_id
        assert "\\" not in session.session_id
        assert session.session_id == "etcpasswd"

        # Check persisted session on disk
        persisted = mgr.get_session("etcpasswd")
        assert persisted is not None
        assert persisted.session_id == "etcpasswd"
        assert persisted.title == "Malicious Import"
