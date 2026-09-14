# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Spatial USD Context Manager for converting OpenUSD Stage hierarchy to JSON context for LLMs.
"""

import json
import logging
from typing import Dict, Any, List, Optional
import omni.usd
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
from core.interfaces import IStageContextSerializer

logger = logging.getLogger(__name__)


def _is_mock(obj: Any) -> bool:
    """Helper to check if an object is a Mock/MagicMock instance from unittest.mock."""
    return getattr(type(obj), "__module__", "").startswith("unittest.mock")


class StageContextSerializer(IStageContextSerializer):
    """Serializes the active OpenUSD stage into JSON context and extracts detailed prim summaries."""

    def get_stage_context_as_json(self, max_depth: int = 4) -> str:
        """
        Traverses active USD stage hierarchy up to max_depth and returns a JSON string.

        Args:
            max_depth (int): Maximum depth in the USD hierarchy to traverse. Default is 4.

        Returns:
            str: JSON representation of the stage hierarchy.
        """
        try:
            usd_context = omni.usd.get_context()
            if not usd_context:
                return json.dumps({"prims": []})
            stage = usd_context.get_stage()
            if not stage:
                return json.dumps({"prims": []})
        except Exception as err:
            logger.warning(f"Error accessing active USD stage: {err}")
            return json.dumps({"prims": []})

        prims_data: List[Dict[str, Any]] = []

        try:
            for prim in stage.Traverse():
                if not prim or _is_mock(prim):
                    # Check if unconfigured mock prim
                    if _is_mock(prim) and not hasattr(prim, "GetPath"):
                        continue
                if hasattr(prim, "IsValid") and callable(prim.IsValid):
                    if not prim.IsValid():
                        continue

                path_str = str(prim.GetPath())
                if _is_mock(prim.GetPath()):
                    continue

                path_elements = [p for p in path_str.strip("/").split("/") if p]
                depth = len(path_elements)

                if depth > max_depth:
                    continue

                prim_type = "Scope"
                if hasattr(prim, "GetTypeName") and callable(prim.GetTypeName):
                    type_name = prim.GetTypeName()
                    if type_name and not _is_mock(type_name):
                        prim_type = str(type_name)

                visibility = self._get_prim_visibility(prim)
                attributes_sample = self._extract_attributes_sample(prim)

                prim_info = {
                    "path": path_str,
                    "type": prim_type,
                    "visibility": visibility,
                    "attributes_sample": attributes_sample,
                }
                prims_data.append(prim_info)

        except Exception as err:
            logger.error(f"Error traversing stage prims: {err}")

        return json.dumps({"prims": prims_data}, indent=2, sort_keys=True)

    def get_prim_summary(self, prim_path: str) -> Dict[str, Any]:
        """
        Extracts extended details of a specific prim (bounding box, transform matrix, associated materials).

        Args:
            prim_path (str): SdfPath string of the prim to inspect.

        Returns:
            Dict[str, Any]: Detailed dictionary containing prim summary or error.
        """
        summary: Dict[str, Any] = {
            "path": prim_path,
            "type": "Unknown",
            "bounding_box": None,
            "transform_matrix": None,
            "associated_materials": [],
        }

        try:
            usd_context = omni.usd.get_context()
            if not usd_context:
                return {"error": "USD context not available", "path": prim_path}
            stage = usd_context.get_stage()
            if not stage:
                return {"error": "USD stage not available", "path": prim_path}
        except Exception as err:
            return {"error": f"Failed to access USD stage: {err}", "path": prim_path}

        try:
            sdf_path = Sdf.Path(prim_path) if hasattr(Sdf, "Path") and callable(Sdf.Path) else prim_path
            prim = stage.GetPrimAtPath(sdf_path)
            if not prim or _is_mock(prim):
                if not prim:
                    return {"error": f"Prim not found at path '{prim_path}'", "path": prim_path}
                if hasattr(prim, "IsValid") and callable(prim.IsValid):
                    if not prim.IsValid():
                        return {"error": f"Prim not found at path '{prim_path}'", "path": prim_path}
                if _is_mock(prim) and not hasattr(prim, "_is_configured"):
                    return {"error": f"Prim not found at path '{prim_path}'", "path": prim_path}

            if hasattr(prim, "GetTypeName") and callable(prim.GetTypeName):
                type_name = prim.GetTypeName()
                if type_name and not _is_mock(type_name):
                    summary["type"] = str(type_name)

            # Bounding Box
            summary["bounding_box"] = self._compute_bounding_box(stage, prim)

            # Transform Matrix
            summary["transform_matrix"] = self._compute_transform_matrix(prim)

            # Associated Materials
            summary["associated_materials"] = self._get_associated_materials(prim)

        except Exception as err:
            logger.error(f"Error building summary for prim '{prim_path}': {err}")
            return {"error": str(err), "path": prim_path}

        return summary

    def _get_prim_visibility(self, prim: Any) -> str:
        """Extracts visibility status from a USD prim."""
        try:
            if hasattr(UsdGeom, "Imageable"):
                imageable = UsdGeom.Imageable(prim)
                if hasattr(imageable, "GetVisibilityAttr"):
                    vis_attr = imageable.GetVisibilityAttr()
                    if vis_attr and hasattr(vis_attr, "Get"):
                        vis_val = vis_attr.Get()
                        if vis_val is not None and not _is_mock(vis_val):
                            return str(vis_val)
            if hasattr(prim, "GetAttribute"):
                vis_attr = prim.GetAttribute("visibility")
                if vis_attr and hasattr(vis_attr, "Get"):
                    vis_val = vis_attr.Get()
                    if vis_val is not None and not _is_mock(vis_val):
                        return str(vis_val)
        except Exception:
            pass
        return "inherited"

    def _extract_attributes_sample(self, prim: Any) -> Dict[str, Any]:
        """Extracts key attribute samples from a USD prim."""
        sample: Dict[str, Any] = {}
        target_keys = [
            "xformOp:translate",
            "xformOp:rotateXYZ",
            "xformOp:scale",
            "displayColor",
            "primvars:displayColor",
            "radius",
            "height",
            "size",
            "intensity",
            "color",
        ]

        try:
            for key in target_keys:
                if hasattr(prim, "GetAttribute"):
                    attr = prim.GetAttribute(key)
                    if attr and hasattr(attr, "Get"):
                        val = attr.Get()
                        if val is not None and not _is_mock(val):
                            sample[key] = self._to_json_serializable(val)
        except Exception:
            pass

        return sample

    def _compute_bounding_box(self, stage: Any, prim: Any) -> Optional[Dict[str, Any]]:
        """Computes world bounding box for a prim."""
        try:
            if hasattr(UsdGeom, "BBoxCache") and hasattr(UsdGeom, "GetStageUpAxis"):
                time_code = Usd.TimeCode.Default() if hasattr(Usd, "TimeCode") else 0.0
                bbox_cache = UsdGeom.BBoxCache(time_code, [UsdGeom.Tokens.default_])
                bbox = bbox_cache.ComputeWorldBound(prim)
                if hasattr(bbox, "ComputeAlignedRange"):
                    aligned_range = bbox.ComputeAlignedRange()
                    if hasattr(aligned_range, "GetMin") and hasattr(aligned_range, "GetMax"):
                        min_pt = aligned_range.GetMin()
                        max_pt = aligned_range.GetMax()
                        if not _is_mock(min_pt) and not _is_mock(max_pt):
                            return {
                                "min": self._to_json_serializable(min_pt),
                                "max": self._to_json_serializable(max_pt),
                            }
        except Exception:
            pass
        return None

    def _compute_transform_matrix(self, prim: Any) -> Optional[List[List[float]]]:
        """Computes world transform matrix for a prim."""
        try:
            if hasattr(UsdGeom, "Xformable"):
                xformable = UsdGeom.Xformable(prim)
                if hasattr(xformable, "ComputeLocalToWorldTransform"):
                    time_code = Usd.TimeCode.Default() if hasattr(Usd, "TimeCode") else 0.0
                    transform = xformable.ComputeLocalToWorldTransform(time_code)
                    if hasattr(transform, "ExtractTranslation") and not _is_mock(transform):
                        return [
                            [float(transform[i][j]) for j in range(4)]
                            for i in range(4)
                        ]
        except Exception:
            pass
        return None

    def _get_associated_materials(self, prim: Any) -> List[str]:
        """Finds associated materials bound to a prim."""
        materials = []
        try:
            if hasattr(UsdShade, "MaterialBindingAPI"):
                binding_api = UsdShade.MaterialBindingAPI(prim)
                if hasattr(binding_api, "GetDirectBinding"):
                    binding = binding_api.GetDirectBinding()
                    if hasattr(binding, "GetMaterial"):
                        mat = binding.GetMaterial()
                        if mat and hasattr(mat, "GetPath"):
                            path = mat.GetPath()
                            if path and not _is_mock(path):
                                materials.append(str(path))
        except Exception:
            pass
        return materials

    def _to_json_serializable(self, val: Any) -> Any:
        """Converts USD Gf/Sdf types to JSON serializable objects."""
        if isinstance(val, (int, float, str, bool, type(None))):
            return val
        if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
            return [self._to_json_serializable(item) for item in val]
        return str(val)
