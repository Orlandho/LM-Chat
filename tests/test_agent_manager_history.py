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

    @pytest.mark.asyncio
    async def test_process_prompt_stream_error_delivers_diagnostic(self):
        """Verifica que un error en streaming entregue la tarjeta de diagnóstico a la UI."""
        manager = AgentManager()
        diag_md_sample = "### ⚠️ Diagnóstico LM-Chat: Servidor Ollama no detectado\n\nPasos recomendados..."

        async def mock_stream_failure(*args, **kwargs):
            yield {
                "success": False,
                "error_type": "ConnectionError",
                "message": "Connection refused",
                "diagnostic_md": diag_md_sample,
            }

        manager.router.stream_chat_completions = mock_stream_failure

        callback_calls = []
        def append_cb(text):
            callback_calls.append(text)

        result = await manager.process_prompt("Crea un cilindro", append_callback=append_cb)
        assert result == diag_md_sample
        assert callback_calls == [diag_md_sample]

    @pytest.mark.asyncio
    async def test_process_prompt_unhandled_exception_generates_diagnostic(self):
        """Verifica que excepciones imprevistas sean capturadas y transformadas en diagnóstico."""
        manager = AgentManager()

        def faulty_stream(*args, **kwargs):
            raise RuntimeError("Fallo inesperado en socket de bajo nivel")

        manager.router.stream_chat_completions = faulty_stream

        callback_calls = []
        def append_cb(text):
            callback_calls.append(text)

        result = await manager.process_prompt("Hola", append_callback=append_cb)
        assert "### ⚠️ Diagnóstico LM-Chat:" in result
        assert "RuntimeError" in result or "Fallo inesperado" in result or "Error" in result
        assert len(callback_calls) == 1
        assert callback_calls[0] == result

    @pytest.mark.asyncio
    async def test_deepseek_r1_think_block_code_extraction(self):
        """Verifica que AgentManager descarte código borrador dentro de etiquetas <think> y ejecute el código final."""
        manager = AgentManager()
        executed_codes = []

        def mock_execute(code):
            executed_codes.append(code)
            return {"success": True}

        manager._usd_controller.execute_code = mock_execute

        deepseek_response = """
<think>
El usuario quiere crear un cubo. Vamos a probar código borrador:
```python
# BORRADOR QUE NO DEBE EJECUTARSE
prim = stage.DefinePrim('/Borrador')
```
Fin del razonamiento.
</think>

Aquí tienes el código correcto para Omniverse:
```python
# CODIGO FINAL OFICIAL
stage = omni.usd.get_context().get_stage()
prim = stage.DefinePrim('/World/Cube', 'Cube')
```
"""

        async def mock_stream_success(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": deepseek_response}}]},
            }

        manager.router.stream_chat_completions = mock_stream_success
        res = await manager.process_prompt("Crea un cubo")
        assert len(executed_codes) == 1
        assert "CODIGO FINAL OFICIAL" in executed_codes[0]
        assert "BORRADOR QUE NO DEBE EJECUTARSE" not in executed_codes[0]
        assert "[Sistema: Código ejecutado exitosamente]" in res
