# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo USD Inspector para la auditoría y diagnóstico de salud en proyectos OpenUSD.
Implementa el contrato IUSDInspector para:
- Detectar activos y texturas no encontrados (Sdf.AssetPath roto).
- Búsqueda semántica avanzada de prims por tipo, visibilidad y atributos.
- Evaluación del estado de la pila de capas (Layer Stack) y cambios no guardados.
"""

import os
import re
import logging
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional

try:
    import omni.usd
    from pxr import Usd, UsdGeom, UsdLux, Sdf
except ImportError:
    omni = None
    Usd = None
    UsdGeom = None
    UsdLux = None
    Sdf = None

from core.interfaces import IUSDInspector

logger = logging.getLogger(__name__)


def _is_mock(obj: Any) -> bool:
    """Helper para verificar si un objeto es un Mock/MagicMock sin configurar."""
    return getattr(type(obj), "__module__", "").startswith("unittest.mock")


class USDInspector(IUSDInspector):
    """Motor de inspección y diagnóstico de salud para escenas OpenUSD en Omniverse."""

    def __init__(self) -> None:
        """Inicializa el inspector de OpenUSD."""
        pass

    def _get_stage(self) -> Optional[Any]:
        """Obtiene la referencia a la escena activa (Stage) de Omniverse."""
        try:
            if omni and hasattr(omni, "usd"):
                usd_context = omni.usd.get_context()
                if usd_context:
                    return usd_context.get_stage()
        except Exception as e:
            logger.warning(f"No se pudo acceder al stage de Omniverse: {e}")
        return None

    def audit_missing_assets(self) -> List[Dict[str, Any]]:
        """
        Escanea todos los atributos de tipo Sdf.AssetPath en el Stage y valida la existencia de los archivos en disco.

        Returns:
            List[Dict[str, Any]]: Lista de activos faltantes con información de diagnóstico.
        """
        stage = self._get_stage()
        if not stage:
            return []

        missing_assets: List[Dict[str, Any]] = []

        try:
            for prim in stage.Traverse():
                if not prim or _is_mock(prim):
                    if _is_mock(prim) and not hasattr(prim, "GetAttributes"):
                        continue

                if hasattr(prim, "IsValid") and callable(prim.IsValid) and not prim.IsValid():
                    continue

                prim_path = str(prim.GetPath()) if hasattr(prim, "GetPath") else "/Unknown"

                # Obtener todos los atributos del prim
                attributes = prim.GetAttributes() if hasattr(prim, "GetAttributes") else []
                if _is_mock(attributes) and not isinstance(attributes, list):
                    continue

                for attr in attributes:
                    try:
                        # Verificar si el tipo de atributo es Asset o SdfAssetPath
                        val = attr.Get() if hasattr(attr, "Get") else None
                        if val is None or _is_mock(val):
                            continue

                        # Sdf.AssetPath o valor con atributos path / resolvedPath
                        is_asset = False
                        asset_raw_path = ""
                        resolved_path = ""

                        if hasattr(val, "path"):
                            is_asset = True
                            asset_raw_path = str(val.path)
                            resolved_path = str(getattr(val, "resolvedPath", ""))
                        elif hasattr(attr, "GetTypeName") and str(attr.GetTypeName()).lower() in ("asset", "assetpath"):
                            is_asset = True
                            asset_raw_path = str(val)

                        if is_asset and asset_raw_path:
                            # Validar existencia de archivo si es una ruta local
                            target_path = resolved_path or asset_raw_path
                            clean_target = target_path

                            # Limpiar prefijos de URI si existen (soporte Windows file:///C:/...)
                            if clean_target.startswith("file://"):
                                url_path = clean_target[7:]
                                clean_target = urllib.request.url2pathname(url_path)

                            # Comprobar si el archivo físico existe en disco
                            exists = False
                            if os.path.isabs(clean_target) and os.path.exists(clean_target):
                                exists = True
                            elif not os.path.isabs(clean_target) and (
                                clean_target.startswith("http://")
                                or clean_target.startswith("https://")
                                or clean_target.startswith("omniverse://")
                            ):
                                # URLs externas o del servidor Nucleus se asumen resolubles por el motor
                                exists = True
                            elif not os.path.isabs(clean_target):
                                # Intentar resolver relativo a la capa raíz del Stage
                                stage_dir = None
                                if hasattr(stage, "GetRootLayer"):
                                    root_layer = stage.GetRootLayer()
                                    if root_layer:
                                        real_path = getattr(root_layer, "realPath", None) or getattr(root_layer, "identifier", "")
                                        if real_path and os.path.exists(os.path.dirname(str(real_path))):
                                            stage_dir = os.path.dirname(str(real_path))
                                if stage_dir:
                                    candidate = os.path.normpath(os.path.join(stage_dir, clean_target))
                                    if os.path.exists(candidate):
                                        exists = True
                                elif os.path.exists(clean_target):
                                    exists = True

                            if not exists and clean_target:
                                attr_name = str(attr.GetName()) if hasattr(attr, "GetName") else "unknown"
                                missing_assets.append({
                                    "prim_path": prim_path,
                                    "attribute_name": attr_name,
                                    "attribute": attr_name,
                                    "asset_path": asset_raw_path,
                                    "raw_path": asset_raw_path,
                                    "resolved_path": resolved_path,
                                    "status": "missing",
                                    "is_missing": True,
                                })
                    except Exception as attr_err:
                        logger.debug(f"Error inspeccionando atributo de prim {prim_path}: {attr_err}")

        except Exception as e:
            logger.error(f"Error durante auditoría de activos en Stage: {e}", exc_info=True)

        return missing_assets

    def find_prims_by_query(self, query_criteria: Dict[str, Any]) -> List[str]:
        """
        Permite búsquedas complejas por tipo (e.g. 'Mesh', 'Light'), visibilidad o atributos.

        Args:
            query_criteria: Criterios de búsqueda:
                - 'type': Nombre del tipo exacto o parcial (ej. 'Light', 'Mesh', 'UsdLuxDiskLight')
                - 'visibility': 'invisible' o 'inherited'
                - 'name_pattern': Subcadena o patrón regex en la ruta/nombre del prim
                - 'has_attribute': Nombre de atributo que debe poseer el prim
                - 'attribute_filter': Dict con {attr_name: valor_esperado}

        Returns:
            List[str]: Rutas de prims coincidentes.
        """
        stage = self._get_stage()
        if not stage:
            return []

        matched_paths: List[str] = []
        target_type = str(query_criteria.get("type", "")).lower()
        target_vis = str(query_criteria.get("visibility", "")).lower()
        name_pattern = query_criteria.get("name_pattern")
        has_attr = query_criteria.get("has_attribute")
        attr_filter = query_criteria.get("attribute_filter", {})

        try:
            for prim in stage.Traverse():
                if not prim or _is_mock(prim):
                    if _is_mock(prim) and not hasattr(prim, "GetPath"):
                        continue
                if hasattr(prim, "IsValid") and callable(prim.IsValid) and not prim.IsValid():
                    continue

                path_str = str(prim.GetPath())

                # 1. Filtro por tipo
                if target_type:
                    prim_type = str(prim.GetTypeName()).lower() if hasattr(prim, "GetTypeName") else ""
                    if target_type not in prim_type:
                        continue

                # 2. Filtro por patrón de nombre
                if name_pattern:
                    if not re.search(name_pattern, path_str, re.IGNORECASE):
                        continue

                # 3. Filtro por visibilidad
                if target_vis:
                    vis_val = "inherited"
                    if hasattr(prim, "GetAttribute"):
                        vis_attr = prim.GetAttribute("visibility")
                        if vis_attr and hasattr(vis_attr, "Get"):
                            v = vis_attr.Get()
                            if v is not None:
                                vis_val = str(v).lower()
                    if vis_val != target_vis:
                        continue

                # 4. Filtro por presencia de atributo
                if has_attr:
                    if not (hasattr(prim, "HasAttribute") and prim.HasAttribute(has_attr)):
                        if hasattr(prim, "GetAttribute") and not prim.GetAttribute(has_attr):
                            continue

                # 5. Filtro por valor de atributos
                if attr_filter and isinstance(attr_filter, dict):
                    match_attrs = True
                    for k, expected_v in attr_filter.items():
                        if hasattr(prim, "GetAttribute"):
                            attr = prim.GetAttribute(k)
                            val = attr.Get() if attr and hasattr(attr, "Get") else None
                            if val != expected_v:
                                match_attrs = False
                                break
                    if not match_attrs:
                        continue

                matched_paths.append(path_str)

        except Exception as e:
            logger.error(f"Error buscando prims por consulta: {e}", exc_info=True)

        return matched_paths

    def get_layer_stack_status(self) -> Dict[str, Any]:
        """
        Informa sobre la capa raíz, capas de sesión y subcapas anónimas modificadas no guardadas.

        Returns:
            Dict[str, Any]: Estado estructurado de las capas en el Stage.
        """
        stage = self._get_stage()
        if not stage:
            return {
                "root_layer": None,
                "session_layer": None,
                "total_layers": 0,
                "dirty_layers": [],
                "has_unsaved_changes": False,
            }

        status: Dict[str, Any] = {
            "root_layer": None,
            "session_layer": None,
            "total_layers": 0,
            "dirty_layers": [],
            "has_unsaved_changes": False,
        }

        try:
            if hasattr(stage, "GetRootLayer"):
                root = stage.GetRootLayer()
                if root and hasattr(root, "identifier"):
                    status["root_layer"] = str(root.identifier)

            if hasattr(stage, "GetSessionLayer"):
                session_layer = stage.GetSessionLayer()
                if session_layer and hasattr(session_layer, "identifier"):
                    status["session_layer"] = str(session_layer.identifier)

            # Capas en la pila
            layers = stage.GetLayerStack() if hasattr(stage, "GetLayerStack") else []
            if _is_mock(layers) and not isinstance(layers, list):
                layers = []

            status["total_layers"] = len(layers)

            dirty_list: List[str] = []
            for layer in layers:
                is_layer_dirty = False
                if hasattr(layer, "dirty") and isinstance(layer.dirty, bool):
                    is_layer_dirty = layer.dirty
                elif hasattr(layer, "IsDirty") and callable(layer.IsDirty):
                    is_layer_dirty = bool(layer.IsDirty())
                elif hasattr(layer, "isDirty"):
                    is_layer_dirty = bool(layer.isDirty() if callable(layer.isDirty) else layer.isDirty)

                if is_layer_dirty:
                    ident = str(getattr(layer, "identifier", "anonymous_layer"))
                    dirty_list.append(ident)

            status["dirty_layers"] = dirty_list
            status["has_unsaved_changes"] = len(dirty_list) > 0

        except Exception as e:
            logger.error(f"Error obteniendo estado de capa stack: {e}", exc_info=True)

        return status
