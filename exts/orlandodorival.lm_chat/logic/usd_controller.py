# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

# -*- coding: utf-8 -*-

"""
Módulo USD Controller para ejecución segura y no-destructiva en OpenUSD.
Integra políticas de seguridad espacial (SpatialSecurityPolicy) y comandos reversibles (omni.kit.commands).
"""

from typing import Dict, Any, List, Optional
import logging

try:
    import omni.ext
    import omni.kit.commands
    import omni.kit.undo
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

from core.policies import SpatialSecurityPolicy, AgentPolicyConfig
from logic.usd_inspector import USDInspector

logger = logging.getLogger(__name__)


class USDController:
    """Handles execution of dynamic USD python code with safety policies and Undo/Redo."""

    # Maximum payload limit (100KB) to prevent DoS via memory/CPU exhaustion
    MAX_CODE_SIZE: int = 100_000

    def __init__(self, policy: Optional[SpatialSecurityPolicy] = None) -> None:
        """Inicializa el controlador USD con políticas espaciales y el inspector del proyecto."""
        self._policy = policy or SpatialSecurityPolicy()
        self._inspector = USDInspector()

    @property
    def policy(self) -> SpatialSecurityPolicy:
        """Acceso a la política de seguridad espacial activa."""
        return self._policy

    @property
    def inspector(self) -> USDInspector:
        """Acceso al inspector de salud de escena."""
        return self._inspector

    def execute_code(self, python_code: str) -> dict:
        """
        Dynamically executes extracted python code within the Omniverse context,
        enforcing security policies and wrapping operations in an undo block.

        Args:
            python_code (str): The code block to execute.

        Returns:
            dict: Structured response indicating success or failure.
        """
        if not isinstance(python_code, str):
            return {"success": False, "error_msg": "Input validation error: python_code must be a string."}

        if not python_code.strip():
            return {"success": False, "error_msg": "Input validation error: python_code cannot be empty."}

        if len(python_code) > self.MAX_CODE_SIZE:
            return {"success": False, "error_msg": f"Security limit exceeded: Code size exceeds maximum allowed limit ({self.MAX_CODE_SIZE} bytes)."}

        # Security Policy & Guardrail validation
        is_valid, violation_err = self._policy.validate_code(python_code)
        if not is_valid:
            return {"success": False, "error_msg": violation_err}

        # Prepare execution environment with safe bindings, restricted builtins, and inspector
        safe_builtins = __builtins__.copy() if isinstance(__builtins__, dict) else __builtins__.__dict__.copy()
        for forbidden in self._policy.config.forbidden_builtins + ("open",):
            safe_builtins.pop(forbidden, None)

        exec_globals = {
            "__builtins__": safe_builtins,
            "omni": __import__('omni') if omni is not None else None,
            "pxr": pxr,
            "Usd": Usd,
            "UsdGeom": UsdGeom,
            "UsdShade": UsdShade,
            "Sdf": Sdf,
            "Gf": Gf,
            "inspector": self._inspector,
            "controller": self,
        }

        undo_opened = False
        try:
            # Wrap execution in an Undo/Redo block to guarantee native Ctrl+Z support
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "undo") and hasattr(omni.kit.undo, "begin"):
                try:
                    omni.kit.undo.begin()
                    undo_opened = True
                except Exception:
                    pass

            exec(python_code, exec_globals)
            return {"success": True}
        except Exception as exec_err:
            return {"success": False, "error_msg": str(exec_err)}
        finally:
            if undo_opened and omni and hasattr(omni, "kit") and hasattr(omni.kit, "undo") and hasattr(omni.kit.undo, "end"):
                try:
                    omni.kit.undo.end()
                except Exception:
                    pass

    def transform_prim(
        self,
        prim_path: str,
        new_transform_matrix: Optional[Any] = None,
        translation: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Transforma interactivamente un prim existente en el Stage usando omni.kit.commands.

        Args:
            prim_path: Ruta del prim a transformar.
            new_transform_matrix: Matriz de transformación 4x4 opcional.
            translation: Vector [x, y, z] opcional.
            rotation: Ángulos de Euler [rx, ry, rz] opcionales.
            scale: Escala [sx, sy, sz] opcional.

        Returns:
            Dict[str, Any]: Resultado de la ejecución con status de éxito.
        """
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                # Ejecutar a través del comando reversible
                kwargs: Dict[str, Any] = {"path": prim_path}
                if new_transform_matrix is not None:
                    kwargs["new_transform_matrix"] = new_transform_matrix
                if translation is not None:
                    kwargs["translation"] = translation
                if rotation is not None:
                    kwargs["rotation"] = rotation
                if scale is not None:
                    kwargs["scale"] = scale

                omni.kit.commands.execute("TransformPrimCommand", **kwargs)
                return {"success": True, "path": prim_path}
            else:
                return {"success": True, "path": prim_path, "note": "Ejecución simulada en entorno headless"}
        except Exception as e:
            return {"success": False, "error_msg": str(e)}

    def bind_material(self, prim_path: str, material_path: str) -> Dict[str, Any]:
        """
        Enlaza un material UsdShade/MDL a un prim (usualmente una malla UsdGeom.Mesh).

        Args:
            prim_path: Ruta del prim receptor.
            material_path: Ruta del material a asignar.

        Returns:
            Dict[str, Any]: Resultado del enlace.
        """
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                omni.kit.commands.execute(
                    "BindMaterialCommand",
                    prim_path=prim_path,
                    material_path=material_path,
                )
                return {"success": True, "prim_path": prim_path, "material_path": material_path}
            else:
                return {"success": True, "prim_path": prim_path, "material_path": material_path, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": str(e)}

    def group_prims(self, prim_paths: List[str], parent_path: str) -> Dict[str, Any]:
        """
        Reorganiza una lista de prims bajo un nuevo nodo padre o Scope en la jerarquía.

        Args:
            prim_paths: Lista de rutas de prims a agrupar.
            parent_path: Ruta del scope/grupo destino.

        Returns:
            Dict[str, Any]: Resultado de la agrupación.
        """
        if len(prim_paths) > getattr(self._policy.config, "max_prims_creation_limit", 500):
            limit = self._policy.config.max_prims_creation_limit
            return {"success": False, "error_msg": f"El número de prims ({len(prim_paths)}) excede el límite permitido de {limit}."}

        if self._policy.is_prim_protected(parent_path):
            return {"success": False, "error_msg": f"La ruta destino '{parent_path}' está protegida por el sistema."}

        for p in prim_paths:
            if self._policy.is_prim_protected(p):
                return {"success": False, "error_msg": f"El prim '{p}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                omni.kit.commands.execute(
                    "GroupPrimsCommand",
                    prim_paths=prim_paths,
                    parent_path=parent_path,
                )
                return {"success": True, "grouped_count": len(prim_paths), "parent_path": parent_path}
            else:
                return {"success": True, "grouped_count": len(prim_paths), "parent_path": parent_path, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": str(e)}

    def set_prim_attribute(self, prim_path: str, attr_name: str, value: Any) -> Dict[str, Any]:
        """
        Modifica un atributo de un prim mediante comandos reversibles de Omniverse.

        Args:
            prim_path: Ruta del prim.
            attr_name: Nombre del atributo a alterar (ej. 'intensity', 'visibility').
            value: Nuevo valor.

        Returns:
            Dict[str, Any]: Resultado de la modificación.
        """
        if self._policy.is_prim_protected(prim_path):
            return {"success": False, "error_msg": f"El prim '{prim_path}' está protegido por el sistema."}

        try:
            if omni and hasattr(omni, "kit") and hasattr(omni.kit, "commands"):
                omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    prop_path=f"{prim_path}.{attr_name}",
                    value=value,
                    prev=None,
                )
                return {"success": True, "prim_path": prim_path, "attribute": attr_name, "value": value}
            else:
                return {"success": True, "prim_path": prim_path, "attribute": attr_name, "value": value, "note": "Simulado"}
        except Exception as e:
            return {"success": False, "error_msg": str(e)}
