# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas para los comandos de historial en la interfaz CLI (cli/omni_harness.py).
Valida /history, /load, /new, /delete, /search y persistencia automática durante prompts.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from cli.omni_harness import LMChatCLI
from logic.inference_router import InferenceRouter
from logic.chat_history import LocalChatHistoryManager


class TestCLIHistory:
    """Pruebas de comandos de historial en LMChatCLI."""

    def test_cli_initializes_with_active_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(router=router, system_prompt="Test Prompt", history_manager=mgr)

        assert cli.current_session is not None
        assert cli.current_session.session_id
        assert len(cli.messages) == 1
        assert cli.messages[0]["role"] == "system"

    def test_cli_resumes_existing_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        sess = mgr.create_session(title="Sesión Existente")
        mgr.save_session(sess)

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(
            router=router,
            system_prompt="Test Prompt",
            history_manager=mgr,
            session_id=sess.session_id,
        )

        assert cli.current_session.session_id == sess.session_id
        assert cli.current_session.title == "Sesión Existente"

    @pytest.mark.asyncio
    async def test_cli_execute_prompt_persists_to_session(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        router = InferenceRouter(provider="lm_studio")

        # Mock stream_chat_completions
        async def mock_stream(messages):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": "Respuesta simulada CLI"}}]},
            }

        router.stream_chat_completions = mock_stream
        cli = LMChatCLI(router=router, system_prompt="Test Prompt", history_manager=mgr)

        response = await cli.execute_prompt("Crea un cilindro en USD")
        assert response == "Respuesta simulada CLI"

        # Verificar persistencia en el objeto session y en disco
        assert len(cli.current_session.messages) == 2
        assert cli.current_session.messages[0].role == "user"
        assert cli.current_session.messages[0].content == "Crea un cilindro en USD"
        assert cli.current_session.messages[1].role == "assistant"
        assert cli.current_session.messages[1].content == "Respuesta simulada CLI"

        # Título auto-generado
        assert "cilindro" in cli.current_session.title

        # Verificar archivo en disco
        stored = mgr.get_session(cli.current_session.session_id)
        assert stored is not None
        assert len(stored.messages) == 2

    def test_cli_load_and_delete_session_by_identifier(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s1 = mgr.create_session(title="Conversación Primera")
        s2 = mgr.create_session(title="Conversación Segunda")

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(router=router, system_prompt="Test", history_manager=mgr)

        # Cargar por ID
        loaded = cli.load_session_by_identifier(s1.session_id[:8])
        assert loaded is True
        assert cli.current_session.session_id == s1.session_id

        # Cargar por índice numérico
        loaded_idx = cli.load_session_by_identifier("1")
        assert loaded_idx is True

        # Eliminar sesión 1
        deleted = cli.delete_session_by_identifier(s1.session_id[:8])
        assert deleted is True
        assert mgr.get_session(s1.session_id) is None

    def test_cli_print_history_list(self, tmp_path, capsys):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        mgr.create_session(title="Sesión para Listar")

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(router=router, system_prompt="Test", history_manager=mgr)

        cli.print_history_list()
        captured = capsys.readouterr()
        assert "Sesión para Listar" in captured.out
        assert "Historial de Chats Locales" in captured.out

    def test_cli_load_and_delete_with_hash_prefix(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s2 = mgr.create_session(title="Sesión Numérica Dos")
        s1 = mgr.create_session(title="Sesión Numérica Uno", metadata={"provider": "ollama", "model": "llama3"})

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(router=router, system_prompt="Test", history_manager=mgr)

        # Cargar usando prefijo '#' (ej: #1 o #2)
        assert cli.load_session_by_identifier("#1") is True
        # Debe sincronizar provider desde metadata de la sesión cargada
        assert cli.router.provider == "ollama"

        # Eliminar usando prefijo '#'
        assert cli.delete_session_by_identifier("#2") is True
        assert mgr.get_session(s2.session_id) is None

    def test_cli_search_history_filter(self, tmp_path, capsys):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        mgr.create_session(title="Controlador de Luces")
        mgr.create_session(title="Simulación de Fluidos")

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(router=router, system_prompt="Test", history_manager=mgr)

        results = cli.print_history_list(query="Fluidos")
        captured = capsys.readouterr()
        assert "Resultados de Búsqueda para 'Fluidos'" in captured.out
        assert "Simulación de Fluidos" in captured.out
        assert "Controlador de Luces" not in captured.out
        assert len(results) == 1

    def test_cli_resumes_session_and_syncs_router(self, tmp_path):
        mgr = LocalChatHistoryManager(storage_dir=str(tmp_path))
        s = mgr.create_session(
            title="Sesión con Ollama",
            metadata={"provider": "ollama", "model": "mistral:latest"},
        )

        router = InferenceRouter(provider="lm_studio")
        cli = LMChatCLI(
            router=router,
            system_prompt="Test Prompt",
            history_manager=mgr,
            session_id=s.session_id,
        )

        assert cli.current_session.session_id == s.session_id
        assert cli.router.provider == "ollama"
        assert cli.router.model == "mistral:latest"
