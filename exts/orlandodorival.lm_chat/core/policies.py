# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Políticas de Gobernanza, Capacidades y Seguridad Espacial para Agentes de LM-Chat™.

Frontera de capacidades (modelo de confianza explícito — F06):
- Este módulo implementa guardrails en proceso (análisis AST, lista blanca de imports con
  módulos stdlib sanitizados y diccionario restringido SAFE_BUILTINS con iteradores acotados)
  para acotar código Python generado por IA dentro del proceso de NVIDIA Omniverse Kit.
- Limitación de seguridad explícita: una lista de nombres/AST en CPython en proceso NO
  constituye un sandbox hermético frente a código adversarial arbitrario ni reemplaza
  el aislamiento de sistema operativo (contenedores, sandboxing OS o subprocesos sin
  privilegios). Su objetivo es prevenir errores destructivos, evasiones comunes
  (ej. builtins.eval, re-exportaciones stdlib, mutación de políticas), bloqueos del hilo
  de Kit y escrituras USD que omitan el historial de Undo.
"""

import ast
import builtins as _py_builtins
import re
import types
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Iterator, Optional, Set, Tuple

from core.interfaces import (
    ExecutionAffinity,
    ExecutionBudgetExceededError,
    IAgentPolicy,
)

# Patrones conservadores para redactar secretos en texto plano, JSON y reprs de diccionarios Python.
_SECRET_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "sk-***"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_-]{8,}\b"), "nvapi-***"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{16,}\b"), "AIza***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{12,}\b"), "gh*_***"),
    (re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._\-+/=]{8,}"), r"\1***"),
    (
        re.compile(
            r"(?i)(['\"]?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|"
            r"secret|password|passwd|authorization|token)\b['\"]?)"
            r"(\s*[:=]\s*['\"]?)([^\s'\",;}\]]{4,})(['\"]?)"
        ),
        r"\1\2***\4",
    ),
)

_KIT_AFFINITY_SYMBOLS: frozenset = frozenset(
    {
        "omni",
        "pxr",
        "Usd",
        "UsdGeom",
        "UsdShade",
        "UsdLux",
        "UsdPhysics",
        "Sdf",
        "Gf",
        "controller",
        "inspector",
        "create_prim",
        "transform_prim",
        "bind_material",
        "group_prims",
        "set_prim_attribute",
        "delete_prims",
        "stage",
    }
)

_OS_LIKE_MODULES: frozenset = frozenset({"os", "posix", "nt", "shutil", "pathlib"})

_DIRECT_USD_PROP_PRODUCERS: frozenset = frozenset(
    {
        "GetAttribute",
        "CreateAttribute",
        "GetProperty",
        "AddTranslateOp",
        "AddRotateXYZOp",
        "AddRotateXOp",
        "AddRotateYOp",
        "AddRotateZOp",
        "AddScaleOp",
        "AddTransformOp",
        "AddOrientOp",
        "CreatePointsAttr",
        "CreateNormalsAttr",
        "CreateSizeAttr",
        "CreateRadiusAttr",
        "CreateIntensityAttr",
    }
)


def redact_secrets(text: Optional[str]) -> Optional[str]:
    """Redacta patrones de claves API, tokens y credenciales en mensajes de error o tracebacks."""
    if text is None or not isinstance(text, str):
        return text
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


_BLOCKED_MODULE_EXPORTS: Dict[str, Set[str]] = {
    "string": {"Formatter"},
}


class _SanitizedModuleProxy:
    """
    Fachada de solo lectura para módulos stdlib permitidos que oculta submódulos prohibidos
    o no incluidos en la lista blanca y envuelve recursivamente submódulos stdlib permitidos
    (cerrando escapes transitivos como `json.codecs`, `typing.contextlib`, `statistics.random`).
    """

    __slots__ = ("_mod_name", "_exports")

    def __init__(
        self,
        module: types.ModuleType,
        forbidden_roots: Set[str],
        allowed_roots: Set[str],
        _seen: Optional[Dict[int, "_SanitizedModuleProxy"]] = None,
    ) -> None:
        seen = _seen if _seen is not None else {}
        seen[id(module)] = self
        mod_root = (module.__name__ or "").split(".")[0].lower()
        blocked_for_mod = _BLOCKED_MODULE_EXPORTS.get(mod_root, set())

        exports: Dict[str, Any] = {}
        for attr_name in dir(module):
            if attr_name.startswith("_") or attr_name in blocked_for_mod:
                continue
            try:
                val = _py_builtins.getattr(module, attr_name)
            except Exception:
                continue
            if isinstance(val, types.ModuleType):
                val_root = (val.__name__ or "").split(".")[0].lower()
                if (
                    val_root in forbidden_roots
                    or attr_name.lower() in forbidden_roots
                    or val_root not in allowed_roots
                    or val_root in ("omni", "pxr")
                ):
                    continue
                if id(val) in seen:
                    exports[attr_name] = seen[id(val)]
                else:
                    exports[attr_name] = _SanitizedModuleProxy(
                        val, forbidden_roots, allowed_roots, _seen=seen
                    )
            else:
                exports[attr_name] = val
        object.__setattr__(self, "_mod_name", module.__name__)
        object.__setattr__(self, "_exports", exports)

    def __getattr__(self, name: str) -> Any:
        exports = object.__getattribute__(self, "_exports")
        if name in exports:
            return exports[name]
        mod_name = object.__getattribute__(self, "_mod_name")
        raise AttributeError(
            f"Security Policy Violation: Attribute '{name}' is not exposed on module '{mod_name}'."
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Security Policy Violation: Sanitized module proxy is read-only.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Security Policy Violation: Sanitized module proxy is read-only.")

    def __dir__(self):
        return sorted(object.__getattribute__(self, "_exports").keys())


@dataclass(frozen=True)
class AgentPolicyConfig:
    """Configuración inmutable de directivas, capacidades y límites de seguridad para el agente."""

    max_prims_creation_limit: int = 500
    max_code_size: int = 100_000
    max_loop_iterations: int = 10_000
    forbid_direct_usd_writes: bool = True
    enforce_import_allowlist: bool = True
    protected_paths: Tuple[str, ...] = (
        "/OmniverseKit_Root",
        "/Render",
        "/World/System",
        "/Library",
    )
    allowed_import_modules: Tuple[str, ...] = (
        "omni",
        "pxr",
        "math",
        "cmath",
        "random",
        "statistics",
        "functools",
        "collections",
        "dataclasses",
        "enum",
        "json",
        "re",
        "string",
        "typing",
        "decimal",
        "fractions",
        "uuid",
        "datetime",
        "copy",
        "colorsys",
    )
    forbidden_modules: Tuple[str, ...] = (
        "builtins",
        "__builtin__",
        "sys",
        "os",
        "importlib",
        "inspect",
        "shutil",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "ftplib",
        "telnetlib",
        "smtplib",
        "webbrowser",
        "winreg",
        "ctypes",
        "posix",
        "nt",
        "pathlib",
        "io",
        "pickle",
        "marshal",
        "gc",
        "code",
        "codeop",
        "pty",
        "signal",
        "threading",
        "multiprocessing",
        "concurrent",
        "time",
        "asyncio",
        "itertools",
        "types",
    )
    forbidden_builtins: Tuple[str, ...] = (
        "eval",
        "compile",
        "exec",
        "open",
        "__import__",
        "breakpoint",
        "input",
        "globals",
        "locals",
        "vars",
        "memoryview",
        "delattr",
        "setattr",
    )
    forbidden_dunder_attributes: Tuple[str, ...] = (
        "__builtins__",
        "__subclasses__",
        "__globals__",
        "__code__",
        "__closure__",
        "__bases__",
        "__base__",
        "__mro__",
        "__class__",
        "__dict__",
        "__import__",
        "__loader__",
        "__spec__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "__self__",
        "__func__",
        "__init_subclass__",
    )
    # Atributos de introspección o re-exportación de módulos sensibles bloqueados en cualquier receptor.
    forbidden_capability_attributes: Tuple[str, ...] = (
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "mro",
        "Formatter",
        "get_field",
        "get_value",
        "vformat",
        "sys",
        "_sys",
        "os",
        "_os",
        "builtins",
        "importlib",
        "subprocess",
        "shutil",
        "ctypes",
        "posix",
        "nt",
        "modules",
        "environ",
        "getenv",
        "putenv",
    )
    # Métodos intrínsecamente de SO/ejecución sin homónimos benignos en str/list/dict.
    forbidden_os_attributes: Tuple[str, ...] = (
        "system",
        "popen",
        "spawn",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "rmdir",
        "unlink",
        "kill",
        "fork",
        "execv",
        "execl",
        "execve",
        "execvp",
    )
    # Métodos peligrosos SOLO cuando el receptor proviene de módulos de SO/archivos
    # (evita falsos positivos en str.replace(), list.remove(), etc.).
    os_scoped_attributes: Tuple[str, ...] = (
        "remove",
        "rename",
        "replace",
        "truncate",
        "chmod",
        "chown",
        "link",
        "symlink",
        "mkdir",
        "makedirs",
        "removedirs",
        "listdir",
        "walk",
        "scandir",
        "getenv",
        "putenv",
    )
    direct_usd_write_methods: Tuple[str, ...] = (
        "DefinePrim",
        "CreatePrim",
        "OverridePrim",
        "RemovePrim",
        "CreateClassPrim",
        "CreatePrimInLayer",
        "CopySpec",
    )
    direct_usd_schema_prefixes: Tuple[str, ...] = (
        "UsdGeom",
        "UsdLux",
        "UsdShade",
        "UsdPhysics",
        "UsdSkel",
        "UsdMedia",
        "UsdVol",
    )


class SpatialSecurityPolicy(IAgentPolicy):
    """
    Guardián y validador de políticas de seguridad espacial, capacidades y ejecución acotada.
    Combina análisis estático AST (con rastreo de alias y propagación de constantes enteras)
    y provisión de `SAFE_BUILTINS` acotados para el entorno de ejecución.
    """

    def __init__(self, config: Optional[AgentPolicyConfig] = None) -> None:
        """Inicializa la política con la configuración especificada o por defecto."""
        self.config = config or AgentPolicyConfig()

    def is_prim_protected(self, prim_path: str) -> bool:
        """Determina si una ruta en el Stage corresponde a un elemento protegido del sistema."""
        if not prim_path:
            return False
        clean_path = prim_path.strip()
        for protected in self.config.protected_paths:
            if clean_path == protected or clean_path.startswith(f"{protected}/"):
                return True
        return False

    def classify_execution_affinity(self, python_code: str) -> ExecutionAffinity:
        """
        Clasifica si el código requiere afinidad con el hilo principal de Kit/USD
        o si es cálculo puro Python elegible para ejecución acotada fuera del hilo principal.

        Ante sintaxis inválida o ambigüedad retorna conservadoramente KIT_MAIN_THREAD.
        """
        if not isinstance(python_code, str) or not python_code.strip():
            return ExecutionAffinity.KIT_MAIN_THREAD

        try:
            tree = ast.parse(python_code)
        except SyntaxError:
            return ExecutionAffinity.KIT_MAIN_THREAD

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in ("omni", "pxr"):
                        return ExecutionAffinity.KIT_MAIN_THREAD
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in ("omni", "pxr"):
                    return ExecutionAffinity.KIT_MAIN_THREAD
            elif isinstance(node, ast.Name) and node.id in _KIT_AFFINITY_SYMBOLS:
                return ExecutionAffinity.KIT_MAIN_THREAD

        return ExecutionAffinity.PURE_COMPUTE

    def get_safe_builtins(
        self,
        safe_range: Optional[Callable[..., Any]] = None,
        iter_wrapper: Optional[Callable[[Iterable[Any]], Iterator[Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Retorna un diccionario fresco y restringido de builtins seguros para ejecución en proceso.

        - Omite `eval`, `exec`, `compile`, `open`, `breakpoint`, `input`, `globals`, `locals`,
          `vars`, `memoryview`, `setattr`, `delattr` y `BaseException`.
        - Media `__import__` con lista blanca y proxys sanitizados para módulos stdlib.
        - Envuelve consumidores de iterables en C (`sum`, `any`, `all`, `list`, `tuple`, `set`,
          `frozenset`, `sorted`, `min`, `max`, `enumerate`, `zip`, `map`, `filter`) con un
          iterador acotado/cancelable.
        """
        allowed_roots = set(self.config.allowed_import_modules)
        forbidden_roots = set(self.config.forbidden_modules)
        enforce_allowlist = self.config.enforce_import_allowlist
        forbidden_dunders = set(self.config.forbidden_dunder_attributes)
        forbidden_names = set(self.config.forbidden_builtins) | set(self.config.forbidden_capability_attributes)
        max_iters = self.config.max_loop_iterations

        def _default_iter_wrapper(iterable: Iterable[Any]) -> Iterator[Any]:
            count = 0
            for item in iterable:
                count += 1
                if count > max_iters:
                    raise ExecutionBudgetExceededError(
                        f"Execution budget exceeded: iterable consumption ({count}) "
                        f"exceeds maximum allowed iterations ({max_iters})."
                    )
                yield item

        wrap_it = iter_wrapper or _default_iter_wrapper

        def _restricted_import(
            name: str,
            globals_: Any = None,
            locals_: Any = None,
            fromlist: Tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if level != 0:
                raise ImportError("Security Policy Violation: Relative imports are prohibited.")
            root_pkg = (name or "").split(".")[0].lower()
            if root_pkg in forbidden_roots:
                raise ImportError(
                    f"Security Policy Violation: Import of forbidden module '{name}' is prohibited."
                )
            if enforce_allowlist and root_pkg not in allowed_roots:
                raise ImportError(
                    f"Security Policy Violation: Import of non-allowlisted module '{name}' is prohibited."
                )
            mod = _py_builtins.__import__(name, globals_, locals_, fromlist, level)
            # Módulos nativos de Omniverse/OpenUSD requieren el objeto módulo real para submódulos
            if root_pkg in ("omni", "pxr"):
                return mod
            if isinstance(mod, types.ModuleType):
                return _SanitizedModuleProxy(mod, forbidden_roots, allowed_roots)
            return mod

        def _safe_type(obj: Any) -> Any:
            # Permite inspección type(obj) pero bloquea creación dinámica de clases type(name, bases, dict)
            return _py_builtins.type(obj)

        def _safe_getattr(obj: Any, name: str, *default: Any) -> Any:
            if (
                not isinstance(name, str)
                or name.startswith("_")
                or name in forbidden_dunders
                or name in forbidden_names
            ):
                raise AttributeError(
                    f"Security Policy Violation: Access to attribute '{name}' via getattr() is blocked."
                )
            return _py_builtins.getattr(obj, name, *default)

        def _safe_hasattr(obj: Any, name: str) -> bool:
            if (
                not isinstance(name, str)
                or name.startswith("_")
                or name in forbidden_dunders
                or name in forbidden_names
            ):
                return False
            return _py_builtins.hasattr(obj, name)

        def _safe_pow(base: Any, exp: Any, mod: Any = None) -> Any:
            if mod is None and isinstance(exp, int) and exp > 10_000 and isinstance(base, (int, float)) and abs(base) > 1:
                raise ExecutionBudgetExceededError(
                    f"Security Policy Violation: Exponentiation power ({exp}) exceeds safe compute bound."
                )
            return _py_builtins.pow(base, exp) if mod is None else _py_builtins.pow(base, exp, mod)

        def _default_bounded_range(*args: Any) -> range:
            r = _py_builtins.range(*args)
            if len(r) > max_iters:
                raise ExecutionBudgetExceededError(
                    f"Execution budget exceeded: range length ({len(r)}) exceeds maximum allowed iterations ({max_iters})."
                )
            return r

        def _safe_sum(iterable: Iterable[Any], *args: Any, **kwargs: Any) -> Any:
            return _py_builtins.sum(wrap_it(iterable), *args, **kwargs)

        def _safe_any(iterable: Iterable[Any]) -> bool:
            return _py_builtins.any(wrap_it(iterable))

        def _safe_all(iterable: Iterable[Any]) -> bool:
            return _py_builtins.all(wrap_it(iterable))

        def _safe_sorted(iterable: Iterable[Any], *args: Any, **kwargs: Any) -> list:
            return _py_builtins.sorted(wrap_it(iterable), *args, **kwargs)

        def _safe_min(*args: Any, **kwargs: Any) -> Any:
            if len(args) == 1:
                return _py_builtins.min(wrap_it(args[0]), **kwargs)
            return _py_builtins.min(*args, **kwargs)

        def _safe_max(*args: Any, **kwargs: Any) -> Any:
            if len(args) == 1:
                return _py_builtins.max(wrap_it(args[0]), **kwargs)
            return _py_builtins.max(*args, **kwargs)

        def _safe_enumerate(iterable: Iterable[Any], start: int = 0) -> Iterator[Tuple[int, Any]]:
            return _py_builtins.enumerate(wrap_it(iterable), start=start)

        def _safe_zip(*iterables: Iterable[Any], **kwargs: Any) -> Iterator[Any]:
            return _py_builtins.zip(*(wrap_it(it) for it in iterables), **kwargs)

        def _safe_map(func: Callable[..., Any], *iterables: Iterable[Any]) -> Iterator[Any]:
            return _py_builtins.map(func, *(wrap_it(it) for it in iterables))

        def _safe_filter(func: Optional[Callable[..., Any]], iterable: Iterable[Any]) -> Iterator[Any]:
            return _py_builtins.filter(func, wrap_it(iterable))

        def _safe_iter(*args: Any) -> Iterator[Any]:
            return wrap_it(_py_builtins.iter(*args))

        safe_dict: Dict[str, Any] = {
            # Constantes
            "True": True,
            "False": False,
            "None": None,
            "Ellipsis": Ellipsis,
            "NotImplemented": NotImplemented,
            # Tipos nativos (preservan isinstance, type(), anotaciones PEP 585 y herencia;
            # sus llamadas constructoras de 1 arg son acotadas en _CooperativeASTTransformer).
            "bool": bool,
            "int": int,
            "float": float,
            "complex": complex,
            "str": str,
            "bytes": bytes,
            "bytearray": bytearray,
            "list": list,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "dict": dict,
            "slice": slice,
            "object": object,
            "property": property,
            "staticmethod": staticmethod,
            "classmethod": classmethod,
            "super": super,
            "type": _safe_type,
            # Utilidades e iteración acotada
            "range": safe_range or _default_bounded_range,
            "len": len,
            "iter": _safe_iter,
            "next": next,
            "enumerate": _safe_enumerate,
            "zip": _safe_zip,
            "map": _safe_map,
            "filter": _safe_filter,
            "reversed": reversed,
            "sorted": _safe_sorted,
            "any": _safe_any,
            "all": _safe_all,
            "sum": _safe_sum,
            "min": _safe_min,
            "max": _safe_max,
            "abs": abs,
            "round": round,
            "pow": _safe_pow,
            "divmod": divmod,
            "hash": hash,
            "hex": hex,
            "oct": oct,
            "bin": bin,
            "ord": ord,
            "chr": chr,
            "repr": repr,
            "ascii": ascii,
            "format": format,
            "callable": callable,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "id": id,
            "print": print,
            "getattr": _safe_getattr,
            "hasattr": _safe_hasattr,
            "__import__": _restricted_import,
            "__build_class__": _py_builtins.__build_class__,
            # Excepciones estándar (BaseException omitida para impedir supresión de cancelación/presupuesto)
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "RuntimeError": RuntimeError,
            "ZeroDivisionError": ZeroDivisionError,
            "StopIteration": StopIteration,
            "AssertionError": AssertionError,
            "NotImplementedError": NotImplementedError,
            "LookupError": LookupError,
            "ArithmeticError": ArithmeticError,
            "NameError": NameError,
            "OverflowError": OverflowError,
            "ImportError": ImportError,
        }
        return safe_dict

    def _eval_constant_int(self, node: ast.AST, env: Dict[str, int]) -> Optional[int]:
        """Evalúa expresiones enteras constantes simples con protección contra desbordamiento."""
        sentinel_overflow = self.config.max_loop_iterations + 1
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_constant_int(node.operand, env)
            if operand is None:
                return None
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.USub):
                return -operand
        if isinstance(node, ast.BinOp):
            left = self._eval_constant_int(node.left, env)
            right = self._eval_constant_int(node.right, env)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.FloorDiv) and right != 0:
                return left // right
            if isinstance(node.op, ast.Pow):
                if right < 0:
                    return 0
                if right > 18 and abs(left) > 1:
                    return sentinel_overflow
                return int(left ** right)
        return None

    def _compute_range_iterations(self, call_node: ast.Call, int_env: Dict[str, int]) -> Optional[int]:
        """Calcula el conteo de iteraciones de range(...) si sus argumentos son resolubles estáticamente."""
        args = call_node.args
        if not args or len(args) > 3:
            return None
        evaluated = [self._eval_constant_int(arg, int_env) for arg in args]
        if any(v is None for v in evaluated):
            return None
        if len(evaluated) == 1:
            return max(0, evaluated[0])  # type: ignore[operator]
        if len(evaluated) == 2:
            start, stop = evaluated[0], evaluated[1]
            return max(0, stop - start)  # type: ignore[operator]
        start, stop, step = evaluated[0], evaluated[1], evaluated[2]
        if step == 0:
            return None
        if step > 0:  # type: ignore[operator]
            if stop <= start:  # type: ignore[operator]
                return 0
            return (stop - start + step - 1) // step  # type: ignore[operator]
        if stop >= start:  # type: ignore[operator]
            return 0
        return (start - stop - step - 1) // (-step)  # type: ignore[operator]

    @staticmethod
    def _extract_root_name(node: ast.AST) -> Optional[str]:
        """Obtiene el nombre raíz de una cadena de atributos (ej. a.b.c -> 'a')."""
        cur = node
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if isinstance(cur, ast.Name):
            return cur.id
        return None

    @staticmethod
    def _extract_attr_chain(node: ast.AST) -> Optional[str]:
        """Reconstruye una cadena punteada simple (ej. UsdGeom.Cube.Define)."""
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            parts.reverse()
            return ".".join(parts)
        return None

    def validate_code(self, python_code: str) -> Tuple[bool, Optional[str]]:
        """
        Valida mediante análisis AST que el código Python cumpla las directivas de seguridad,
        capacidades, acotamiento y no-destructividad OpenUSD.
        """
        # 1. Validación de tipo y contenido no vacío
        if not isinstance(python_code, str) or not python_code.strip():
            return False, "Input validation error: Code payload must be a non-empty string."

        # 2. Validación de longitud máxima (DoS / agotamiento de memoria)
        if len(python_code) > self.config.max_code_size:
            return (
                False,
                f"Security limit exceeded: Code payload length exceeds maximum allowed limit of {self.config.max_code_size} characters.",
            )

        # 3. Análisis sintáctico + compilación de módulo (rechaza return/yield top-level)
        try:
            tree = ast.parse(python_code)
            compile(tree, "<validate>", "exec")
        except SyntaxError as e:
            return False, f"Syntax Error in generated code: {e}"

        # 4. Recolección de alias de importación y constantes enteras simples
        module_aliases: Dict[str, str] = {}
        imported_symbols: Dict[str, Tuple[str, str]] = {}
        usd_schema_aliases: Set[str] = set()
        usd_prop_vars: Set[str] = set()
        int_constants: Dict[str, int] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0].lower()
                    local_name = alias.asname or alias.name.split(".")[0]
                    module_aliases[local_name] = root_pkg
                    if alias.name.startswith("pxr.") and any(
                        alias.name == f"pxr.{pref}" or alias.name.startswith(f"pxr.{pref}.")
                        for pref in self.config.direct_usd_schema_prefixes
                    ):
                        usd_schema_aliases.add(local_name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0].lower()
                    for alias in node.names:
                        local_name = alias.asname or alias.name
                        imported_symbols[local_name] = (root_pkg, alias.name)
                        if node.module.startswith("pxr") and any(
                            alias.name == pref or node.module.endswith(f".{pref}")
                            for pref in self.config.direct_usd_schema_prefixes
                        ):
                            usd_schema_aliases.add(local_name)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                val = self._eval_constant_int(node.value, int_constants)
                if val is not None:
                    int_constants[node.targets[0].id] = val
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr in _DIRECT_USD_PROP_PRODUCERS
                ):
                    usd_prop_vars.add(node.targets[0].id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                val = self._eval_constant_int(node.value, int_constants)
                if val is not None:
                    int_constants[node.target.id] = val
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr in _DIRECT_USD_PROP_PRODUCERS
                ):
                    usd_prop_vars.add(node.target.id)

        # 5. Protección prioritaria contra manipulación de prims protegidos del sistema
        lower_code = python_code.lower()
        tampering_keywords = (
            "delete", "remove", "clear", "destroy", "drop",
            "define", "create", "override", "set", "add", "mutate", "group", "bind",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for protected in self.config.protected_paths:
                    if node.value == protected or node.value.startswith(f"{protected}/"):
                        if any(kw in lower_code for kw in tampering_keywords):
                            return (
                                False,
                                f"Security Policy Violation: Tampering or mutating system-protected prim path '{node.value}' is strictly forbidden.",
                            )

        # 6. Detección de bucles infinitos, límites de iteraciones, potencias desmedidas y supresión en finally
        try_node_types: Tuple[type, ...] = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)
        for node in ast.walk(tree):
            if isinstance(node, try_node_types) and node.finalbody:
                for sub in node.finalbody:
                    for inner in ast.walk(sub):
                        if isinstance(inner, (ast.Return, ast.Break, ast.Continue)):
                            return (
                                False,
                                "Security Policy Violation: Control-flow jump ('return'/'break'/'continue') "
                                "inside a 'finally' block is prohibited because it suppresses cancellation.",
                            )

            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                exp_val = self._eval_constant_int(node.right, int_constants)
                base_val = self._eval_constant_int(node.left, int_constants)
                if exp_val is not None and exp_val > 10_000 and (base_val is None or abs(base_val) > 1):
                    return (
                        False,
                        f"Security Policy Violation: Exponentiation power ({exp_val}) exceeds safe compute bound.",
                    )

            elif isinstance(node, ast.While):
                is_always_true = isinstance(node.test, ast.Constant) and bool(node.test.value)
                if is_always_true:
                    has_break = any(isinstance(subnode, ast.Break) for subnode in ast.walk(node))
                    if not has_break:
                        return (
                            False,
                            "Security Policy Violation: Potential infinite loop detected ('while True' without break statement).",
                        )

            elif isinstance(node, ast.For):
                if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):
                    if node.iter.func.id == "range" and node.iter.args:
                        iter_count = self._compute_range_iterations(node.iter, int_constants)
                        if iter_count is not None:
                            if iter_count > self.config.max_loop_iterations:
                                return (
                                    False,
                                    f"Security Policy Violation: Loop iteration limit ({iter_count} > {self.config.max_loop_iterations}) exceeded.",
                                )
                            if iter_count > self.config.max_prims_creation_limit:
                                creates_prim = False
                                for subnode in ast.walk(node):
                                    if isinstance(subnode, ast.Call):
                                        if isinstance(subnode.func, ast.Attribute) and subnode.func.attr in (
                                            "Define", "DefinePrim", "CreatePrim", "Create",
                                            "AddSphere", "AddCube", "create_prim",
                                        ):
                                            creates_prim = True
                                            break
                                        elif isinstance(subnode.func, ast.Name) and subnode.func.id in (
                                            "DefinePrim", "CreatePrim", "create_prim",
                                        ):
                                            creates_prim = True
                                            break
                                if creates_prim:
                                    return (
                                        False,
                                        f"Security Policy Violation: Prim creation limit in loop ({iter_count} > {self.config.max_prims_creation_limit}) exceeded.",
                                    )

        # 7. Verificación de capacidades, identificadores reservados del runtime, builtins, dunders y SO
        forbidden_builtins_set = set(self.config.forbidden_builtins)
        forbidden_dunders_set = set(self.config.forbidden_dunder_attributes)
        forbidden_cap_attrs_set = set(self.config.forbidden_capability_attributes)
        forbidden_os_attrs_set = set(self.config.forbidden_os_attributes)
        os_scoped_attrs_set = set(self.config.os_scoped_attributes)

        for node in ast.walk(tree):
            # Proteger hooks internos del ejecutor cooperativo contra lectura/sobrescritura/borrado
            if isinstance(node, ast.Name) and node.id.startswith("__lmchat_"):
                return (
                    False,
                    f"Security Policy Violation: Access to internal execution guard identifier '{node.id}' is blocked.",
                )
            if isinstance(node, ast.arg) and node.arg.startswith("__lmchat_"):
                return (
                    False,
                    f"Security Policy Violation: Redefining internal execution guard parameter '{node.arg}' is blocked.",
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name.startswith("__lmchat_"):
                return (
                    False,
                    f"Security Policy Violation: Redefining internal execution symbol '{node.name}' is blocked.",
                )
            if isinstance(node, ast.Attribute) and node.attr.startswith("__lmchat_"):
                return (
                    False,
                    f"Security Policy Violation: Access to internal execution guard attribute '{node.attr}' is blocked.",
                )

            # Acceso a dunders restringidos o atributos de introspección/módulo prohibidos (en Call o Load!)
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden_dunders_set:
                    return (
                        False,
                        f"Security Policy Violation: Access to restricted dunder attribute '{node.attr}' is blocked.",
                    )
                if node.attr in forbidden_builtins_set and node.attr in ("eval", "exec", "compile", "open", "__import__"):
                    return (
                        False,
                        f"Security Policy Violation: Execution of forbidden builtin function '{node.attr}()' is blocked.",
                    )
                if node.attr in forbidden_cap_attrs_set:
                    return (
                        False,
                        f"Security Policy Violation: Access to restricted capability attribute '{node.attr}' is blocked.",
                    )
                if node.attr in forbidden_os_attrs_set:
                    return (
                        False,
                        f"Security Policy Violation: Dangerous system operation '{node.attr}()' is blocked.",
                    )

            if isinstance(node, ast.Name):
                if node.id in forbidden_dunders_set:
                    return (
                        False,
                        f"Security Policy Violation: Access to restricted dunder identifier '{node.id}' is blocked.",
                    )

            # Llamadas específicas (nombres, alias de imports, os_scoped_attributes y time.sleep)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name in forbidden_builtins_set:
                        return (
                            False,
                            f"Security Policy Violation: Execution of forbidden builtin function '{func_name}()' is blocked.",
                        )
                    if func_name in imported_symbols:
                        src_mod, src_sym = imported_symbols[func_name]
                        if src_mod in ("builtins", "__builtin__") and src_sym in forbidden_builtins_set:
                            return (
                                False,
                                f"Security Policy Violation: Execution of forbidden builtin function '{src_sym}()' is blocked.",
                            )
                        if src_mod in _OS_LIKE_MODULES and (
                            src_sym in forbidden_os_attrs_set or src_sym in os_scoped_attrs_set
                        ):
                            return (
                                False,
                                f"Security Policy Violation: Dangerous system operation '{src_sym}()' is blocked.",
                            )
                        if src_mod == "time" and src_sym == "sleep":
                            return (
                                False,
                                "Security Policy Violation: Blocking call 'time.sleep()' is prohibited on Kit threads.",
                            )
                    if func_name in ("getattr", "hasattr") and len(node.args) >= 2:
                        second = node.args[1]
                        if isinstance(second, ast.Constant) and isinstance(second.value, str):
                            if (
                                second.value.startswith("_")
                                or second.value in forbidden_builtins_set
                                or second.value in forbidden_cap_attrs_set
                            ):
                                return (
                                    False,
                                    f"Security Policy Violation: Dynamic access to restricted attribute '{second.value}' is blocked.",
                                )

                elif isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr
                    root_name = self._extract_root_name(node.func.value)
                    resolved_mod = module_aliases.get(root_name or "", (root_name or "").lower())

                    if attr_name in forbidden_builtins_set and resolved_mod in ("builtins", "__builtin__"):
                        return (
                            False,
                            f"Security Policy Violation: Execution of forbidden builtin function '{attr_name}()' is blocked.",
                        )

                    if attr_name == "sleep" and resolved_mod in ("time", "asyncio"):
                        return (
                            False,
                            "Security Policy Violation: Blocking call 'time.sleep()' is prohibited on Kit threads.",
                        )

                    # Bloquear operaciones con homónimos benignos (replace, remove, rename, truncate)
                    # SOLO cuando el receptor proviene de módulos de SO/archivos (evita falsos positivos en str.replace).
                    if attr_name in os_scoped_attrs_set and resolved_mod in _OS_LIKE_MODULES:
                        return (
                            False,
                            f"Security Policy Violation: Dangerous system operation '{attr_name}()' is blocked.",
                        )

            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in forbidden_builtins_set:
                    return (
                        False,
                        f"Security Policy Violation: Execution of forbidden builtin function '{node.id}()' is blocked.",
                    )

        # 8. Verificación de imports prohibidos, wildcards y lista blanca de módulos
        forbidden_modules_set = set(self.config.forbidden_modules)
        allowed_modules_set = set(self.config.allowed_import_modules)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0].lower()
                    if root_pkg in forbidden_modules_set:
                        return (
                            False,
                            f"Security Policy Violation: Import of forbidden module '{alias.name}' is prohibited.",
                        )
                    if self.config.enforce_import_allowlist and root_pkg not in allowed_modules_set:
                        return (
                            False,
                            f"Security Policy Violation: Import of non-allowlisted module '{alias.name}' is prohibited.",
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    return (
                        False,
                        "Security Policy Violation: Relative imports are prohibited.",
                    )
                if any(alias.name == "*" for alias in node.names):
                    return (
                        False,
                        f"Security Policy Violation: Wildcard import 'from {node.module} import *' is prohibited; import explicit names.",
                    )
                if node.module:
                    root_pkg = node.module.split(".")[0].lower()
                    if root_pkg in forbidden_modules_set:
                        return (
                            False,
                            f"Security Policy Violation: Import from forbidden module '{node.module}' is prohibited.",
                        )
                    if self.config.enforce_import_allowlist and root_pkg not in allowed_modules_set:
                        return (
                            False,
                            f"Security Policy Violation: Import from non-allowlisted module '{node.module}' is prohibited.",
                        )

        # 9. Gobernanza Undo OpenUSD (F01): rechazar escrituras directas sobre Stage/Sdf/Atributos
        #    (tanto llamadas directas como referencias de atributo tipo `fn = stage.DefinePrim`).
        if self.config.forbid_direct_usd_writes:
            direct_write_methods = set(self.config.direct_usd_write_methods)
            schema_prefixes = set(self.config.direct_usd_schema_prefixes)

            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if node.attr in direct_write_methods:
                        return (
                            False,
                            f"Security Policy Violation: Direct USD stage mutation '{node.attr}()' bypasses Kit Undo history. "
                            "Use reversible commands via controller.create_prim()/transform_prim()/set_prim_attribute() "
                            "or omni.kit.commands.execute().",
                        )
                    if node.attr == "Define":
                        chain = self._extract_attr_chain(node) or ""
                        root = self._extract_root_name(node.value) or ""
                        if (
                            root in schema_prefixes
                            or root in usd_schema_aliases
                            or any(f"{pref}." in chain for pref in schema_prefixes)
                        ):
                            return (
                                False,
                                f"Security Policy Violation: Direct USD stage mutation '{chain or node.attr}()' bypasses Kit Undo history. "
                                "Use reversible commands via controller.create_prim() or omni.kit.commands.execute().",
                            )
                    if node.attr in ("Save", "Export"):
                        root = (self._extract_root_name(node.value) or "").lower()
                        is_stage_call_receiver = (
                            isinstance(node.value, ast.Call)
                            and isinstance(node.value.func, ast.Attribute)
                            and node.value.func.attr in ("get_stage", "GetRootLayer", "GetSessionLayer", "GetEditTarget")
                        )
                        if root in ("stage", "layer", "root_layer", "usd") or is_stage_call_receiver:
                            return (
                                False,
                                f"Security Policy Violation: Direct USD layer/stage persistence ('{node.attr}()') is blocked in generated scripts.",
                            )

                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Set":
                    receiver = node.func.value
                    if (
                        isinstance(receiver, ast.Call)
                        and isinstance(receiver.func, ast.Attribute)
                        and receiver.func.attr in _DIRECT_USD_PROP_PRODUCERS
                    ):
                        return (
                            False,
                            f"Security Policy Violation: Direct USD property write '{receiver.func.attr}().Set()' "
                            "bypasses Kit Undo history. Use controller.set_prim_attribute() or controller.transform_prim().",
                        )
                    if isinstance(receiver, ast.Name) and receiver.id in usd_prop_vars:
                        return (
                            False,
                            f"Security Policy Violation: Direct USD property write '{receiver.id}.Set()' "
                            "bypasses Kit Undo history. Use controller.set_prim_attribute() or controller.transform_prim().",
                        )

        return True, None
