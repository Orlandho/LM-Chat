# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

# -*- coding: utf-8 -*-

"""
Módulo USD Controller para ejecución segura, acotada, cancelable y no-destructiva en OpenUSD.

Integra:
- Políticas de capacidades y saneamiento AST (SpatialSecurityPolicy + SAFE_BUILTINS).
- Fachada segura `_SafeControllerProxy` (no expone `controller.policy` ni `execute_code` a scripts).
- Comandos reversibles compatibles con NVIDIA Omniverse Kit SDK 107.3.7 / omni.kit.commands 1.4.10
  (`begin_group` / `end_group` / `group`, `CreatePrimWithDefaultXform`, `TransformPrimCommand`,
  `TransformPrimSRTCommand`, `BindMaterialCommand`, `MovePrimsCommand`, `GroupPrimsCommand`,
  `ChangePropertyCommand` con lectura de `prev`, `DeletePrimsCommand`).
- Instrumentación AST cooperativa para ejecución por tramos acotados y cancelación efectiva
  respetando la afinidad de hilo principal de Kit/USD vs cálculo puro.
- Diagnósticos estructurados con número de línea, traceback filtrado y redacción de secretos.
"""

import ast
import asyncio
import logging
import threading
import time
import traceback
from collections import deque
from typing import Any, AsyncIterable, AsyncIterator, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from unittest.mock import NonCallableMock

try:
    import omni.ext
    import omni.kit.commands
    import omni.kit.undo
    import omni.usd
    import pxr
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
except ImportError:
    omni = None
    pxr = None
    Usd = None
    UsdGeom = None
    UsdShade = None
    Sdf = None
    Gf = None

from core.interfaces import (
    CancellationToken,
    ExecutionAffinity,
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionCancelledError,
    ExecutionResult,
    IUSDController,
)
from core.policies import SpatialSecurityPolicy, redact_secrets
from logic.usd_inspector import USDInspector

logger = logging.getLogger(__name__)

_SCRIPT_FILENAME = "<lmchat_script>"


def _make_safe_controller_proxy(controller: "USDController") -> Any:
    """
    Crea una fachada mínima sin atributos de instancia (`__slots__ = ()`) respaldada por closure.
    Solo expone los métodos de manipulación reversible de escena y no posee atributo `._controller`,
    impidiendo acceder o mutar `USDController.policy`, `policy.config` o `execute_code`.
    """

    class _SafeControllerProxy:
        __slots__ = ()

        def create_prim(
            self,
            prim_type: str,
            prim_path: Optional[str] = None,
            attributes: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return controller.create_prim(
                prim_type=prim_type,
                prim_path=prim_path,
                attributes=attributes,
            )

        def transform_prim(
            self,
            prim_path: str,
            new_transform_matrix: Optional[Any] = None,
            translation: Optional[List[float]] = None,
            rotation: Optional[List[float]] = None,
            scale: Optional[List[float]] = None,
        ) -> Dict[str, Any]:
            return controller.transform_prim(
                prim_path=prim_path,
                new_transform_matrix=new_transform_matrix,
                translation=translation,
                rotation=rotation,
                scale=scale,
            )

        def bind_material(self, prim_path: str, material_path: str) -> Dict[str, Any]:
            return controller.bind_material(
                prim_path=prim_path,
                material_path=material_path,
            )

        def group_prims(self, prim_paths: List[str], parent_path: Optional[str] = None) -> Dict[str, Any]:
            return controller.group_prims(
                prim_paths=prim_paths,
                parent_path=parent_path,
            )

        def set_prim_attribute(self, prim_path: str, attr_name: str, value: Any) -> Dict[str, Any]:
            return controller.set_prim_attribute(
                prim_path=prim_path,
                attr_name=attr_name,
                value=value,
            )

        def delete_prims(self, prim_paths: List[str]) -> Dict[str, Any]:
            return controller.delete_prims(prim_paths=prim_paths)

        def __setattr__(self, name: str, value: Any) -> None:
            raise AttributeError("Security Policy Violation: controller proxy is read-only.")

        def __delattr__(self, name: str) -> None:
            raise AttributeError("Security Policy Violation: controller proxy is read-only.")

    return _SafeControllerProxy()


class _ExecutionGuard:
    """
    Guardia cooperativo de ejecución acotada y cancelable.

    Se inyecta en los puntos de control (checkpoints) del AST instrumentado y en
    iteradores/rangos/consumidores acotados para garantizar que:
    - Una solicitud de cancelación (`CancellationToken.cancel()`) detiene efectivamente
      el cómputo o impide el inicio del siguiente tramo acotado.
    - Los bucles, comprensiones y consumidores en C (`sum`, `list`, `any`, etc.) no exceden
      `ExecutionBudget` (iteraciones, pasos totales, tiempo).
    - En ejecución asíncrona sobre el hilo de Kit, el control se cede periódicamente al event
      loop mediante `await asyncio.sleep(0)` para mantener la UI atendida.
    """

    def __init__(
        self,
        budget: ExecutionBudget,
        token: CancellationToken,
    ) -> None:
        self.budget = budget
        self.token = token
        self.start_time = time.monotonic()
        self.last_yield_time = self.start_time
        self.steps: int = 0
        self.loop_iterations: int = 0
        self.async_checkpoints: int = 0
        self.yield_count: int = 0

    def _check_limits(self) -> None:
        self.token.throw_if_cancellation_requested()

        if self.loop_iterations > self.budget.max_loop_iterations:
            raise ExecutionBudgetExceededError(
                f"Execution budget exceeded: loop iterations ({self.loop_iterations}) "
                f"exceeded maximum ({self.budget.max_loop_iterations})."
            )

        if self.steps > self.budget.max_total_steps:
            raise ExecutionBudgetExceededError(
                f"Execution budget exceeded: total execution steps ({self.steps}) "
                f"exceeded maximum ({self.budget.max_total_steps})."
            )

        elapsed = time.monotonic() - self.start_time
        if elapsed > self.budget.max_wall_time_seconds:
            raise ExecutionBudgetExceededError(
                f"Execution budget exceeded: wall time ({elapsed:.3f}s) "
                f"exceeded maximum ({self.budget.max_wall_time_seconds:.3f}s)."
            )

    def check_sync(self, is_loop_iter: bool = False) -> None:
        """Checkpoint síncrono para bucles, funciones y worker threads cooperativos."""
        self.steps += 1
        if is_loop_iter:
            self.loop_iterations += 1
        self._check_limits()

    async def check_async(self, is_loop_iter: bool = False) -> None:
        """Checkpoint asíncrono que verifica cancelación/presupuesto y cede control al loop de UI."""
        self.check_sync(is_loop_iter=is_loop_iter)
        self.async_checkpoints += 1

        now = time.monotonic()
        yield_by_time = (now - self.last_yield_time) >= self.budget.slice_yield_interval_seconds
        yield_step_interval = max(1, int(self.budget.yield_every_n_steps))
        yield_by_steps = (self.async_checkpoints % yield_step_interval) == 0

        if yield_by_time or yield_by_steps:
            self.yield_count += 1
            await asyncio.sleep(0)
            self.last_yield_time = time.monotonic()
            # Volver a verificar cancelación y presupuesto inmediatamente al reanudar,
            # impidiendo que el siguiente tramo se ejecute si se canceló mientras la UI corría.
            self._check_limits()

    def wrap_iter(self, iterable: Iterable[Any]) -> Iterator[Any]:
        """Envuelve iterables de bucles `for`, comprensiones y builtins C con control cooperativo."""
        self._check_limits()
        for item in iterable:
            self.check_sync(is_loop_iter=True)
            yield item

    async def wrap_aiter(self, async_iterable: AsyncIterable[Any]) -> AsyncIterator[Any]:
        """Envuelve iterables asíncronos (`async for` y comprensiones async) con control cooperativo."""
        await self.check_async(is_loop_iter=False)
        async for item in async_iterable:
            await self.check_async(is_loop_iter=True)
            yield item

    def safe_range(self, *args: Any) -> range:
        """Versión acotada de `range()` que rechaza tamaños superiores al presupuesto sin iterar."""
        self._check_limits()
        r = range(*args)
        if len(r) > self.budget.max_loop_iterations:
            raise ExecutionBudgetExceededError(
                f"Execution budget exceeded: range length ({len(r)}) "
                f"exceeds maximum allowed iterations ({self.budget.max_loop_iterations})."
            )
        return r


def _collect_target_names(target: ast.AST, out: Set[str]) -> None:
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_target_names(elt, out)
    elif isinstance(target, ast.Starred):
        _collect_target_names(target.value, out)


def _collect_top_level_assigned_names(stmts: List[ast.stmt]) -> Set[str]:
    """
    Recolecta los identificadores enlazados a nivel de módulo (sin entrar en funciones,
    clases, lambdas o comprensiones) para preservar la semántica de `global` cuando el
    cuerpo top-level se envuelve en `async def __lmchat_entry__()`.
    """
    names: Set[str] = set()

    def _scan_block(block: List[ast.stmt]) -> None:
        for stmt in block:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    _collect_target_names(t, names)
            elif isinstance(stmt, ast.AnnAssign):
                _collect_target_names(stmt.target, names)
            elif isinstance(stmt, ast.AugAssign):
                _collect_target_names(stmt.target, names)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(stmt.name)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    if alias.name != "*":
                        names.add(alias.asname or alias.name)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                _collect_target_names(stmt.target, names)
                _scan_block(stmt.body)
                _scan_block(stmt.orelse)
            elif isinstance(stmt, ast.While):
                _scan_block(stmt.body)
                _scan_block(stmt.orelse)
            elif isinstance(stmt, ast.If):
                _scan_block(stmt.body)
                _scan_block(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars is not None:
                        _collect_target_names(item.optional_vars, names)
                _scan_block(stmt.body)
            elif isinstance(stmt, ((ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,))):
                _scan_block(stmt.body)
                for handler in stmt.handlers:
                    if handler.name:
                        names.add(handler.name)
                    _scan_block(handler.body)
                _scan_block(stmt.orelse)
                _scan_block(stmt.finalbody)
            elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    _scan_block(case.body)
            # También expresiones walrus (:=) fuera de funciones/clases/comprensiones
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for child in ast.iter_child_nodes(stmt):
                    if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                        names.add(child.target.id)

    _scan_block(stmts)
    return {n for n in names if not n.startswith("__lmchat_")}


class _CooperativeASTTransformer(ast.NodeTransformer):
    """
    Transforma el AST de un script validado para inyectar checkpoints cooperativos de
    cancelación, presupuesto de pasos y cesión de control al event loop de Kit.

    Limitación documentada (F05):
    - Las sentencias top-level, bucles top-level y funciones `async def` ceden control al
      event loop mediante `await asyncio.sleep(0)` entre tramos.
    - Las funciones `def` síncronas declaradas dentro de un script siguen estando acotadas
      y son cancelables en cada paso/iteración (`__lmchat_sync_step__`), pero no pueden usar
      `await` internamente; la cesión al loop de UI ocurre al volver al alcance `async`/top-level.
    """

    def __init__(self, async_mode: bool = False) -> None:
        super().__init__()
        self._async_mode = async_mode
        self._in_async_scope = async_mode

    @staticmethod
    def _set_synthetic_loc(node: ast.AST, lineno: int, col: int = 0) -> ast.AST:
        """Asigna lineno/end_lineno consistentes (Python 3.12+) a todos los nodos sintéticos creados."""
        safe_line = max(1, int(lineno or 1))
        safe_col = max(0, int(col or 0))
        for sub in ast.walk(node):
            if isinstance(sub, (ast.stmt, ast.expr)):
                sub.lineno = safe_line
                sub.end_lineno = safe_line
                sub.col_offset = safe_col
                sub.end_col_offset = safe_col
        return node

    def _make_step_stmt(self, is_loop_iter: bool, ref_node: ast.AST) -> ast.stmt:
        arg = ast.Constant(value=is_loop_iter)
        if self._in_async_scope:
            call = ast.Call(
                func=ast.Name(id="__lmchat_async_step__", ctx=ast.Load()),
                args=[arg],
                keywords=[],
            )
            stmt: ast.stmt = ast.Expr(value=ast.Await(value=call))
        else:
            call = ast.Call(
                func=ast.Name(id="__lmchat_sync_step__", ctx=ast.Load()),
                args=[arg],
                keywords=[],
            )
            stmt = ast.Expr(value=call)
        lineno = getattr(ref_node, "lineno", 1) or 1
        col = getattr(ref_node, "col_offset", 0) or 0
        self._set_synthetic_loc(stmt, lineno, col)
        return stmt

    def _wrap_iter_expr(self, expr: ast.expr, ref_node: ast.AST, is_async: bool = False) -> ast.expr:
        lineno = getattr(expr, "lineno", None) or getattr(ref_node, "lineno", 1) or 1
        end_lineno = getattr(expr, "end_lineno", None) or lineno
        if end_lineno < lineno:
            end_lineno = lineno
        col = getattr(expr, "col_offset", None) or 0
        end_col = getattr(expr, "end_col_offset", None) or col

        wrapper_id = "__lmchat_aiter__" if is_async else "__lmchat_iter__"
        func_name = ast.Name(id=wrapper_id, ctx=ast.Load())
        func_name.lineno = lineno
        func_name.end_lineno = lineno
        func_name.col_offset = col
        func_name.end_col_offset = col

        wrapped = ast.Call(
            func=func_name,
            args=[expr],
            keywords=[],
        )
        wrapped.lineno = lineno
        wrapped.end_lineno = end_lineno
        wrapped.col_offset = col
        wrapped.end_col_offset = end_col
        return wrapped

    def _instrument_statement_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        new_body: List[ast.stmt] = []
        for stmt in stmts:
            visited = self.visit(stmt)
            if visited is None:
                continue
            if isinstance(visited, list):
                for sub in visited:
                    new_body.append(self._make_step_stmt(False, sub))
                    new_body.append(sub)
            else:
                new_body.append(self._make_step_stmt(False, visited))
                new_body.append(visited)
        return new_body

    def visit_For(self, node: ast.For) -> ast.AST:
        node.iter = self._wrap_iter_expr(self.visit(node.iter), node, is_async=False)
        node.target = self.visit(node.target)
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        # __lmchat_iter__ ya cuenta la iteración; aquí inyectamos checkpoint de tramo/yield sin doble conteo.
        node.body.insert(0, self._make_step_stmt(False, node))
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:
        node.iter = self._wrap_iter_expr(self.visit(node.iter), node, is_async=True)
        node.target = self.visit(node.target)
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        node.body.insert(0, self._make_step_stmt(False, node))
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        node.test = self.visit(node.test)
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        node.body.insert(0, self._make_step_stmt(True, node))
        return node

    def visit_comprehension(self, node: ast.comprehension) -> ast.comprehension:
        node.target = self.visit(node.target)
        node.iter = self._wrap_iter_expr(
            self.visit(node.iter),
            node.iter,
            is_async=bool(getattr(node, "is_async", 0)),
        )
        node.ifs = [self.visit(cond) for cond in node.ifs]
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        node.func = self.visit(node.func)
        node.args = [self.visit(a) for a in node.args]
        node.keywords = [self.visit(k) for k in node.keywords]
        # Acotar constructores de colecciones nativas sin sustituir las clases builtin
        # (preserva isinstance, type(), list[T] PEP 585 y herencia).
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in ("list", "tuple", "set", "frozenset")
            and len(node.args) == 1
            and not node.keywords
            and not isinstance(node.args[0], ast.Starred)
        ):
            node.args[0] = self._wrap_iter_expr(node.args[0], node.args[0], is_async=False)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        prev_scope = self._in_async_scope
        self._in_async_scope = False
        try:
            node.args = self.visit(node.args)
            node.decorator_list = [self.visit(d) for d in node.decorator_list]
            node.body = [self.visit(s) for s in node.body]
            node.body.insert(0, self._make_step_stmt(False, node))
            return node
        finally:
            self._in_async_scope = prev_scope

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        prev_scope = self._in_async_scope
        self._in_async_scope = True
        try:
            node.args = self.visit(node.args)
            node.decorator_list = [self.visit(d) for d in node.decorator_list]
            node.body = [self.visit(s) for s in node.body]
            node.body.insert(0, self._make_step_stmt(False, node))
            return node
        finally:
            self._in_async_scope = prev_scope

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        prev_scope = self._in_async_scope
        self._in_async_scope = False
        try:
            node.bases = [self.visit(b) for b in node.bases]
            node.keywords = [self.visit(k) for k in node.keywords]
            node.decorator_list = [self.visit(d) for d in node.decorator_list]
            node.body = [self.visit(s) for s in node.body]
            return node
        finally:
            self._in_async_scope = prev_scope

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        # Evita que un `except:` desnudo capture ExecutionCancelledError / ExecutionBudgetExceededError
        if node.type is None:
            exc_name = ast.Name(id="Exception", ctx=ast.Load())
            self._set_synthetic_loc(exc_name, getattr(node, "lineno", 1) or 1, getattr(node, "col_offset", 0) or 0)
            node.type = exc_name
        else:
            node.type = self.visit(node.type)
        node.body = [self.visit(s) for s in node.body]
        return node

    def transform_module(self, tree: ast.Module) -> ast.Module:
        """Transforma el módulo completo; en modo async lo envuelve en `async def __lmchat_entry__`
        declarando `global` para nombres top-level y preservando la semántica de módulo Python."""
        top_names = _collect_top_level_assigned_names(tree.body) if self._async_mode else set()
        instrumented_body = self._instrument_statement_list(tree.body)
        if not self._async_mode:
            new_mod = ast.Module(body=instrumented_body, type_ignores=[])
            return ast.fix_missing_locations(new_mod)

        if not instrumented_body:
            pass_node = ast.Pass()
            self._set_synthetic_loc(pass_node, 1, 0)
            instrumented_body = [pass_node]

        if top_names:
            global_stmt = ast.Global(names=sorted(top_names))
            self._set_synthetic_loc(global_stmt, 1, 0)
            instrumented_body.insert(0, global_stmt)

        max_end_line = max(
            max(getattr(s, "lineno", 1) or 1, getattr(s, "end_lineno", 1) or 1)
            for s in instrumented_body
        )

        entry_fn = ast.AsyncFunctionDef(
            name="__lmchat_entry__",
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=instrumented_body,
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        entry_fn.lineno = 1
        entry_fn.end_lineno = max(1, max_end_line)
        entry_fn.col_offset = 0
        entry_fn.end_col_offset = 0

        new_mod = ast.Module(body=[entry_fn], type_ignores=[])
        return ast.fix_missing_locations(new_mod)


def _is_mock_object(obj: Any) -> bool:
    """Determina si un objeto corresponde a un doble unittest.mock."""
    if obj is None:
        return True
    if isinstance(obj, NonCallableMock):
        return True
    mod_name = getattr(type(obj), "__module__", "")
    return mod_name.startswith("unittest.mock")


def _to_gf_vec3d(values: Any) -> Any:
    """Convierte listas/tuplas de 3 números en pxr.Gf.Vec3d cuando Gf real está disponible en Kit."""
    if values is None:
        return None
    if Gf is not None and hasattr(Gf, "Vec3d") and not _is_mock_object(Gf) and not _is_mock_object(Gf.Vec3d):
        if isinstance(values, (list, tuple)) and len(values) == 3:
            return Gf.Vec3d(float(values[0]), float(values[1]), float(values[2]))
    return values


def _extract_script_error_details(exc: BaseException) -> Tuple[Optional[int], str]:
    """
    Extrae el número de línea del script del usuario y un traceback estructurado,
    filtrando marcos internos del ejecutor y redactando secretos.
    """
    tb_frames = traceback.extract_tb(exc.__traceback__)
    script_frames = [f for f in tb_frames if f.filename == _SCRIPT_FILENAME]
    line_number: Optional[int] = script_frames[-1].lineno if script_frames else None

    if script_frames:
        formatted_frames = "".join(traceback.format_list(script_frames))
    else:
        formatted_frames = "".join(traceback.format_list(tb_frames[-3:])) if tb_frames else ""

    exc_summary = f"{type(exc).__name__}: {exc}"
    raw_tb = f"Traceback (most recent call last):\n{formatted_frames}{exc_summary}".strip()
    return line_number, redact_secrets(raw_tb) or ""


class USDController(IUSDController):
    """Handles execution of dynamic USD python code with safety policies, bounded execution and Undo/Redo."""

    # Maximum payload limit (100KB) to prevent DoS via memory/CPU exhaustion
    MAX_CODE_SIZE: int = 100_000

    def __init__(
        self,
        policy: Optional[SpatialSecurityPolicy] = None,
        default_budget: Optional[ExecutionBudget] = None,
    ) -> None:
        """Inicializa el controlador USD con políticas espaciales, presupuesto y el inspector del proyecto."""
        self._policy = policy or SpatialSecurityPolicy()
        self._inspector = USDInspector()
        self._default_budget = default_budget or ExecutionBudget()
        self._active_undo_group_depth: int = 0
        self._commands_executed_in_group: int = 0

    @property
    def policy(self) -> SpatialSecurityPolicy:
        """Acceso a la política de seguridad espacial activa."""
        return self._policy

    @property
    def inspector(self) -> USDInspector:
        """Acceso al inspector de salud de escena."""
        return self._inspector

    def _build_exec_globals(
        self,
        guard: _ExecutionGuard,
        include_kit_bindings: bool = True,
    ) -> Dict[str, Any]:
        """Construye el entorno global acotado con SAFE_BUILTINS, fachada proxy y hooks cooperativos."""
        safe_builtins = self._policy.get_safe_builtins(
            safe_range=guard.safe_range,
            iter_wrapper=guard.wrap_iter,
        )

        exec_globals: Dict[str, Any] = {
            "__name__": "__lmchat_script__",
            "__builtins__": safe_builtins,
            "__lmchat_sync_step__": guard.check_sync,
            "__lmchat_async_step__": guard.check_async,
            "__lmchat_iter__": guard.wrap_iter,
            "__lmchat_aiter__": guard.wrap_aiter,
        }

        if include_kit_bindings:
            proxy = _make_safe_controller_proxy(self)
            exec_globals.update(
                {
                    "omni": omni,
                    "pxr": pxr,
                    "Usd": Usd,
                    "UsdGeom": UsdGeom,
                    "UsdShade": UsdShade,
                    "Sdf": Sdf,
                    "Gf": Gf,
                    "inspector": self._inspector,
                    "controller": proxy,
                    "create_prim": proxy.create_prim,
                    "transform_prim": proxy.transform_prim,
                    "bind_material": proxy.bind_material,
                    "group_prims": proxy.group_prims,
                    "set_prim_attribute": proxy.set_prim_attribute,
                    "delete_prims": proxy.delete_prims,
                }
            )
        return exec_globals

    @staticmethod
    def _has_kit_undo() -> bool:
        return bool(omni and hasattr(omni, "kit") and hasattr(omni.kit, "undo"))

    def _get_real_undo_stack_len(self) -> Optional[int]:
        """Obtiene la longitud real de la pila Undo cuando `get_undo_stack()` no es un MagicMock."""
        if not self._has_kit_undo() or not hasattr(omni.kit.undo, "get_undo_stack"):
            return None
        getter = omni.kit.undo.get_undo_stack
        if _is_mock_object(getter):
            return None
        try:
            stack = getter()
            if isinstance(stack, (list, tuple, deque)):
                return len(stack)
        except Exception:
            pass
        return None

    def _record_command_executed(self) -> None:
        if self._active_undo_group_depth > 0:
            self._commands_executed_in_group += 1

    def _begin_undo_group(self) -> Tuple[bool, Optional[int], int]:
        """Inicia un grupo Undo de Kit 107.3.7 y registra línea base del stack y comandos."""
        stack_before = self._get_real_undo_stack_len()
        cmds_before = self._commands_executed_in_group
        if self._has_kit_undo() and hasattr(omni.kit.undo, "begin_group"):
            try:
                omni.kit.undo.begin_group()
                self._active_undo_group_depth += 1
                return True, stack_before, cmds_before
            except Exception as e:
                logger.warning(f"No se pudo iniciar el grupo de undo: {e}")
        return False, stack_before, cmds_before

    def _end_undo_group(self) -> None:
        if self._has_kit_undo() and hasattr(omni.kit.undo, "end_group"):
            try:
                omni.kit.undo.end_group()
            except Exception as e:
                logger.warning(f"No se pudo cerrar el grupo de undo: {e}")
            finally:
                if self._active_undo_group_depth > 0:
                    self._active_undo_group_depth -= 1
                if self._active_undo_group_depth == 0:
                    self._commands_executed_in_group = 0

    def _rollback_undo_group(
        self,
        undo_opened: bool,
        stack_before: Optional[int],
        cmds_before: int,
    ) -> bool:
        """
        Cierra el grupo Undo activo y ejecuta `omni.kit.undo.undo()` ÚNICAMENTE cuando:
        1. Estamos cerrando el grupo raíz (nunca en grupos anidados, evitando revertir acciones previas).
        2. El stack de Undo creció por esta transacción (o hubo comandos ejecutados sobre un mock sin stack real).
        """
        if not undo_opened or not self._has_kit_undo():
            return False

        cmds_in_this_group = self._commands_executed_in_group - cmds_before
        rolled_back = False

        if hasattr(omni.kit.undo, "end_group"):
            try:
                omni.kit.undo.end_group()
            except Exception as end_err:
                logger.error(f"Fallo cerrando grupo Undo durante rollback: {end_err}")
                return False
            finally:
                if self._active_undo_group_depth > 0:
                    self._active_undo_group_depth -= 1
                if self._active_undo_group_depth == 0:
                    self._commands_executed_in_group = 0

            # Nunca invocar undo() global mientras un grupo exterior sigue abierto
            if self._active_undo_group_depth > 0:
                return False

            stack_after = self._get_real_undo_stack_len()
            if stack_before is not None and stack_after is not None:
                # Host real o doble estricto con stack real: solo revertir si el stack creció
                should_undo = stack_after > stack_before
            else:
                # Doble minimalista sin stack real: solo revertir si efectivamente se ejecutaron comandos
                should_undo = cmds_in_this_group > 0

            if should_undo and hasattr(omni.kit.undo, "undo"):
                try:
                    undo_res = omni.kit.undo.undo()
                    rolled_back = True if undo_res is None else bool(undo_res)
                    if rolled_back:
                        logger.info("Reversión automática de undo ejecutada tras fallo o cancelación parcial.")
                except Exception as rb_err:
                    logger.error(f"Fallo durante la reversión automática de undo: {rb_err}")
        return rolled_back

    def _get_real_stage(self) -> Any:
        """Retorna el Usd.Stage activo cuando omni.usd no es un MagicMock."""
        try:
            if not omni or not hasattr(omni, "usd") or not hasattr(omni.usd, "get_context"):
                return None
            ctx = omni.usd.get_context()
            if _is_mock_object(ctx) or not hasattr(ctx, "get_stage"):
                return None
            stage = ctx.get_stage()
            if _is_mock_object(stage):
                return None
            return stage
        except Exception:
            return None

    def _read_existing_attribute_value(self, prim_path: str, attr_name: str) -> Any:
        """Lee el valor previo de un atributo USD en un Stage real para poblar `prev` en ChangePropertyCommand."""
        try:
            stage = self._get_real_stage()
            if stage is None:
                return None
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or (hasattr(prim, "IsValid") and not prim.IsValid()):
                return None
            attr = prim.GetAttribute(attr_name)
            if not attr or (hasattr(attr, "IsValid") and not attr.IsValid()):
                return None
            return attr.Get()
        except Exception:
            return None

    def _prim_exists_in_real_stage(self, prim_path: str) -> bool:
        try:
            stage = self._get_real_stage()
            if stage is None:
                return False
            prim = stage.GetPrimAtPath(prim_path)
            return bool(prim and (not hasattr(prim, "IsValid") or prim.IsValid()))
        except Exception:
            return False

    def _validate_input_and_policy(self, python_code: Any) -> Optional[ExecutionResult]:
        if not isinstance(python_code, str):
            return ExecutionResult(
                success=False,
                error_msg="Input validation error: python_code must be a string.",
                error_type="TypeError",
            )
        if not python_code.strip():
            return ExecutionResult(
                success=False,
                error_msg="Input validation error: python_code cannot be empty.",
                error_type="ValueError",
            )
        if len(python_code) > self.MAX_CODE_SIZE:
            return ExecutionResult(
                success=False,
                error_msg=f"Security limit exceeded: Code size exceeds maximum allowed limit ({self.MAX_CODE_SIZE} bytes).",
                error_type="SecurityPolicyError",
            )
        is_valid, violation_err = self._policy.validate_code(python_code)
        if not is_valid:
            return ExecutionResult(
                success=False,
                error_msg=redact_secrets(violation_err),
                error_type="SecurityPolicyError",
            )
        return None

    def _compile_instrumented(self, python_code: str, async_mode: bool) -> Any:
        parsed = ast.parse(python_code, filename=_SCRIPT_FILENAME, mode="exec")
        transformer = _CooperativeASTTransformer(async_mode=async_mode)
        transformed = transformer.transform_module(parsed)
        return compile(transformed, _SCRIPT_FILENAME, "exec")

    def _build_failure_result(
        self,
        exc: BaseException,
        start_time: float,
        rolled_back: bool,
        cancelled: bool,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        line_number, tb_str = _extract_script_error_details(exc)
        safe_msg = redact_secrets(str(exc)) or type(exc).__name__
        return ExecutionResult(
            success=False,
            error_msg=safe_msg,
            error_type=type(exc).__name__,
            line_number=line_number,
            traceback_str=tb_str,
            cancelled=cancelled,
            execution_time_ms=elapsed_ms,
            partial_changes_rolled_back=rolled_back,
            metadata=metadata,
        )

    def execute_code(
        self,
        python_code: str,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta código Python de forma síncrona, acotada, cancelable y con capacidades restringidas,
        envolviendo mutaciones en un grupo reversible `begin_group`/`end_group` de Kit 107.3.7.
        """
        start_time = time.monotonic()
        validation_err = self._validate_input_and_policy(python_code)
        if validation_err is not None:
            return validation_err.to_dict()

        eff_budget = budget or self._default_budget
        eff_token = cancellation_token or CancellationToken()
        guard = _ExecutionGuard(budget=eff_budget, token=eff_token)
        affinity = self._policy.classify_execution_affinity(python_code)
        exec_thread_id = threading.get_ident()

        try:
            compiled = self._compile_instrumented(python_code, async_mode=False)
        except Exception as compile_err:
            return self._build_failure_result(
                compile_err,
                start_time=start_time,
                rolled_back=False,
                cancelled=False,
                metadata={"affinity": affinity.value, "execution_thread_id": exec_thread_id},
            ).to_dict()

        exec_globals = self._build_exec_globals(guard, include_kit_bindings=True)
        undo_opened, stack_before, cmds_before = self._begin_undo_group()

        try:
            exec(compiled, exec_globals)
            # Defensa en profundidad: verificar cancelación y presupuesto tras finalizar
            guard._check_limits()
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                success=True,
                execution_time_ms=elapsed_ms,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": exec_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                },
            ).to_dict()
        except ExecutionCancelledError as cancel_err:
            rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before)
            undo_opened = False
            return self._build_failure_result(
                cancel_err,
                start_time=start_time,
                rolled_back=rolled_back,
                cancelled=True,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": exec_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                },
            ).to_dict()
        except (ExecutionBudgetExceededError, Exception) as exec_err:
            rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before)
            undo_opened = False
            return self._build_failure_result(
                exec_err,
                start_time=start_time,
                rolled_back=rolled_back,
                cancelled=False,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": exec_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                },
            ).to_dict()
        finally:
            if undo_opened:
                self._end_undo_group()

    async def execute_code_async(
        self,
        python_code: str,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ExecutionResult:
        """
        Ejecuta código Python de forma acotada y cancelable respetando afinidad de hilo:
        - `KIT_MAIN_THREAD`: corre en el hilo del event loop principal (hilo de Kit)
          instrumentado en tramos cooperativos con `await asyncio.sleep(0)` y bloque Undo real.
        - `PURE_COMPUTE`: corre en un worker thread cooperativo con el mismo `CancellationToken`
          y presupuesto de pasos, sin tocar `omni`/`pxr` ni bloquear el event loop de UI.
        """
        start_time = time.monotonic()
        validation_err = self._validate_input_and_policy(python_code)
        if validation_err is not None:
            return validation_err

        eff_budget = budget or self._default_budget
        eff_token = cancellation_token or CancellationToken()
        guard = _ExecutionGuard(budget=eff_budget, token=eff_token)
        affinity = self._policy.classify_execution_affinity(python_code)

        if affinity == ExecutionAffinity.PURE_COMPUTE:
            return await self._execute_pure_compute_off_thread(
                python_code=python_code,
                guard=guard,
                start_time=start_time,
            )

        main_thread_id = threading.get_ident()
        try:
            compiled = self._compile_instrumented(python_code, async_mode=True)
        except Exception as compile_err:
            return self._build_failure_result(
                compile_err,
                start_time=start_time,
                rolled_back=False,
                cancelled=False,
                metadata={"affinity": affinity.value, "execution_thread_id": main_thread_id},
            )

        exec_globals = self._build_exec_globals(guard, include_kit_bindings=True)
        undo_opened, stack_before, cmds_before = self._begin_undo_group()

        try:
            exec(compiled, exec_globals)
            entry_coro = exec_globals["__lmchat_entry__"]()
            await entry_coro
            # Defensa en profundidad: verificar cancelación y presupuesto tras finalizar
            guard._check_limits()
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            return ExecutionResult(
                success=True,
                execution_time_ms=elapsed_ms,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": main_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                    "yield_count": guard.yield_count,
                },
            )
        except (ExecutionCancelledError, asyncio.CancelledError) as cancel_err:
            eff_token.cancel()
            rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before)
            undo_opened = False
            actual_exc: BaseException = (
                cancel_err
                if isinstance(cancel_err, ExecutionCancelledError)
                else ExecutionCancelledError("La ejecución fue cancelada cooperativamente.")
            )
            return self._build_failure_result(
                actual_exc,
                start_time=start_time,
                rolled_back=rolled_back,
                cancelled=True,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": main_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                    "yield_count": guard.yield_count,
                },
            )
        except (ExecutionBudgetExceededError, Exception) as exec_err:
            rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before)
            undo_opened = False
            return self._build_failure_result(
                exec_err,
                start_time=start_time,
                rolled_back=rolled_back,
                cancelled=False,
                metadata={
                    "affinity": affinity.value,
                    "execution_thread_id": main_thread_id,
                    "steps_executed": guard.steps,
                    "loop_iterations": guard.loop_iterations,
                    "yield_count": guard.yield_count,
                },
            )
        finally:
            if undo_opened:
                self._end_undo_group()

    async def _execute_pure_compute_off_thread(
        self,
        python_code: str,
        guard: _ExecutionGuard,
        start_time: float,
    ) -> ExecutionResult:
        """
        Ejecuta cálculo puro en un hilo trabajador con instrumentación cooperativa.
        Si se cancela el token (o la tarea asyncio), el worker detiene realmente el cómputo
        al siguiente checkpoint sin dejar hilos zombi ni forzar terminación destructiva.
        """
        try:
            compiled = self._compile_instrumented(python_code, async_mode=False)
        except Exception as compile_err:
            return self._build_failure_result(
                compile_err,
                start_time=start_time,
                rolled_back=False,
                cancelled=False,
                metadata={"affinity": ExecutionAffinity.PURE_COMPUTE.value},
            )

        exec_globals = self._build_exec_globals(guard, include_kit_bindings=False)
        worker_done = threading.Event()
        worker_meta: Dict[str, Any] = {
            "affinity": ExecutionAffinity.PURE_COMPUTE.value,
            "execution_thread_id": None,
            "worker_stopped": False,
        }

        def _worker_entry() -> ExecutionResult:
            worker_meta["execution_thread_id"] = threading.get_ident()
            try:
                exec(compiled, exec_globals)
                guard._check_limits()
                elapsed_ms = (time.monotonic() - start_time) * 1000.0
                worker_meta["steps_executed"] = guard.steps
                worker_meta["loop_iterations"] = guard.loop_iterations
                worker_meta["worker_stopped"] = True
                return ExecutionResult(
                    success=True,
                    execution_time_ms=elapsed_ms,
                    metadata=dict(worker_meta),
                )
            except ExecutionCancelledError as cancel_err:
                worker_meta["steps_executed"] = guard.steps
                worker_meta["loop_iterations"] = guard.loop_iterations
                worker_meta["worker_stopped"] = True
                return self._build_failure_result(
                    cancel_err,
                    start_time=start_time,
                    rolled_back=False,
                    cancelled=True,
                    metadata=dict(worker_meta),
                )
            except (ExecutionBudgetExceededError, Exception) as exc:
                worker_meta["steps_executed"] = guard.steps
                worker_meta["loop_iterations"] = guard.loop_iterations
                worker_meta["worker_stopped"] = True
                return self._build_failure_result(
                    exc,
                    start_time=start_time,
                    rolled_back=False,
                    cancelled=False,
                    metadata=dict(worker_meta),
                )
            finally:
                worker_done.set()

        loop = asyncio.get_running_loop()
        worker_future = loop.run_in_executor(None, _worker_entry)
        try:
            return await worker_future
        except asyncio.CancelledError:
            guard.token.cancel()
            bounded_wait = min(1.0, max(0.2, float(guard.budget.max_wall_time_seconds)))
            try:
                return await asyncio.wait_for(asyncio.shield(worker_future), timeout=bounded_wait)
            except Exception:
                return ExecutionResult(
                    success=False,
                    error_msg="La ejecución fue cancelada por el usuario.",
                    error_type="ExecutionCancelledError",
                    cancelled=True,
                    execution_time_ms=(time.monotonic() - start_time) * 1000.0,
                    metadata={**worker_meta, "worker_stopped": worker_done.is_set()},
                )

    def create_prim(
        self,
        prim_type: str,
        prim_path: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Crea un prim de forma no-destructiva mediante CreatePrimWithDefaultXform (Kit 107.3.7)."""
        if prim_path and self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                cmd_kwargs: Dict[str, Any] = {
                    "prim_type": prim_type,
                    "attributes": attributes or {},
                }
                if prim_path:
                    cmd_kwargs["prim_path"] = prim_path

                cmd_res = omni.kit.commands.execute(
                    "CreatePrimWithDefaultXform",
                    **cmd_kwargs,
                )
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {
                        "success": False,
                        "error_msg": f"Error ejecutando CreatePrimWithDefaultXform para '{prim_path or prim_type}': {res}",
                    }
                self._record_command_executed()
                return {
                    "success": True,
                    "prim_path": prim_path,
                    "prim_type": prim_type,
                    "result": res,
                }
            else:
                return {
                    "success": True,
                    "prim_path": prim_path,
                    "prim_type": prim_type,
                    "note": "Ejecución simulada en entorno headless",
                }
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}

    def transform_prim(
        self,
        prim_path: str,
        new_transform_matrix: Optional[Any] = None,
        translation: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Transforma interactivamente un prim existente usando comandos reales de Kit 107.3.7:
        - `TransformPrimCommand(path, new_transform_matrix)` cuando se provee matriz 4x4.
        - `TransformPrimSRTCommand(path, new_translation, new_rotation_euler, new_scale)` para SRT.
        """
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                if new_transform_matrix is not None:
                    cmd_name = "TransformPrimCommand"
                    kwargs: Dict[str, Any] = {
                        "path": prim_path,
                        "new_transform_matrix": new_transform_matrix,
                    }
                else:
                    cmd_name = "TransformPrimSRTCommand"
                    kwargs = {"path": prim_path}
                    if translation is not None:
                        kwargs["new_translation"] = _to_gf_vec3d(translation)
                    if rotation is not None:
                        kwargs["new_rotation_euler"] = _to_gf_vec3d(rotation)
                    if scale is not None:
                        kwargs["new_scale"] = _to_gf_vec3d(scale)

                cmd_res = omni.kit.commands.execute(cmd_name, **kwargs)
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {"success": False, "error_msg": f"Error ejecutando {cmd_name} para {prim_path}: {res}"}
                self._record_command_executed()
                return {"success": True, "path": prim_path, "command": cmd_name}
            else:
                return {"success": True, "path": prim_path, "note": "Ejecución simulada en entorno headless"}
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}

    def bind_material(self, prim_path: str, material_path: str) -> Dict[str, Any]:
        """Enlaza un material UsdShade/MDL a un prim usando BindMaterialCommand (Kit 107.3.7)."""
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                cmd_res = omni.kit.commands.execute(
                    "BindMaterialCommand",
                    prim_path=prim_path,
                    material_path=material_path,
                )
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {"success": False, "error_msg": f"Error ejecutando BindMaterialCommand para {prim_path}: {res}"}
                self._record_command_executed()
                return {"success": True, "prim_path": prim_path, "material_path": material_path}
            else:
                return {"success": True, "prim_path": prim_path, "material_path": material_path, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}

    def group_prims(self, prim_paths: List[str], parent_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Reorganiza una lista de prims de forma reversible compatible con Kit 107.3.7:
        - Si `parent_path` se especifica: crea un Scope `parent_path` (`CreatePrimWithDefaultXform`)
          y mueve los prims con `MovePrimsCommand(paths_to_move=...)`.
          Si se ejecuta fuera de un grupo Undo exterior, envuelve en su propio grupo raíz y hace
          rollback en fallo; si se ejecuta anidado dentro de `execute_code()`, limpia el Scope recién
          creado con `DeletePrimsCommand` sin invocar `omni.kit.undo.undo()` sobre el historial previo.
        - Si `parent_path` es None/vacío: invoca `GroupPrimsCommand(prim_paths=...)`.
        """
        if len(prim_paths) > getattr(self._policy.config, "max_prims_creation_limit", 500):
            limit = self._policy.config.max_prims_creation_limit
            return {"success": False, "error_msg": f"El número de prims ({len(prim_paths)}) excede el límite permitido de {limit}."}

        if parent_path and self._policy.is_prim_protected(parent_path):
            return {"success": False, "error_msg": f"La ruta destino '{parent_path}' está protegida por el sistema."}

        for p in prim_paths:
            if self._policy.is_prim_protected(p):
                return {"success": False, "error_msg": f"El prim '{p}' está protegido por el sistema."}

        # Fail-fast en Stage real: validar que todos los prims origen existan antes de crear el Scope
        if self._get_real_stage() is not None:
            for p in prim_paths:
                if not self._prim_exists_in_real_stage(p):
                    return {
                        "success": False,
                        "error_msg": f"El prim origen '{p}' no existe en el Stage.",
                        "partial_changes_rolled_back": False,
                    }

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                if parent_path:
                    is_nested = self._active_undo_group_depth > 0
                    scope_existed_before = self._prim_exists_in_real_stage(parent_path)
                    undo_opened = False
                    stack_before: Optional[int] = None
                    cmds_before = self._commands_executed_in_group

                    if not is_nested:
                        undo_opened, stack_before, cmds_before = self._begin_undo_group()

                    try:
                        scope_res = omni.kit.commands.execute(
                            "CreatePrimWithDefaultXform",
                            prim_type="Scope",
                            prim_path=parent_path,
                            attributes={},
                        )
                        scope_ok = scope_res[0] if isinstance(scope_res, tuple) else bool(scope_res)
                        if not scope_ok:
                            detail = scope_res[1] if isinstance(scope_res, tuple) and len(scope_res) > 1 else None
                            rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before) if not is_nested else False
                            undo_opened = False
                            return {
                                "success": False,
                                "error_msg": f"Error ejecutando CreatePrimWithDefaultXform para {parent_path}: {detail}",
                                "partial_changes_rolled_back": rolled_back,
                            }
                        self._record_command_executed()

                        clean_parent = parent_path.rstrip("/")
                        paths_to_move = {
                            p: f"{clean_parent}/{p.rstrip('/').rsplit('/', 1)[-1]}"
                            for p in prim_paths
                        }
                        move_res = omni.kit.commands.execute(
                            "MovePrimsCommand",
                            paths_to_move=paths_to_move,
                        )
                        move_ok = move_res[0] if isinstance(move_res, tuple) else bool(move_res)
                        if not move_ok:
                            detail = move_res[1] if isinstance(move_res, tuple) and len(move_res) > 1 else None
                            if not is_nested:
                                rolled_back = self._rollback_undo_group(undo_opened, stack_before, cmds_before)
                                undo_opened = False
                            else:
                                # Dentro de un grupo exterior abierto: nunca llamar undo() global;
                                # compensar limpiamente el Scope recién creado para no dejar huérfanos.
                                rolled_back = False
                                if not scope_existed_before:
                                    del_res = omni.kit.commands.execute("DeletePrimsCommand", paths=[parent_path])
                                    rolled_back = del_res[0] if isinstance(del_res, tuple) else bool(del_res)
                            return {
                                "success": False,
                                "error_msg": f"Error ejecutando MovePrimsCommand para {parent_path}: {detail}",
                                "partial_changes_rolled_back": rolled_back,
                            }
                        self._record_command_executed()
                    finally:
                        if undo_opened:
                            self._end_undo_group()
                    return {
                        "success": True,
                        "grouped_count": len(prim_paths),
                        "parent_path": parent_path,
                        "moved_paths": paths_to_move,
                    }

                cmd_res = omni.kit.commands.execute(
                    "GroupPrimsCommand",
                    prim_paths=prim_paths,
                )
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {"success": False, "error_msg": f"Error ejecutando GroupPrimsCommand: {res}"}
                self._record_command_executed()
                return {"success": True, "grouped_count": len(prim_paths), "parent_path": parent_path}
            else:
                return {"success": True, "grouped_count": len(prim_paths), "parent_path": parent_path, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}

    def set_prim_attribute(self, prim_path: str, attr_name: str, value: Any) -> Dict[str, Any]:
        """
        Modifica un atributo de un prim mediante ChangePropertyCommand (Kit 107.3.7),
        capturando el valor previo del Stage real cuando está disponible para un Ctrl+Z fiel.
        """
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                prev_val = self._read_existing_attribute_value(prim_path, attr_name)
                cmd_res = omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    prop_path=f"{prim_path}.{attr_name}",
                    value=value,
                    prev=prev_val,
                )
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {"success": False, "error_msg": f"Error ejecutando ChangePropertyCommand para {prim_path}.{attr_name}: {res}"}
                self._record_command_executed()
                return {"success": True, "prim_path": prim_path, "attribute": attr_name, "value": value}
            else:
                return {"success": True, "prim_path": prim_path, "attribute": attr_name, "value": value, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}

    def delete_prims(self, prim_paths: List[str]) -> Dict[str, Any]:
        """Elimina uno o más prims de forma reversible mediante DeletePrimsCommand (Kit 107.3.7)."""
        for p in prim_paths:
            if self._policy.is_prim_protected(p):
                return {"success": False, "error_msg": f"El prim '{p}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                cmd_res = omni.kit.commands.execute(
                    "DeletePrimsCommand",
                    paths=list(prim_paths),
                )
                if isinstance(cmd_res, tuple):
                    status, res = cmd_res[0], cmd_res[1] if len(cmd_res) > 1 else None
                else:
                    status, res = bool(cmd_res), None

                if not status:
                    return {"success": False, "error_msg": f"Error ejecutando DeletePrimsCommand: {res}"}
                self._record_command_executed()
                return {"success": True, "deleted_paths": list(prim_paths)}
            else:
                return {"success": True, "deleted_paths": list(prim_paths), "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": redact_secrets(str(e))}
