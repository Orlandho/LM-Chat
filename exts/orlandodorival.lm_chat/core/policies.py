# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Políticas de Gobernanza y Seguridad Espacial para Agentes de LM-Chat™.

Implementa directivas y guardrails para:
- Protección de prims del sistema y jerarquías protegidas en OpenUSD.
- Detección de bucles infinitos y recursión peligrosa mediante análisis AST.
- Prevención de inyecciones de comandos de sistema operativo y llamadas no autorizadas.
- Límites de conteo para evitar explosión combinatoria de geometrías.
"""

import ast
import re
from typing import Tuple, Optional, List, Set, Any
from dataclasses import dataclass, field

from core.interfaces import IAgentPolicy


@dataclass
class AgentPolicyConfig:
    """Configuración formal de directivas y límites de seguridad para el agente."""
    max_prims_creation_limit: int = 500
    max_code_size: int = 100_000
    max_loop_iterations: int = 10_000
    protected_paths: Tuple[str, ...] = (
        "/OmniverseKit_Root",
        "/Render",
        "/World/System",
        "/Library",
    )
    forbidden_modules: Tuple[str, ...] = (
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
    )
    forbidden_builtins: Tuple[str, ...] = (
        "eval",
        "compile",
        "exec",
        "__import__",
        "breakpoint",
        "open",
    )
    forbidden_os_attributes: Tuple[str, ...] = (
        "system",
        "popen",
        "spawn",
        "remove",
        "rmdir",
        "unlink",
        "kill",
        "rename",
        "replace",
        "truncate",
    )


class SpatialSecurityPolicy(IAgentPolicy):
    """
    Guardián y validador de políticas de seguridad espacial y de ejecución de código.
    Utiliza análisis estático AST para validar scripts antes de mutar el Stage OpenUSD.
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

    def validate_code(self, python_code: str) -> Tuple[bool, Optional[str]]:
        """
        Valida que el código Python generado cumpla todas las directivas de seguridad.

        Args:
            python_code (str): Código Python a validar.

        Returns:
            Tuple[bool, Optional[str]]: (True, None) si es seguro, o (False, mensaje_error).
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

        # 3. Análisis sintáctico mediante AST
        try:
            tree = ast.parse(python_code)
        except SyntaxError as e:
            return False, f"Syntax Error in generated code: {e}"

        # 4. Inspección de nodos AST
        for node in ast.walk(tree):
            # A. Verificación de imports prohibidos
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0].lower()
                    if root_pkg in self.config.forbidden_modules:
                        return (
                            False,
                            f"Security Policy Violation: Import of forbidden module '{alias.name}' is prohibited.",
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0].lower()
                    if root_pkg in self.config.forbidden_modules:
                        return (
                            False,
                            f"Security Policy Violation: Import from forbidden module '{node.module}' is prohibited.",
                        )

            # B. Verificación de llamadas a funciones o builtins prohibidos
            elif isinstance(node, ast.Call):
                # Llamadas a nombres directos (ej. eval(...), compile(...))
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name in self.config.forbidden_builtins:
                        return (
                            False,
                            f"Security Policy Violation: Execution of forbidden builtin function '{func_name}()' is blocked.",
                        )

                # Llamadas a atributos (ej. os.system(...), os.remove(...))
                elif isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr
                    if attr_name in self.config.forbidden_os_attributes:
                        return (
                            False,
                            f"Security Policy Violation: Dangerous system operation '{attr_name}()' is blocked.",
                        )

            # C. Detección de bucles infinitos estáticos (while True: sin break)
            elif isinstance(node, ast.While):
                # Si la prueba es constante True (o número distinto de 0)
                is_always_true = False
                if isinstance(node.test, ast.Constant) and bool(node.test.value):
                    is_always_true = True
                elif isinstance(node.test, ast.NameConstant) and node.test.value is True:
                    is_always_true = True

                if is_always_true:
                    # Comprobar si hay alguna instrucción Break dentro del cuerpo del while
                    has_break = any(isinstance(subnode, ast.Break) for subnode in ast.walk(node))
                    if not has_break:
                        return (
                            False,
                            "Security Policy Violation: Potential infinite loop detected ('while True' without break statement).",
                        )

            # D. Detección de rangos de bucles excesivos y límites de creación de prims
            elif isinstance(node, ast.For):
                if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):
                    if node.iter.func.id == "range" and node.iter.args:
                        # Extraer el argumento final del rango
                        last_arg = node.iter.args[-1]
                        if isinstance(last_arg, ast.Constant) and isinstance(last_arg.value, int):
                            if last_arg.value > self.config.max_loop_iterations:
                                return (
                                    False,
                                    f"Security Policy Violation: Loop iteration limit ({last_arg.value} > {self.config.max_loop_iterations}) exceeded.",
                                )
                            # Respeto de límites de prims: verificar si el bucle instancia geometrías/prims
                            if last_arg.value > self.config.max_prims_creation_limit:
                                creates_prim = False
                                for subnode in ast.walk(node):
                                    if isinstance(subnode, ast.Call):
                                        if isinstance(subnode.func, ast.Attribute) and subnode.func.attr in (
                                            "Define", "DefinePrim", "CreatePrim", "Create", "AddSphere", "AddCube"
                                        ):
                                            creates_prim = True
                                            break
                                        elif isinstance(subnode.func, ast.Name) and subnode.func.id in ("DefinePrim", "CreatePrim"):
                                            creates_prim = True
                                            break
                                if creates_prim:
                                    return (
                                        False,
                                        f"Security Policy Violation: Prim creation limit in loop ({last_arg.value} > {self.config.max_prims_creation_limit}) exceeded.",
                                    )

            # E. Protección contra manipulación de prims protegidos del sistema
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for protected in self.config.protected_paths:
                    if node.value == protected or node.value.startswith(f"{protected}/"):
                        # Comprobar si el contexto del script involucra manipulación, mutación o eliminación
                        lower_code = python_code.lower()
                        tampering_keywords = (
                            "delete", "remove", "clear", "destroy", "drop",
                            "define", "create", "override", "set", "add", "mutate", "group", "bind"
                        )
                        if any(kw in lower_code for kw in tampering_keywords):
                            return (
                                False,
                                f"Security Policy Violation: Tampering or mutating system-protected prim path '{node.value}' is strictly forbidden.",
                            )

        return True, None
