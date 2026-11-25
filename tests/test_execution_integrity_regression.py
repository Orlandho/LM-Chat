# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Suite de pruebas de regresión estrictas para Integridad de Ejecución (Encargo 1: F01, F05, F06).

Basada directamente en las sondas de `scratch/audit-20261029-probes.py` y contrastada contra el
contrato real de NVIDIA Omniverse Kit SDK 107.3.7 (`omni.kit.commands 1.4.10` / `omni.usd`).

Nota de alcance de evidencia:
- Estas pruebas verifican contratos de API, reversibilidad en máquina de estados estricta,
  acotamiento cooperativo, afinidad de hilo, cancelación efectiva y frontera de capacidades en
  entorno headless.
- NO sustituyen la verificación gráfica en vivo dentro de Omniverse Kit (RTX, 60 FPS reales,
  atajos Ctrl+Z/Ctrl+Y del viewport).
"""

import ast
import asyncio
import copy
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from core.interfaces import (
    CancellationToken,
    ExecutionAffinity,
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionCancelledError,
    ExecutionMode,
    ExecutionResult,
    IExecutionEngine,
)
from core.policies import AgentPolicyConfig, SpatialSecurityPolicy, redact_secrets
import logic.usd_controller as uc
from logic.agent_manager import AgentManager
from logic.usd_controller import USDController
from extension import LMChatExtension


# ---------------------------------------------------------------------------
# Doble estricto sin MagicMock del host Kit 107.3.7 (Undo + Commands)
# ---------------------------------------------------------------------------

class _StrictKitCommandsDouble:
    """
    Doble estricto con estado real en memoria que solo acepta comandos y firmas
    válidas de NVIDIA Omniverse Kit 107.3.7 (`omni.usd.commands.usd_commands`).
    No utiliza MagicMock: cualquier método o parámetro inexistente falla explícitamente.
    """

    __slots__ = ("_stage", "_undo_host", "call_log")

    def __init__(self, stage: Dict[str, Dict[str, Any]], undo_host: "_StrictKitUndoHost") -> None:
        self._stage = stage
        self._undo_host = undo_host
        self.call_log: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, command_name: str, **kwargs: Any) -> Tuple[bool, Any]:
        self.call_log.append((command_name, copy.deepcopy(kwargs)))
        before = copy.deepcopy(self._stage)

        if command_name == "CreatePrimWithDefaultXform":
            allowed = {"prim_type", "prim_path", "select_new_prim", "attributes", "create_default_xform", "stage", "context_name"}
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"CreatePrimWithDefaultXform unexpected kwargs: {extra}")
            prim_type = kwargs["prim_type"]
            prim_path = kwargs.get("prim_path") or f"/{prim_type}"
            attributes = dict(kwargs.get("attributes") or {})
            self._stage[prim_path] = {
                "type": prim_type,
                "attributes": attributes,
                "transform": {},
            }
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, prim_path

        if command_name == "TransformPrimSRTCommand":
            allowed = {
                "path", "new_translation", "new_rotation_euler", "new_scale",
                "new_rotation_order", "old_translation", "old_rotation_euler",
                "old_rotation_order", "old_scale", "time_code", "had_transform_at_key",
                "usd_context_name",
            }
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"TransformPrimSRTCommand unexpected kwargs: {extra}")
            path = kwargs["path"]
            if path not in self._stage:
                return False, f"Prim '{path}' does not exist"
            tr = self._stage[path]["transform"]
            if "new_translation" in kwargs:
                tr["translation"] = tuple(kwargs["new_translation"])
            if "new_rotation_euler" in kwargs:
                tr["rotation"] = tuple(kwargs["new_rotation_euler"])
            if "new_scale" in kwargs:
                tr["scale"] = tuple(kwargs["new_scale"])
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, None

        if command_name == "TransformPrimCommand":
            allowed = {
                "path", "new_transform_matrix", "old_transform_matrix",
                "time_code", "had_transform_at_key", "usd_context_name",
            }
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"TransformPrimCommand unexpected kwargs: {extra}")
            path = kwargs["path"]
            if path not in self._stage:
                return False, f"Prim '{path}' does not exist"
            self._stage[path]["transform"]["matrix"] = kwargs["new_transform_matrix"]
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, None

        if command_name == "ChangePropertyCommand":
            allowed = {
                "prop_path", "value", "prev", "timecode",
                "type_to_create_if_not_exist", "target_layer",
                "usd_context_name", "is_custom", "variability",
            }
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"ChangePropertyCommand unexpected kwargs: {extra}")
            prop_path = kwargs["prop_path"]
            prim_path, attr_name = prop_path.split(".", 1)
            if prim_path not in self._stage:
                return False, f"Prim '{prim_path}' does not exist"
            prev_arg = kwargs.get("prev")
            self._stage[prim_path]["attributes"][attr_name] = kwargs["value"]
            after = copy.deepcopy(self._stage)
            # Simula la semántica real de ChangePropertyCommand: si prev != None restaura prev;
            # si prev is None sobre un atributo que ya tenía valor, limpia el atributo (revela bugs de prev=None).
            undo_snapshot = copy.deepcopy(before)
            if prev_arg is not None:
                undo_snapshot[prim_path]["attributes"][attr_name] = prev_arg
            elif attr_name in before[prim_path]["attributes"]:
                undo_snapshot[prim_path]["attributes"][attr_name] = None
            self._undo_host._record_mutation(command_name, undo_snapshot, after)
            return True, None

        if command_name == "BindMaterialCommand":
            allowed = {"prim_path", "material_path", "strength", "stage", "context_name", "material_purpose"}
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"BindMaterialCommand unexpected kwargs: {extra}")
            prim_path = kwargs["prim_path"]
            if prim_path not in self._stage:
                return False, f"Prim '{prim_path}' does not exist"
            self._stage[prim_path]["material"] = kwargs["material_path"]
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, None

        if command_name == "MovePrimsCommand":
            allowed = {"paths_to_move", "time_code", "keep_world_transform", "on_move_fn", "destructive", "stage_or_context"}
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"MovePrimsCommand unexpected kwargs: {extra}")
            for src, dst in kwargs["paths_to_move"].items():
                if src not in self._stage:
                    return False, f"Prim '{src}' does not exist"
                self._stage[dst] = self._stage.pop(src)
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, None

        if command_name == "GroupPrimsCommand":
            allowed = {"prim_paths", "stage", "context_name", "destructive"}
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"GroupPrimsCommand unexpected kwargs: {extra}")
            group_path = "/World/Group"
            self._stage[group_path] = {"type": "Xform", "attributes": {}, "transform": {}}
            for p in kwargs["prim_paths"]:
                if p in self._stage:
                    name = p.rstrip("/").rsplit("/", 1)[-1]
                    self._stage[f"{group_path}/{name}"] = self._stage.pop(p)
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, group_path

        if command_name == "DeletePrimsCommand":
            allowed = {"paths", "destructive", "stage", "context_name"}
            extra = set(kwargs) - allowed
            if extra:
                raise TypeError(f"DeletePrimsCommand unexpected kwargs: {extra}")
            for p in kwargs["paths"]:
                self._stage.pop(p, None)
            after = copy.deepcopy(self._stage)
            self._undo_host._record_mutation(command_name, before, after)
            return True, None

        raise ValueError(f"Unknown Kit command: {command_name}")


class _StrictKitUndoHost:
    """
    Doble estricto sin MagicMock que reproduce la semántica de `omni.kit.undo`
    de Kit 107.3.7 (`omni.kit.commands 1.4.10`):
    - Exporta begin_group(), end_group() (sin parámetros), group(), undo(), redo(),
      can_undo(), can_redo().
    - Rechaza `begin` y `end` (y cualquier atributo inexistente) con AttributeError.
    - Agrupa mutaciones en una sola transacción deshacible/rehacible.
    """

    __slots__ = (
        "_stage",
        "_undo_stack",
        "_redo_stack",
        "_group_depth",
        "_active_group_entries",
        "_push_empty_groups",
        "begin_group_calls",
        "end_group_calls",
        "undo_calls",
        "redo_calls",
    )

    def __init__(self, stage: Dict[str, Dict[str, Any]], push_empty_groups: bool = True) -> None:
        self._stage = stage
        self._undo_stack: List[List[Tuple[str, Dict[str, Any], Dict[str, Any]]]] = []
        self._redo_stack: List[List[Tuple[str, Dict[str, Any], Dict[str, Any]]]] = []
        self._group_depth: int = 0
        self._active_group_entries: Optional[List[Tuple[str, Dict[str, Any], Dict[str, Any]]]] = None
        self._push_empty_groups = push_empty_groups
        self.begin_group_calls: int = 0
        self.end_group_calls: int = 0
        self.undo_calls: int = 0
        self.redo_calls: int = 0

    def get_undo_stack(self):
        return self._undo_stack

    def _record_mutation(self, cmd_name: str, before: Dict[str, Any], after: Dict[str, Any]) -> None:
        entry = (cmd_name, before, after)
        self._redo_stack.clear()
        if self._group_depth > 0 and self._active_group_entries is not None:
            self._active_group_entries.append(entry)
        else:
            self._undo_stack.append([entry])

    def begin_group(self) -> None:
        self.begin_group_calls += 1
        self._group_depth += 1
        if self._group_depth == 1:
            self._active_group_entries = []

    def end_group(self) -> None:
        # Firma estricta de Kit 107.3.7 (undo.py:315): sin argumentos.
        self.end_group_calls += 1
        if self._group_depth <= 0:
            raise RuntimeError("end_group() called without matching begin_group()")
        self._group_depth -= 1
        if self._group_depth == 0:
            entries = self._active_group_entries or []
            self._active_group_entries = None
            if entries or self._push_empty_groups:
                self._undo_stack.append(entries)

    @contextmanager
    def group(self):
        self.begin_group()
        try:
            yield
        finally:
            self.end_group()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        self.undo_calls += 1
        if not self._undo_stack:
            return False
        group_entries = self._undo_stack.pop()
        self._redo_stack.append(group_entries)
        if group_entries:
            # Restaurar estado previo al primer comando del grupo
            first_before = group_entries[0][1]
            self._stage.clear()
            self._stage.update(copy.deepcopy(first_before))
        return True

    def redo(self) -> bool:
        self.redo_calls += 1
        if not self._redo_stack:
            return False
        group_entries = self._redo_stack.pop()
        self._undo_stack.append(group_entries)
        if group_entries:
            # Restaurar estado posterior al último comando del grupo
            last_after = group_entries[-1][2]
            self._stage.clear()
            self._stage.update(copy.deepcopy(last_after))
        return True


class _StrictUsdStageReader:
    """Doble estricto sin MagicMock de lectura de Stage para validar prev en ChangePropertyCommand."""

    __slots__ = ("_stage",)

    def __init__(self, stage: Dict[str, Dict[str, Any]]) -> None:
        self._stage = stage

    def GetPrimAtPath(self, path: str):
        if path not in self._stage:
            return None
        data = self._stage[path]

        class _Attr:
            __slots__ = ("_exists", "_val")

            def __init__(self, exists, val):
                self._exists = exists
                self._val = val

            def IsValid(self):
                return self._exists

            def Get(self):
                return self._val

        class _Prim:
            __slots__ = ("_attrs",)

            def __init__(self, attrs):
                self._attrs = attrs

            def IsValid(self):
                return True

            def GetAttribute(self, name: str):
                return _Attr(name in self._attrs, self._attrs.get(name))

        return _Prim(data["attributes"])


class _StrictKitNamespace:
    __slots__ = ("kit", "usd")

    def __init__(
        self,
        undo_host: _StrictKitUndoHost,
        commands_host: _StrictKitCommandsDouble,
        stage: Dict[str, Dict[str, Any]],
    ) -> None:
        class _Kit:
            __slots__ = ("undo", "commands")

            def __init__(self, u, c):
                self.undo = u
                self.commands = c

        class _UsdContext:
            __slots__ = ("_reader",)

            def __init__(self, st):
                self._reader = _StrictUsdStageReader(st)

            def get_stage(self):
                return self._reader

        class _UsdMod:
            __slots__ = ("_ctx",)

            def __init__(self, st):
                self._ctx = _UsdContext(st)

            def get_context(self):
                return self._ctx

        self.kit = _Kit(undo_host, commands_host)
        self.usd = _UsdMod(stage)


def _make_strict_kit_host(
    push_empty_groups: bool = True,
) -> Tuple[Dict[str, Dict[str, Any]], _StrictKitUndoHost, _StrictKitCommandsDouble, _StrictKitNamespace]:
    stage: Dict[str, Dict[str, Any]] = {}
    undo_host = _StrictKitUndoHost(stage, push_empty_groups=push_empty_groups)
    commands_host = _StrictKitCommandsDouble(stage, undo_host)
    omni_ns = _StrictKitNamespace(undo_host, commands_host, stage)
    return stage, undo_host, commands_host, omni_ns


# ===========================================================================
# F01 · Regresiones de Undo, API real Kit 107.3.7 y mutaciones USD reversibles
# ===========================================================================

class TestF01UndoAndUsdIntegrity:
    """Regresiones estrictas para F01 basadas en Kit SDK 107.3.7 / Commands 1.4.10."""

    def test_f01_strict_undo_host_rejects_nonexistent_begin_and_end_and_matches_sdk(self):
        """Verifica API estricta sin MagicMock y contrasta con el SDK local si está presente."""
        _, undo_host, _, omni_ns = _make_strict_kit_host()

        assert hasattr(undo_host, "begin") is False
        assert hasattr(undo_host, "end") is False
        assert hasattr(undo_host, "begin_group") is True
        assert hasattr(undo_host, "end_group") is True
        assert hasattr(undo_host, "group") is True

        with pytest.raises(AttributeError):
            _ = undo_host.begin  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            _ = undo_host.end  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            _ = undo_host.invented_mock_method  # type: ignore[attr-defined]

        # Contraste directo con el SDK 107.3.7 local si es accesible en el host actual
        sdk_undo_init = Path(r"C:\Users\Orlando\kit-sdk-public\exts\omni.kit.commands\omni\kit\undo\__init__.py")
        try:
            sdk_accessible = sdk_undo_init.exists()
        except OSError:
            sdk_accessible = False

        if sdk_accessible:
            tree = ast.parse(sdk_undo_init.read_text(encoding="utf-8"))
            exported = next(
                ast.literal_eval(n.value)
                for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
            )
            assert "begin" not in exported
            assert "end" not in exported
            assert "begin_group" in exported
            assert "end_group" in exported
            assert "group" in exported

        with patch.object(uc, "omni", omni_ns):
            controller = USDController()
            res = controller.execute_code("answer = 2 + 2")
            assert res["success"] is True
            assert undo_host.begin_group_calls == 1
            assert undo_host.end_group_calls == 1

    def test_f01_compound_operation_reversible_create_undo_redo(self):
        """
        Demuestra con máquina de estados estricta (sin MagicMock) que una operación compuesta
        (crear 2 prims + transformar SRT + cambiar atributo + agrupar) se revierte íntegra
        con un solo undo() y se restaura íntegra con un solo redo().
        """
        stage, undo_host, commands_host, omni_ns = _make_strict_kit_host()

        compound_script = """
controller.create_prim("Cube", "/World/BoxA", attributes={"size": 2.0})
controller.create_prim("Sphere", "/World/BallB", attributes={"radius": 1.5})
controller.transform_prim("/World/BoxA", translation=[10.0, 20.0, 30.0], scale=[2.0, 2.0, 2.0])
controller.set_prim_attribute("/World/BallB", "visibility", "invisible")
controller.group_prims(["/World/BoxA", "/World/BallB"], "/World/Rig")
"""
        with patch.object(uc, "omni", omni_ns):
            controller = USDController()
            res = controller.execute_code(compound_script)

        assert res["success"] is True
        assert "/World/Rig" in stage
        assert "/World/Rig/BoxA" in stage
        assert "/World/Rig/BallB" in stage
        assert stage["/World/Rig/BoxA"]["transform"]["translation"] == (10.0, 20.0, 30.0)
        assert stage["/World/Rig/BallB"]["attributes"]["visibility"] == "invisible"

        # Un único Ctrl+Z revierte TODA la operación compuesta
        assert undo_host.can_undo() is True
        assert undo_host.undo() is True
        assert stage == {}

        # Un único Ctrl+Y rehace TODA la operación compuesta
        assert undo_host.can_redo() is True
        assert undo_host.redo() is True
        assert "/World/Rig/BoxA" in stage
        assert "/World/Rig/BallB" in stage
        assert stage["/World/Rig/BoxA"]["transform"]["translation"] == (10.0, 20.0, 30.0)
        assert stage["/World/Rig/BallB"]["attributes"]["visibility"] == "invisible"

        # Verificar que solo se invocaron comandos con firmas reales de Kit 107.3.7
        executed_names = [name for name, _ in commands_host.call_log]
        assert executed_names == [
            "CreatePrimWithDefaultXform",
            "CreatePrimWithDefaultXform",
            "TransformPrimSRTCommand",
            "ChangePropertyCommand",
            "CreatePrimWithDefaultXform",
            "MovePrimsCommand",
        ]

    def test_f01_partial_failure_rolls_back_to_defined_clean_state(self):
        """
        Si un script falla a mitad tras crear y transformar prims, cierra el grupo y
        ejecuta undo() dejando el Stage en el estado exacto previo, con contexto de error útil.
        """
        stage, undo_host, _, omni_ns = _make_strict_kit_host()
        stage["/World/PreExisting"] = {"type": "Xform", "attributes": {}, "transform": {}}

        failing_script = """
controller.create_prim("Cube", "/World/TempCube")
controller.transform_prim("/World/TempCube", translation=[1.0, 2.0, 3.0])
raise RuntimeError("Fallo simulado tras mutación parcial")
"""
        with patch.object(uc, "omni", omni_ns):
            controller = USDController()
            res = controller.execute_code(failing_script)

        assert res["success"] is False
        assert res["error_type"] == "RuntimeError"
        assert res["line_number"] == 4
        assert "Fallo simulado tras mutación parcial" in res["error_msg"]
        assert "<lmchat_script>" in res["traceback_str"]
        assert res["partial_changes_rolled_back"] is True

        # El prim parcial fue revertido; el prim preexistente permanece intacto
        assert "/World/TempCube" not in stage
        assert "/World/PreExisting" in stage
        assert undo_host.begin_group_calls == 1
        assert undo_host.end_group_calls == 1
        assert undo_host.undo_calls == 1

    def test_f01_direct_stage_write_probe_blocked(self):
        """
        Regresión directa de `scratch/audit-20261029-probes.py` ('direct_stage_write'):
        escrituras USD directas que omiten el historial de Undo son rechazadas.
        """
        policy = SpatialSecurityPolicy()
        probe_cases = [
            "stage=omni.usd.get_context().get_stage()\nstage.DefinePrim('/World/AuditCube','Cube')",
            "from pxr import UsdGeom\nUsdGeom.Cube.Define(stage, '/World/DirectCube')",
            "stage.RemovePrim('/World/Cube')",
        ]
        controller = USDController(policy=policy)

        for code in probe_cases:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Debió bloquear escritura directa USD: {code}"
            assert "Undo" in err

            res = controller.execute_code(code)
            assert res["success"] is False
            assert res["error_type"] == "SecurityPolicyError"


# ===========================================================================
# F05 · Regresiones de Ejecución Acotada, Cancelación Real y Afinidad de Hilo
# ===========================================================================

class TestF05BoundedCancellableExecution:
    """Regresiones estrictas para F05: acotamiento, cancelación cooperativa y afinidad de hilo."""

    def test_f05_sleep_main_thread_probe_blocked(self):
        """Regresión directa de sonda `sleep_main_thread` (`import time; time.sleep(0.03)`)."""
        policy = SpatialSecurityPolicy()
        for code in [
            "import time\ntime.sleep(0.03)",
            "from time import sleep\nsleep(0.01)",
            "import time as t\nt.sleep(0.01)",
        ]:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Debió bloquear sleep bloqueante: {code}"
            assert "time.sleep" in err or "forbidden module" in err

    def test_f05_dynamic_loop_limit_probe_blocked_statically_and_at_runtime(self):
        """
        Regresión directa de sonda `dynamic_loop_limit`:
        - Constante propagada `limit = 1000000000` bloqueada estáticamente en AST.
        - Límite dinámico real bloqueado en tiempo de ejecución por ExecutionBudget sin correr bucles enormes.
        """
        policy = SpatialSecurityPolicy()
        probe_code = "limit=1000000000\nfor i in range(limit):\n    pass"
        valid, err = policy.validate_code(probe_code)
        assert valid is False
        assert "Loop iteration limit" in err

        # Límite no resoluble estáticamente (construido dinámicamente) acotado en runtime
        dynamic_code = """
n = len("a" * 50) * 20
total = 0
for i in range(n):
    total += i
"""
        valid_dyn, _ = policy.validate_code(dynamic_code)
        assert valid_dyn is True

        tight_budget = ExecutionBudget(max_loop_iterations=100, max_total_steps=500)
        controller = USDController(policy=policy, default_budget=tight_budget)
        res = controller.execute_code(dynamic_code, budget=tight_budget)
        assert res["success"] is False
        assert res["error_type"] == "ExecutionBudgetExceededError"
        assert "exceeded" in res["error_msg"].lower()

    @pytest.mark.asyncio
    async def test_f05_kit_main_thread_slices_serve_ui_and_cancel_halts_next_slice_with_rollback(self):
        """
        Demuestra que un script con mutaciones USD:
        1. Se clasifica y ejecuta en el hilo principal de Kit (sin mover omni/pxr a otro hilo).
        2. Cede control cooperativamente al event loop para que la UI siga atendida entre tramos.
        3. Al cancelar vía CancellationToken, detiene efectivamente el trabajo (el siguiente tramo
           NUNCA se ejecuta) y revierte atómicamente los prims parcialmente creados.
        """
        stage, undo_host, _, omni_ns = _make_strict_kit_host()
        main_thread_id = threading.get_ident()
        token = CancellationToken()
        budget = ExecutionBudget(
            max_wall_time_seconds=5.0,
            max_loop_iterations=500,
            slice_yield_interval_seconds=0.0,
            yield_every_n_steps=2,
        )

        script = """
for i in range(100):
    controller.create_prim("Cube", f"/World/SliceCube_{i}")
"""
        policy = SpatialSecurityPolicy()
        assert policy.classify_execution_affinity(script) == ExecutionAffinity.KIT_MAIN_THREAD

        ui_ticks = 0
        exec_done = False

        async def simulated_ui_pump():
            nonlocal ui_ticks
            while not exec_done and not token.is_cancellation_requested:
                ui_ticks += 1
                if ui_ticks >= 3 and len(stage) >= 2:
                    token.cancel()
                    break
                await asyncio.sleep(0)

        with patch.object(uc, "omni", omni_ns):
            controller = USDController(policy=policy, default_budget=budget)
            ui_task = asyncio.create_task(simulated_ui_pump())
            try:
                result = await controller.execute_code_async(
                    script,
                    budget=budget,
                    cancellation_token=token,
                )
            finally:
                exec_done = True
                await ui_task

        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.cancelled is True
        assert result.error_type == "ExecutionCancelledError"
        assert result.partial_changes_rolled_back is True
        # La UI recibió ticks mientras el script corría por tramos
        assert ui_ticks >= 3
        assert result.metadata["yield_count"] >= 1
        # Afinidad estricta de hilo principal de Kit
        assert result.metadata["affinity"] == ExecutionAffinity.KIT_MAIN_THREAD.value
        assert result.metadata["execution_thread_id"] == main_thread_id
        # Se detuvo mucho antes de completar las 100 iteraciones
        stopped_iters = result.metadata["loop_iterations"]
        assert 1 <= stopped_iters < 100
        # Rollback atómico dejó el Stage limpio
        assert stage == {}
        assert undo_host.undo_calls == 1

        # Esperar unos ciclos del loop y confirmar que no se ejecutó ningún tramo posterior
        await asyncio.sleep(0.01)
        assert stage == {}

    @pytest.mark.asyncio
    async def test_f05_pure_compute_runs_off_main_thread_and_worker_actually_stops_on_cancel(self):
        """
        Demuestra que el cálculo puro (sin omni/pxr):
        1. Se clasifica como PURE_COMPUTE y corre en un worker thread separado (sin tocar Undo).
        2. Al activar CancellationToken, el hilo trabajador realmente detiene el cálculo
           y finaliza (worker_stopped=True), a diferencia de Future.cancel() sobre exec bloqueante.
        """
        _, undo_host, _, omni_ns = _make_strict_kit_host()
        main_thread_id = threading.get_ident()
        token = CancellationToken()
        budget = ExecutionBudget(max_wall_time_seconds=5.0, max_loop_iterations=100_000, max_total_steps=300_000)

        # Dos bucles legítimos dentro del límite estático (200 * 400 = 80,000 iteraciones cooperativas)
        pure_compute_script = """
acc = 0
for i in range(200):
    for j in range(400):
        acc += (i * 3 + j) % 17
"""
        policy = SpatialSecurityPolicy()
        assert policy.classify_execution_affinity(pure_compute_script) == ExecutionAffinity.PURE_COMPUTE

        # Sincronizar determinísticamente el inicio real del worker thread antes de cancelar
        worker_entered = threading.Event()
        orig_check_sync = uc._ExecutionGuard.check_sync

        def observed_check_sync(guard_self, is_loop_iter: bool = False):
            if guard_self.loop_iterations >= 50:
                worker_entered.set()
            return orig_check_sync(guard_self, is_loop_iter=is_loop_iter)

        with patch.object(uc, "omni", omni_ns), patch.object(uc._ExecutionGuard, "check_sync", observed_check_sync):
            controller = USDController(policy=policy, default_budget=budget)
            exec_task = asyncio.create_task(
                controller.execute_code_async(
                    pure_compute_script,
                    budget=budget,
                    cancellation_token=token,
                )
            )
            # Esperar cooperativamente a que el worker efectivamente haya iniciado el cálculo
            while not worker_entered.is_set() and not exec_task.done():
                await asyncio.sleep(0.001)
            token.cancel()
            result = await exec_task

        assert result.cancelled is True
        assert result.success is False
        assert result.error_type == "ExecutionCancelledError"
        assert result.metadata["affinity"] == ExecutionAffinity.PURE_COMPUTE.value
        assert result.metadata["execution_thread_id"] != main_thread_id
        assert result.metadata["worker_stopped"] is True
        assert 50 <= result.metadata["loop_iterations"] < 80_000
        # Cálculo puro no debe ensuciar la pila de Undo de Kit
        assert undo_host.begin_group_calls == 0
        assert undo_host.end_group_calls == 0

    def test_f05_except_exception_and_bare_except_cannot_swallow_cancellation_or_budget(self):
        """Un `try/except Exception` o `except:` en código generado NO puede silenciar cancelación ni presupuesto."""
        controller = USDController()
        token = CancellationToken()
        token.cancel()

        swallow_scripts = [
            """
try:
    x = 1
except Exception:
    x = 2
""",
            """
try:
    x = 1
except:
    x = 2
""",
        ]
        for script in swallow_scripts:
            res = controller.execute_code(script, cancellation_token=token)
            assert res["success"] is False
            assert res["cancelled"] is True
            assert res["error_type"] == "ExecutionCancelledError"

    @pytest.mark.asyncio
    async def test_f05_agent_manager_execution_engine_and_nonblocking_extension_callback(self, tmp_path, monkeypatch):
        """Verifica contrato IExecutionEngine en AgentManager y despacho no bloqueante en LMChatExtension."""
        monkeypatch.setenv("LM_CHAT_STORAGE_PATH", str(tmp_path))

        stage, undo_host, _, omni_ns = _make_strict_kit_host()
        with patch.object(uc, "omni", omni_ns):
            manager = AgentManager(
                execution_mode=ExecutionMode.PLAN_AND_CONFIRM.value,
                execution_budget=ExecutionBudget(
                    max_loop_iterations=500,
                    slice_yield_interval_seconds=0.0,
                    yield_every_n_steps=2,
                ),
            )
            assert isinstance(manager, IExecutionEngine)

            # Dry run valida sin ejecutar mutaciones
            dry_res = manager.execute_script("controller.create_prim('Cube', '/World/DryCube')", dry_run=True)
            assert dry_res.success is True
            assert stage == {}

            # Probar ejecución asíncrona no bloqueante desde callback _on_plan_action de LMChatExtension
            ext = LMChatExtension()
            ext.on_startup("test_f05_ext")
            try:
                ext._agent_manager = manager
                manager._pending_code = """
for i in range(60):
    controller.create_prim("Cube", f"/World/GuiCube_{i}")
"""
                # _on_plan_action("execute") debe regresar sin bloquear, programando una Task
                ext._on_plan_action("execute")
                plan_task = ext._active_plan_task
                assert plan_task is not None
                assert not plan_task.done()

                # Permitir algunos tramos y luego cancelar desde la acción UI "cancel"
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                ext._on_plan_action("cancel")
                await plan_task

                # Cambios parciales revertidos por la cancelación cooperativa
                assert stage == {}
                assert undo_host.undo_calls >= 1
            finally:
                ext.on_shutdown()


# ===========================================================================
# F06 · Regresiones de Frontera de Capacidades, Alias, Falsos Positivos y Secretos
# ===========================================================================

class TestF06CapabilitiesAndDiagnostics:
    """Regresiones estrictas para F06."""

    def test_f06_builtins_eval_probe_blocked_by_ast_and_runtime_layer(self):
        """
        Regresión directa de `scratch/audit-20261029-probes.py` ('builtin_alias' y 'BUILTINS_EXEC'):
        `import builtins; value=builtins.eval('2+2')` falla tanto en AST como en runtime SAFE_BUILTINS.
        """
        policy = SpatialSecurityPolicy()
        probe = "import builtins\nvalue=builtins.eval('2+2')\nassert value==4"

        valid, err = policy.validate_code(probe)
        assert valid is False
        assert "eval" in err or "builtins" in err

        controller = USDController(policy=policy)
        res = controller.execute_code(probe)
        assert res["success"] is False

        # Defensa en profundidad: incluso si se omitiera el filtro AST, SAFE_BUILTINS bloquea la ejecución
        safe_builtins = policy.get_safe_builtins()
        for forbidden_name in ("eval", "exec", "compile", "open", "breakpoint", "globals", "locals", "vars"):
            assert forbidden_name not in safe_builtins

        with pytest.raises(ImportError, match="Security Policy Violation"):
            exec(probe, {"__builtins__": safe_builtins})

        with pytest.raises(NameError):
            exec("value = eval('2+2')", {"__builtins__": safe_builtins})

    def test_f06_aliases_and_dunder_escapes_blocked(self):
        """Rechaza alias de builtins, escapes por dunders, getattr peligroso y llamadas os.* peligrosas."""
        policy = SpatialSecurityPolicy()
        bypass_attempts = [
            "import builtins as b\nb.eval('2+2')",
            "from builtins import eval as e\ne('2+2')",
            "fn = eval\nfn('2+2')",
            "x = ().__class__.__base__.__subclasses__()",
            "x = __builtins__['eval']('2+2')",
            "x = getattr((), '__class__')",
            "import sys\nx = sys.modules",
            "import importlib\nimportlib.import_module('os')",
            "import os\nos.replace('a', 'b')",
            "import os as o\no.remove('/tmp/x')",
            "from os import replace as r\nr('a', 'b')",
        ]
        for code in bypass_attempts:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Bypass no bloqueado: {code}"
            assert "Security Policy Violation" in err

        # Verificar también que _safe_getattr y _safe_type en runtime bloquean evasiones
        safe_builtins = policy.get_safe_builtins()
        with pytest.raises(AttributeError):
            safe_builtins["getattr"]((), "__class__")
        with pytest.raises(TypeError):
            safe_builtins["type"]("Dyn", (), {})  # type() restringido a 1 argumento

    def test_f06_str_replace_and_benign_python_allowed_and_executed(self):
        """
        Regresión directa de `scratch/audit-20261029-probes.py` ('str_replace_false_positive')
        y otras operaciones benignas legítimas de Python/OpenUSD.
        """
        policy = SpatialSecurityPolicy()
        controller = USDController(policy=policy)

        benign_scripts = [
            "path = '/World/old'.replace('old', 'new')\nassert path == '/World/new'",
            "items = ['a', 'b', 'c']\nitems.remove('b')\nassert items == ['a', 'c']",
            "import math, json\nval = round(math.sin(math.pi / 2), 4)\npayload = json.dumps({'v': val})\nassert val == 1.0",
            "coords = [i * 2 for i in range(10) if i % 2 == 0]\nassert len(coords) == 5",
            "assert hasattr(controller, 'create_prim') is True\nassert type(42) is int",
        ]
        for code in benign_scripts:
            valid, err = policy.validate_code(code)
            assert valid is True, f"Falso positivo en código benigno: {code} -> {err}"
            assert err is None

            res = controller.execute_code(code)
            assert res["success"] is True, f"Fallo ejecutando código benigno: {code} -> {res}"

    def test_f06_structured_error_context_and_secret_redaction(self):
        """Errores en ejecución incluyen tipo, línea, traceback útil y redactan cualquier secreto."""
        controller = USDController()
        leaking_code = """
a = 1
b = 2
secret_msg = "Fallo auth sk-test1234567890abcdef nvapi-9876543210fedcba Bearer eyJhbGciOiJIUzI1NiJ9 api_key=my_top_secret_99"
raise ValueError(secret_msg)
"""
        res = controller.execute_code(leaking_code)

        assert res["success"] is False
        assert res["error_type"] == "ValueError"
        assert res["line_number"] == 5
        assert "<lmchat_script>" in res["traceback_str"]

        # Ningún secreto en texto claro debe aparecer ni en error_msg ni en traceback_str
        combined = f"{res['error_msg']}\n{res['traceback_str']}"
        for raw_secret in (
            "sk-test1234567890abcdef",
            "nvapi-9876543210fedcba",
            "eyJhbGciOiJIUzI1NiJ9",
            "my_top_secret_99",
        ):
            assert raw_secret not in combined

        assert "sk-***" in combined
        assert "nvapi-***" in combined
        assert "Bearer ***" in combined
        assert "api_key=***" in combined
        assert redact_secrets("Valor normal sin secretos") == "Valor normal sin secretos"

        # P2-1: Redacción en cadenas JSON y reprs de diccionarios Python con comillas antes de ':'
        json_secret = redact_secrets('{"api_key": "my_secret_json_999", "token": "tok_secret_value_123"}')
        dict_secret = redact_secrets("{'password': 'my_dict_password'}")
        assert "my_secret_json_999" not in json_secret
        assert "tok_secret_value_123" not in json_secret
        assert "my_dict_password" not in dict_secret


# ===========================================================================
# Regresiones de endurecimiento derivadas de la Auditoría Independiente (P1-1..P1-5)
# ===========================================================================

class TestIndependentAuditHardeningRegressions:
    """Regresiones específicas para todos los hallazgos P1/P2 de la auditoría independiente."""

    def test_p1_1_nested_group_prims_failure_preserves_prior_user_undo_history(self):
        """P1-1: Un fallo parcial de group_prims() dentro de execute_code() NO debe borrar acciones previas del usuario."""
        stage, undo_host, _, omni_ns = _make_strict_kit_host()
        with patch.object(uc, "omni", omni_ns):
            controller = USDController()
            # Acción previa confirmada del usuario
            r1 = controller.execute_code("controller.create_prim('Cube', '/World/UserPreExisting')")
            assert r1["success"] is True
            assert "/World/UserPreExisting" in stage

            # Segundo script: group_prims falla por prim inexistente pero el script captura el error
            r2 = controller.execute_code("""
controller.create_prim("Cube", "/World/TempBox")
grp_res = controller.group_prims(["/World/TempBox", "/World/MissingPrim"], "/World/NewGroup")
assert grp_res["success"] is False
""")
            assert r2["success"] is True
            # El prim previo del usuario DEBE seguir existiendo y el Scope huérfano fue limpiado
            assert "/World/UserPreExisting" in stage
            assert "/World/TempBox" in stage
            assert "/World/NewGroup" not in stage
            assert undo_host.undo_calls == 0

    def test_p1_2_empty_group_failure_never_undoes_prior_user_action_and_preserves_prev_attr(self):
        """P1-2: Un script que falla sin mutar el Stage nunca deshace la acción previa; ChangePropertyCommand captura prev real."""
        stage, undo_host, commands_host, omni_ns = _make_strict_kit_host(push_empty_groups=False)
        with patch.object(uc, "omni", omni_ns):
            controller = USDController()
            r1 = controller.execute_code("controller.create_prim('Cube', '/World/PriorUserCube', attributes={'size': 2.0})")
            assert r1["success"] is True
            assert stage["/World/PriorUserCube"]["attributes"]["size"] == 2.0

            # Script que falla sin tocar el Stage
            r_err = controller.execute_code("x = 1 / 0")
            assert r_err["success"] is False
            assert r_err["partial_changes_rolled_back"] is False
            assert "/World/PriorUserCube" in stage
            assert undo_host.undo_calls == 0

            # set_prim_attribute debe pasar prev=2.0 real a ChangePropertyCommand y restaurar 2.0 al hacer undo()
            r_attr = controller.set_prim_attribute("/World/PriorUserCube", "size", 9.5)
            assert r_attr["success"] is True
            assert stage["/World/PriorUserCube"]["attributes"]["size"] == 9.5
            last_cmd, last_kwargs = commands_host.call_log[-1]
            assert last_cmd == "ChangePropertyCommand"
            assert last_kwargs["prev"] == 2.0

            assert undo_host.undo() is True
            assert stage["/World/PriorUserCube"]["attributes"]["size"] == 2.0

    def test_p1_3_guard_hooks_mro_finally_return_and_c_loops_hardened(self):
        """P1-3: Bloquea sobrescritura de __lmchat_*, .mro(), finally: return, itertools y acota sum()."""
        policy = SpatialSecurityPolicy()
        blocked_cases = [
            "__lmchat_sync_step__ = lambda *a, **k: None\nx = 1",
            "__lmchat_iter__ = lambda it: it\nx = 1",
            "try:\n    x = 1\nexcept Exception.mro()[1]:\n    pass",
            "def sneak():\n    try:\n        x = 1\n    finally:\n        return 'swallowed'\nsneak()",
            "import itertools\ntotal = sum(itertools.repeat(1, 20000))",
            "return 1",
            "yield 1",
        ]
        for code in blocked_cases:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Debió rechazarse: {code}"

        # Builtins consumidores en C (sum, list) respetan ExecutionBudget
        tight_budget = ExecutionBudget(max_loop_iterations=25, max_total_steps=100)
        controller = USDController(policy=policy, default_budget=tight_budget)
        res = controller.execute_code("total = sum(range(20))\nmore = sum([1] * 30)", budget=tight_budget)
        assert res["success"] is False
        assert res["error_type"] == "ExecutionBudgetExceededError"

    @pytest.mark.asyncio
    async def test_p1_4_class_global_async_comprehension_and_delete_prims_work_in_sync_and_async(self):
        """P1-4: class, global en funciones, async comprehensions y delete_prims funcionan en sync y async."""
        stage, _, _, omni_ns = _make_strict_kit_host()
        policy = SpatialSecurityPolicy()

        # delete_prims debe clasificarse como KIT_MAIN_THREAD
        assert policy.classify_execution_affinity('delete_prims(["/World/Cube"])') == ExecutionAffinity.KIT_MAIN_THREAD

        # from math import * rechazado consistentemente
        valid_star, err_star = policy.validate_code("from math import *\nx = sin(0)")
        assert valid_star is False
        assert "Wildcard import" in err_star

        class_and_global_script = """
COUNTER = 0
class Point:
    def __init__(self, x):
        self.x = x

def bump_and_create():
    global COUNTER
    COUNTER += 1
    p = Point(COUNTER)
    controller.create_prim("Cube", f"/World/Pt_{p.x}")

bump_and_create()
bump_and_create()
assert COUNTER == 2
delete_prims(["/World/Pt_1"])
"""
        with patch.object(uc, "omni", omni_ns):
            controller = USDController(policy=policy)
            # Sync
            res_sync = controller.execute_code(class_and_global_script)
            assert res_sync["success"] is True, f"Sync falló: {res_sync}"
            assert "/World/Pt_1" not in stage
            assert "/World/Pt_2" in stage

            stage.clear()
            # Async (KIT_MAIN_THREAD)
            res_async = await controller.execute_code_async(class_and_global_script)
            assert res_async.success is True, f"Async falló: {res_async}"
            assert "/World/Pt_1" not in stage
            assert "/World/Pt_2" in stage

            # Comprensión asíncrona ejecutada realmente mediante _CooperativeASTTransformer + wrap_aiter
            async_def_script = """
async def agen():
    for i in range(3):
        yield i

async def collect():
    return [x * 2 async for x in agen()]
"""
            compiled_ac = controller._compile_instrumented(async_def_script, async_mode=True)
            guard_ac = uc._ExecutionGuard(ExecutionBudget(), CancellationToken())
            g_ac = controller._build_exec_globals(guard_ac, include_kit_bindings=True)
            exec(compiled_ac, g_ac)
            await g_ac["__lmchat_entry__"]()
            vals = await g_ac["collect"]()
            assert vals == [0, 2, 4]

    def test_p1_5_controller_proxy_frozen_config_stdlib_reexports_and_usd_write_bypasses_blocked(self):
        """P1-5: controller proxy impide mutar policy.config; módulos stdlib sanitizados; bypasses USD bloqueados."""
        stage, _, _, omni_ns = _make_strict_kit_host()
        policy = SpatialSecurityPolicy()

        # AgentPolicyConfig es inmutable
        with pytest.raises(Exception):
            policy.config.protected_paths = ()  # type: ignore[misc]

        with patch.object(uc, "omni", omni_ns):
            controller = USDController(policy=policy)
            # Intentar acceder a controller.policy o controller.execute_code falla
            res_tamper = controller.execute_code("controller.policy.config.protected_paths = ()")
            assert res_tamper["success"] is False
            assert policy.is_prim_protected("/Render/Camera") is True

            res_exec_attr = controller.execute_code("controller.execute_code('x = 1')")
            assert res_exec_attr["success"] is False

        # Bypasses de stdlib re-exports y escrituras USD directas rechazados en AST
        bypass_cases = [
            "import dataclasses\nb = dataclasses.sys.modules['builtins']\nfn = b.eval\nfn('2+2')",
            "import uuid\nx = list(uuid.os.environ.keys())",
            "import random\nx = random._os",
            "import pxr.UsdGeom as g\ng.Cube.Define(None, '/World/BypassCube')",
            "fn = stage.DefinePrim\nfn('/World/BypassCube', 'Cube')",
            "prim.GetAttribute('xformOp:translate').Set((1, 2, 3))",
            "stage.Save()",
        ]
        for code in bypass_cases:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Bypass P1-5 no bloqueado: {code}"

        # Defensa en profundidad en runtime: módulos stdlib importados vía SAFE_BUILTINS ocultan sys/os/_os
        safe_builtins = policy.get_safe_builtins()
        dc_mod = safe_builtins["__import__"]("dataclasses")
        uuid_mod = safe_builtins["__import__"]("uuid")
        rand_mod = safe_builtins["__import__"]("random")
        dt_mod = safe_builtins["__import__"]("datetime")

        assert hasattr(dc_mod, "dataclass")
        assert hasattr(uuid_mod, "uuid4")
        assert hasattr(rand_mod, "uniform")
        assert hasattr(dt_mod, "datetime")
        assert hasattr(dt_mod, "time")  # Clase datetime.time permitida

        with pytest.raises(AttributeError):
            _ = dc_mod.sys
        with pytest.raises(AttributeError):
            _ = uuid_mod.os
        with pytest.raises(AttributeError):
            _ = rand_mod._os

    def test_p1_r2_1_native_collection_types_preserved_and_constructors_bounded(self):
        """P1-R2-1: list/tuple/set/frozenset siguen siendo tipos nativos (isinstance, PEP 585, herencia) pero acotados."""
        controller = USDController()
        native_types_script = """
assert isinstance([1, 2, 3], list)
assert isinstance((1, 2), tuple)
assert isinstance({1, 2}, set)
assert isinstance(frozenset([1]), frozenset)
assert type([1, 2]) is list
assert type((1, 2)) is tuple

def summarize(paths: list[str]) -> tuple[int, set[str]]:
    return (len(paths), set(paths))

class CustomList(list):
    pass

cl = CustomList([1, 2])
assert isinstance(cl, list) and len(cl) == 2
cnt, uniq = summarize(["/World/A", "/World/B", "/World/A"])
assert cnt == 3 and len(uniq) == 2
"""
        res = controller.execute_code(native_types_script)
        assert res["success"] is True, f"Tipos nativos rotos: {res}"

        # Constructor list(...) sigue respetando ExecutionBudget vía instrumentación AST
        tight_budget = ExecutionBudget(max_loop_iterations=10, max_total_steps=50)
        res_bounded = controller.execute_code("xs = list(range(50))", budget=tight_budget)
        assert res_bounded["success"] is False
        assert res_bounded["error_type"] == "ExecutionBudgetExceededError"

    def test_p1_r2_2_formatter_get_field_and_transitive_stdlib_submodules_blocked(self):
        """P1-R2-2: string.Formatter.get_field y submódulos transitivos crudos (json.codecs, typing.contextlib, etc.) bloqueados."""
        policy = SpatialSecurityPolicy()
        controller = USDController(policy=policy)

        escape_scripts = [
            "import string\nfmt = string.Formatter()\nraw_ctrl, _ = fmt.get_field('0._controller', (controller,), {})",
            "import string\nfmt = string.Formatter()\ng, _ = fmt.get_field('0.__globals__', (fmt.get_field,), {})",
            "attr = prim.GetAttribute('xformOp:translate')\nattr.Set((1.0, 2.0, 3.0))",
            "omni.usd.get_context().get_stage().Save()",
            "stage.Export('/tmp/out.usda')",
            "x = 2 ** 20000",
        ]
        for code in escape_scripts:
            valid, err = policy.validate_code(code)
            assert valid is False, f"Escape P1-R2-2/P2-R2 no bloqueado: {code}"

        # Defensa en profundidad en runtime: submódulos transitivos no permitidos ocultos y permitidos sanitizados recursivamente
        safe_builtins = policy.get_safe_builtins()
        string_mod = safe_builtins["__import__"]("string")
        json_mod = safe_builtins["__import__"]("json")
        typing_mod = safe_builtins["__import__"]("typing")
        stats_mod = safe_builtins["__import__"]("statistics")
        re_mod = safe_builtins["__import__"]("re")

        assert not hasattr(string_mod, "Formatter")
        assert not hasattr(json_mod, "codecs")
        assert not hasattr(typing_mod, "contextlib")
        assert not hasattr(typing_mod, "warnings")
        if hasattr(stats_mod, "random"):
            assert not hasattr(stats_mod.random, "_os")
        if hasattr(re_mod, "enum"):
            assert not hasattr(re_mod.enum, "sys")
        if hasattr(typing_mod, "collections"):
            assert not hasattr(typing_mod.collections, "_sys")

        # Proxy del controlador no tiene atributo _controller en la instancia
        proxy = uc._make_safe_controller_proxy(controller)
        assert not hasattr(proxy, "_controller")
        assert not hasattr(proxy, "policy")
        assert not hasattr(proxy, "execute_code")

    def test_p1_r2_3_trystar_finally_return_and_two_arg_iter_bounded(self):
        """P1-R2-3: TryStar (except*) con finally: return bloqueado; iter(fn, sentinel) + join acotado por ExecutionBudget."""
        policy = SpatialSecurityPolicy()
        trystar_code = """
def sneak():
    try:
        x = 1
    except* ValueError:
        pass
    finally:
        return "swallowed"
sneak()
"""
        valid, err = policy.validate_code(trystar_code)
        assert valid is False
        assert "finally" in err

        # iter(callable, sentinel) dentro de "".join(...) debe respetar ExecutionBudget y cancelación
        tight_budget = ExecutionBudget(max_loop_iterations=25, max_total_steps=100)
        controller = USDController(policy=policy, default_budget=tight_budget)
        iter_join_code = """
c = []
s = "".join(iter(lambda: (c.append(1) or "x") if len(c) < 200 else None, None))
"""
        res = controller.execute_code(iter_join_code, budget=tight_budget)
        assert res["success"] is False
        assert res["error_type"] == "ExecutionBudgetExceededError"
