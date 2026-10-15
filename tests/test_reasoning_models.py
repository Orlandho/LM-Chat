# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas automatizadas para el soporte de modelos de razonamiento (PLAN 1).
Cubre TC-RSN-001 a TC-RSN-004:
- TC-RSN-001: Detección heurística de modelos con pensamiento extendido.
- TC-RSN-002: Adaptación de payloads (omisión de temperature, max_completion_tokens).
- TC-RSN-003: Parsing de streams con fragmentación de tags <think> y reasoning_content.
- TC-RSN-004: Integración visual del contenedor colapsable de razonamiento en la UI.
"""

import pytest
from typing import Tuple
from unittest.mock import MagicMock
from logic.inference_router import (
    is_reasoning_model,
    StreamingReasoningParser,
    InferenceRouter,
)
from core.interfaces import InferenceConfig, ExecutionMode
from logic.agent_manager import AgentManager
from ui.chat_window import ChatWindow


class TestReasoningModelAwareness:
    """Suite de pruebas para modelos de razonamiento (TC-RSN-001 a TC-RSN-004)."""

    def test_tc_rsn_001_reasoning_model_detection(self):
        """TC-RSN-001: Detecta correctamente modelos de razonamiento frontier y open-weight."""
        reasoning_models = [
            "o1",
            "o1-mini",
            "o1-preview",
            "o3-mini",
            "deepseek-r1",
            "deepseek-r1-distill-qwen-32b",
            "qwq-32b",
            "claude-3-7-sonnet-thinking",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-2.0-flash-thinking",
            "gemini-2.5-flash-thinking",
            "deepseek-reasoner",
        ]
        non_reasoning_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet-20241022",
            "gemini-1.5-pro",
            "llama-3.1-8b-instruct",
            "mistral-7b-instruct",
        ]

        for model in reasoning_models:
            assert is_reasoning_model(model), f"Fallo al identificar modelo de razonamiento: {model}"

        for model in non_reasoning_models:
            assert not is_reasoning_model(model), f"Falso positivo en modelo estándar: {model}"

    def test_tc_rsn_002_payload_adaptation(self):
        """TC-RSN-002: Omite temperature y sustituye max_tokens por max_completion_tokens."""
        router = InferenceRouter(provider="openai", model="o1-mini")
        config = InferenceConfig(temperature=0.7, max_tokens=4096)
        messages = [{"role": "user", "content": "Genera una escena 3D"}]

        payload = router._build_payload(messages, config, stream=False)

        # En modelos de razonamiento, temperature debe ser omitida
        assert "temperature" not in payload, "Temperature no debe estar presente para modelos de razonamiento"
        # Debe mapear max_tokens a max_completion_tokens
        assert "max_completion_tokens" in payload
        assert payload["max_completion_tokens"] == 4096
        assert "max_tokens" not in payload

        # Verificar caso estándar (no reasoning)
        std_router = InferenceRouter(provider="openai", model="gpt-4o")
        std_payload = std_router._build_payload(messages, config, stream=False)
        assert "temperature" in std_payload
        assert std_payload["temperature"] == 0.7
        assert "max_tokens" in std_payload
        assert "max_completion_tokens" not in std_payload

    def test_tc_rsn_003_streaming_reasoning_parser_split_chunks(self):
        """TC-RSN-003: Separa tokens de pensamiento incluso si <think> se fragmenta en varios chunks."""
        parser = StreamingReasoningParser()

        # Simular llegada fragmentada por SSE
        chunks = [
            "<th",
            "ink>\nPrimero evaluamos el stage OpenUSD.\n",
            "Vamos a crear un cubo prim.",
            "\n</thi",
            "nk>\n\n```python\nimport omni.usd\n```",
        ]

        thought_accumulator = []
        content_accumulator = []

        for ch in chunks:
            thoughts, content = parser.feed_chunk(ch)
            if thoughts:
                thought_accumulator.append(thoughts)
            if content:
                content_accumulator.append(content)

        flush_items = parser.flush()
        for item in flush_items:
            if item.get("type") == "reasoning":
                thought_accumulator.append(item.get("text", ""))
            else:
                content_accumulator.append(item.get("text", ""))

        full_thoughts = "".join(thought_accumulator)
        full_content = "".join(content_accumulator)

        assert "Primero evaluamos el stage OpenUSD." in full_thoughts
        assert "Vamos a crear un cubo prim." in full_thoughts
        assert "<think>" not in full_thoughts
        assert "</think>" not in full_thoughts
        assert "import omni.usd" in full_content
        assert "Primero evaluamos" not in full_content

    def test_tc_rsn_003_streaming_reasoning_native_reasoning_content(self):
        """TC-RSN-003: Procesa streaming directo con el campo nativo reasoning_content (DeepSeek)."""
        parser = StreamingReasoningParser()

        thoughts, content = parser.feed_chunk("Respuesta final", reasoning_chunk="Pensamiento nativo")
        assert thoughts == "Pensamiento nativo"
        assert content == "Respuesta final"

    @pytest.mark.asyncio
    async def test_tc_rsn_004_code_inside_think_is_ignored(self):
        """TC-RSN-004: Código Python preliminar dentro de <think> es ignorado; solo se ejecuta el bloque fuera."""
        manager = AgentManager(execution_mode=ExecutionMode.IMMEDIATE.value)

        executed_codes = []
        manager._usd_controller.execute_code = lambda code: (executed_codes.append(code), {"success": True})[1]

        # Simular respuesta de DeepSeek-R1 que incluye código borrador dentro de <think>
        deepseek_response = """
<think>
Vamos a intentar crear una esfera de prueba preliminar:
```python
stage = omni.usd.get_context().get_stage()
stage.DefinePrim('/World/DraftBuggyPrim', 'Sphere')
```
No, el usuario pidió un Cubo definitivo. Descartamos el borrador.
</think>
Aquí está el cubo final solicitado:
```python
stage = omni.usd.get_context().get_stage()
stage.DefinePrim('/World/FinalCorrectCube', 'Cube')
```
"""
        async def mock_stream(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": deepseek_response}}]},
            }

        manager.router.stream_chat_completions = mock_stream

        res = await manager.process_prompt("Crea un cubo")

        # Solo debe haberse ejecutado el bloque fuera de <think>
        assert len(executed_codes) == 1
        assert "FinalCorrectCube" in executed_codes[0]
        assert "DraftBuggyPrim" not in executed_codes[0]

    def test_tc_rsn_004_ui_reasoning_collapsible_widget(self):
        """TC-RSN-004 UI: append_reasoning crea un CollapsibleFrame que se colapsa y actualiza título."""
        window = ChatWindow()
        window.add_message_bubble("assistant", "")

        # Emitir tokens de razonamiento
        window.append_reasoning("Analizando el stage...")
        window.append_reasoning(" Identificando prims.")

        assert window._active_reasoning_frame is not None
        assert window._active_reasoning_label is not None
        assert "Analizando el stage... Identificando prims." in window._active_reasoning_label.text
        assert not window._active_reasoning_frame.collapsed

        # Al comenzar a recibir texto de respuesta final, el frame de razonamiento debe colapsarse
        window.append_to_last_message("Aquí está la respuesta final.")
        assert window._active_reasoning_frame.collapsed is True
        assert "Pensamiento analítico completado" in window._active_reasoning_frame.title

    def test_tc_rsn_malformed_unclosed_think_tag_stream_eof(self):
        """Verifica que un flujo SSE con tag <think> que nunca se cierra antes del EOF se descargue como razonamiento."""
        parser = StreamingReasoningParser()
        thoughts, _ = parser.feed_chunk("<think>Pensamiento truncado sin cierre...")
        assert thoughts == "Pensamiento truncado sin cierre..."
        assert parser.in_thinking_phase is True

        # Además, si hay caracteres retenidos que formaban un cierre parcial pero el stream acabó
        parser.feed_chunk(" y fragmento </thi")
        flushed = parser.flush()
        assert len(flushed) == 1
        assert flushed[0]["type"] == "reasoning"
        assert flushed[0]["text"] == "</thi"
        assert parser.in_thinking_phase is False

    def test_tc_rsn_type_annotations_evaluate_cleanly(self):
        """Verifica que las anotaciones de tipos de StreamingReasoningParser no arrojen NameError en runtime."""
        annotations = StreamingReasoningParser.feed_chunk.__annotations__
        assert annotations.get("return") in (Tuple[str, str], "Tuple[str, str]")
