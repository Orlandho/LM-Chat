# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas automatizadas para Modos de Ejecución: Inmediato vs Plan & Confirmar (PLAN 3).
Cubre TC-MOD-001 a TC-MOD-004:
- TC-MOD-001: Modo Inmediato (⚡ Fast Act / Autónomo) ejecuta código automáticamente.
- TC-MOD-002: Modo Plan & Confirmar retiene código propuesto y notifica callback.
- TC-MOD-003: Confirmación interactiva ejecuta el código pendiente en el Stage OpenUSD.
- TC-MOD-004: Cancelación interactiva descarta el código pendiente sin alterar la escena.
"""

import pytest
from unittest.mock import MagicMock
from core.interfaces import ExecutionMode
from logic.agent_manager import AgentManager
from ui.chat_window import ChatWindow


class TestExecutionModes:
    """Suite de pruebas para Modos de Ejecución (TC-MOD-001 a TC-MOD-004)."""

    @pytest.mark.asyncio
    async def test_tc_mod_001_immediate_mode_autonomous_execution(self):
        """TC-MOD-001: En Modo Inmediato, el código se ejecuta directamente sin requerir confirmación."""
        manager = AgentManager(execution_mode=ExecutionMode.IMMEDIATE.value)
        assert manager.execution_mode == ExecutionMode.IMMEDIATE.value

        executed_codes = []

        def mock_execute(code):
            executed_codes.append(code)
            return {"success": True}

        manager._usd_controller.execute_code = mock_execute

        ai_code_response = """
Aquí tienes el cubo:
```python
stage = omni.usd.get_context().get_stage()
stage.DefinePrim('/World/Cube', 'Cube')
```
"""

        async def mock_stream(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": ai_code_response}}]},
            }

        manager.router.stream_chat_completions = mock_stream

        confirmation_mock = MagicMock()
        res = await manager.process_prompt("Crea un cubo", confirmation_callback=confirmation_mock)

        # El código se ejecutó automáticamente
        assert len(executed_codes) == 1
        assert "stage.DefinePrim('/World/Cube', 'Cube')" in executed_codes[0]
        # No se debió requerir confirmación interactiva
        confirmation_mock.assert_not_called()
        assert not manager.has_pending_code()
        assert "[Sistema: Código ejecutado exitosamente]" in res

    @pytest.mark.asyncio
    async def test_tc_mod_002_plan_mode_holds_pending_code_and_invokes_callback(self):
        """TC-MOD-002: En Modo Plan & Confirm, el código NO se ejecuta en escena y queda retenido."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)
        assert manager.execution_mode == ExecutionMode.PLAN_AND_CONFIRM.value

        executed_codes = []

        def mock_execute(code):
            executed_codes.append(code)
            return {"success": True}

        manager._usd_controller.execute_code = mock_execute

        ai_plan_response = """
Plan de acción propuesto:
1. Inspeccionar el Stage para evitar colisiones de nombres.
2. Crear un prim de tipo Esfera en /World/Sphere.

```python
stage = omni.usd.get_context().get_stage()
stage.DefinePrim('/World/Sphere', 'Sphere')
```
"""

        async def mock_stream(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": ai_plan_response}}]},
            }

        manager.router.stream_chat_completions = mock_stream

        confirmation_mock = MagicMock()
        res = await manager.process_prompt("Crea una esfera", confirmation_callback=confirmation_mock)

        # El código NO se ejecutó inmediatamente en el Stage
        assert len(executed_codes) == 0
        # El callback de confirmación fue invocado con el código propuesto y metadatos
        confirmation_mock.assert_called_once()
        call_code, call_meta = confirmation_mock.call_args[0]
        assert "stage.DefinePrim('/World/Sphere', 'Sphere')" in call_code
        assert "Plan de acción propuesto" in call_meta["plan"]

        # El código queda pendiente de confirmación en AgentManager
        assert manager.has_pending_code()
        assert "DefinePrim('/World/Sphere', 'Sphere')" in manager.get_pending_code()
        assert "[Sistema: Plan y código listos. Esperando confirmación para ejecutar en escena...]" in res

    def test_tc_mod_003_confirm_and_execute_pending_code(self):
        """TC-MOD-003: Confirmar el plan interactivo ejecuta el código retenido en el Stage."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)
        test_code = "stage.DefinePrim('/World/ConfirmedCylinder', 'Cylinder')"
        manager._pending_code = test_code

        executed = []

        def mock_execute(code):
            executed.append(code)
            return {"success": True, "created": "/World/ConfirmedCylinder"}

        manager._usd_controller.execute_code = mock_execute

        res = manager.execute_pending_code()

        assert res["success"] is True
        assert len(executed) == 1
        assert executed[0] == test_code
        # Después de ejecutar, ya no debe quedar código pendiente
        assert not manager.has_pending_code()

    def test_tc_mod_004_cancel_pending_code(self):
        """TC-MOD-004: Cancelar el plan interactivo descarta el código retenido sin tocar la escena."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)
        test_code = "stage.DefinePrim('/World/CancelledMesh', 'Mesh')"
        manager._pending_code = test_code

        executed = []
        manager._usd_controller.execute_code = lambda code: executed.append(code)

        res = manager.cancel_pending_code()

        assert res["success"] is True
        assert res.get("cancelled") is True
        # El código no se ejecutó
        assert len(executed) == 0
        assert not manager.has_pending_code()

    def test_tc_mod_plan_confirmation_card_ui_interaction(self):
        """Verifica que la tarjeta interactiva de confirmación en ChatWindow despacha eventos al delegado."""
        window = ChatWindow()
        executed_actions = []

        window.delegate.set_plan_action_callback(lambda act: executed_actions.append(act))

        # Renderizar tarjeta interactiva
        window.show_plan_confirmation_card(
            code="stage.DefinePrim('/World/Cube', 'Cube')",
            plan_text="Creación de un prim cúbico."
        )

        # Simular evento de confirmación
        window.delegate.on_execute_plan()
        assert executed_actions == ["execute"]

        # Simular evento de cancelación
        window.delegate.on_cancel_plan()
        assert executed_actions == ["execute", "cancel"]

    def test_tc_mod_double_execution_safely_prevented(self):
        """Verifica que ejecutar el código pendiente dos veces seguidas sea rechazado de forma segura."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)
        manager._pending_code = "stage.DefinePrim('/World/SingleExec', 'Cube')"
        manager._usd_controller.execute_code = lambda code: {"success": True}

        # Primera ejecución exitosa
        first_res = manager.execute_pending_code()
        assert first_res["success"] is True

        # Segunda ejecución inmediata debe fallar limpiamente
        second_res = manager.execute_pending_code()
        assert second_res["success"] is False
        assert "No hay código pendiente" in second_res["error_msg"]

    @pytest.mark.asyncio
    async def test_tc_mod_new_prompt_resets_old_pending_code(self):
        """Verifica que el envío de una nueva instrucción por el usuario limpie cualquier plan pendiente anterior."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)
        manager._pending_code = "stage.DefinePrim('/World/OldAbandonedPlan', 'Cube')"

        async def mock_stream(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": "Hola, ¿en qué puedo ayudarte hoy?"}}]},
            }

        manager.router.stream_chat_completions = mock_stream
        await manager.process_prompt("Hola")

        # El código anterior abandonado ya no debe existir
        assert not manager.has_pending_code()
        assert manager.get_pending_code() is None

    @pytest.mark.asyncio
    async def test_tc_mod_clean_plan_description_without_code_duplication(self):
        """Verifica que la tarjeta interactiva reciba solo los pasos del plan, sin duplicar el bloque ```python."""
        manager = AgentManager(execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value)

        ai_response = """
Pasos del Plan:
1. Validar la ruta destino.
2. Crear un prim tipo Cono.

```python
stage = omni.usd.get_context().get_stage()
stage.DefinePrim('/World/Cone', 'Cone')
```
"""
        async def mock_stream(*args, **kwargs):
            yield {
                "success": True,
                "data": {"choices": [{"delta": {"content": ai_response}}]},
            }

        manager.router.stream_chat_completions = mock_stream

        received_meta = {}
        def mock_confirm(code, meta):
            received_meta.update(meta)

        await manager.process_prompt("Crea un cono", confirmation_callback=mock_confirm)

        assert "plan" in received_meta
        plan_text = received_meta["plan"]
        assert "Pasos del Plan:" in plan_text
        assert "1. Validar la ruta destino." in plan_text
        assert "```python" not in plan_text
        assert "DefinePrim" not in plan_text
