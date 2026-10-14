# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas automatizadas para USD Inspector y Edición Avanzada Reversible (PLAN 2).
Cubre TC-EDT-001 a TC-EDT-004:
- TC-EDT-001: Auditoría de activos y texturas faltantes (Sdf.AssetPath roto).
- TC-EDT-002: Búsqueda avanzada y filtrado de prims por consulta semántica.
- TC-EDT-003: Inspección de Layer Stack y detección de cambios no guardados (isDirty).
- TC-EDT-004: Mutaciones avanzadas y protección de prims del sistema con Command Pattern.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
import omni.usd
import omni.kit.commands
import omni.kit.undo
from logic.usd_inspector import USDInspector
from logic.usd_controller import USDController
from core.policies import SpatialSecurityPolicy


class TestUSDInspectorAndEditing:
    """Suite de pruebas para diagnóstico de escena y edición no destructiva (TC-EDT-001 a TC-EDT-004)."""

    def test_tc_edt_001_audit_missing_assets(self, tmp_path):
        """TC-EDT-001: Detecta activos y texturas referenciadas inexistentes en disco."""
        inspector = USDInspector()

        # Crear archivo temporal existente y una ruta inexistente
        existing_file = tmp_path / "diffuse.png"
        existing_file.write_text("fake image content")
        missing_file = tmp_path / "missing_normal.png"

        # Mock de atributos de prims con Sdf.AssetPath
        class MockAssetPath:
            def __init__(self, path):
                self.path = str(path)
                self.resolvedPath = str(path) if os.path.exists(path) else ""

        class MockAttr:
            def __init__(self, name, asset_path):
                self._name = name
                self._val = MockAssetPath(asset_path)

            def GetName(self):
                return self._name

            def GetTypeName(self):
                return "Asset"

            def Get(self):
                return self._val

        class MockPrim:
            def __init__(self, path, attrs):
                self._path = path
                self._attrs = attrs

            def GetPath(self):
                return self._path

            def IsValid(self):
                return True

            def GetAttributes(self):
                return self._attrs

        prim_valid = MockPrim("/World/Cube", [MockAttr("inputs:diffuseTexture", str(existing_file))])
        prim_missing = MockPrim("/World/MeshWithBrokenTex", [MockAttr("inputs:normalTexture", str(missing_file))])

        mock_stage = MagicMock()
        mock_stage.Traverse.return_value = [prim_valid, prim_missing]

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            missing = inspector.audit_missing_assets()

            assert len(missing) == 1
            assert missing[0]["prim_path"] == "/World/MeshWithBrokenTex"
            assert missing[0]["attribute"] == "inputs:normalTexture"
            assert missing[0]["raw_path"] == str(missing_file)
            assert missing[0]["is_missing"] is True

    def test_tc_edt_002_find_prims_by_query(self):
        """TC-EDT-002: Búsqueda y filtrado semántico de prims por tipo, nombre y visibilidad."""
        inspector = USDInspector()

        class MockQueryPrim:
            def __init__(self, path, prim_type, visibility="inherited", attrs=None):
                self._path = path
                self._type = prim_type
                self._visibility = visibility
                self._attrs = attrs or {}

            def GetPath(self):
                return self._path

            def GetTypeName(self):
                return self._type

            def IsValid(self):
                return True

            def HasAttribute(self, name):
                return name in self._attrs or name == "visibility"

            def GetAttribute(self, name):
                if name == "visibility":
                    m = MagicMock()
                    m.Get.return_value = self._visibility
                    return m
                if name in self._attrs:
                    m = MagicMock()
                    m.Get.return_value = self._attrs[name]
                    return m
                return None

        prims = [
            MockQueryPrim("/World/Geometry/Mesh1", "Mesh", "inherited"),
            MockQueryPrim("/World/Geometry/Mesh2", "Mesh", "invisible"),
            MockQueryPrim("/World/Lights/Sun", "SphereLight", "inherited", {"intensity": 1000}),
            MockQueryPrim("/World/Camera", "Camera", "inherited"),
        ]

        mock_stage = MagicMock()
        mock_stage.Traverse.return_value = prims

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            # Filtro por tipo
            mesh_paths = inspector.find_prims_by_query({"type": "Mesh"})
            assert len(mesh_paths) == 2
            assert "/World/Geometry/Mesh1" in mesh_paths
            assert "/World/Geometry/Mesh2" in mesh_paths

            # Filtro por visibilidad
            hidden_paths = inspector.find_prims_by_query({"visibility": "invisible"})
            assert hidden_paths == ["/World/Geometry/Mesh2"]

            # Filtro por patrón de nombre regex
            light_paths = inspector.find_prims_by_query({"name_pattern": r"^/World/Lights/.*"})
            assert light_paths == ["/World/Lights/Sun"]

            # Filtro por valor de atributo
            intensity_paths = inspector.find_prims_by_query({"attribute_filter": {"intensity": 1000}})
            assert intensity_paths == ["/World/Lights/Sun"]

    def test_tc_edt_003_get_layer_stack_status(self):
        """TC-EDT-003: Inspecciona el Layer Stack e identifica capas modificadas con cambios sin guardar."""
        inspector = USDInspector()

        mock_root_layer = MagicMock()
        mock_root_layer.identifier = "anon:root.usd"
        mock_root_layer.isDirty = True

        mock_sublayer = MagicMock()
        mock_sublayer.identifier = "anon:sub.usd"
        mock_sublayer.isDirty = False

        mock_stage = MagicMock()
        mock_stage.GetRootLayer.return_value = mock_root_layer
        mock_stage.GetSessionLayer.return_value = None
        mock_stage.GetLayerStack.return_value = [mock_root_layer, mock_sublayer]

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            status = inspector.get_layer_stack_status()

            assert status["root_layer"] == "anon:root.usd"
            assert status["total_layers"] == 2
            assert "anon:root.usd" in status["dirty_layers"]
            assert status["has_unsaved_changes"] is True

    def test_tc_edt_004_advanced_mutations_and_undo(self):
        """TC-EDT-004: Ejecución de transform, material binding, grouping con omni.kit.commands y undo."""
        controller = USDController()

        # Probar transform_prim
        res_trans = controller.transform_prim(
            "/World/Cube",
            translation=(10.0, 0.0, 5.0),
            rotation=(0.0, 45.0, 0.0),
            scale=(2.0, 2.0, 2.0),
        )
        assert res_trans["success"] is True
        omni.kit.commands.execute.assert_any_call(
            "TransformPrimCommand",
            path="/World/Cube",
            translation=(10.0, 0.0, 5.0),
            rotation=(0.0, 45.0, 0.0),
            scale=(2.0, 2.0, 2.0),
        )

        # Probar bind_material
        res_mat = controller.bind_material("/World/Cube", "/World/Materials/Gold")
        assert res_mat["success"] is True
        omni.kit.commands.execute.assert_any_call(
            "BindMaterialCommand",
            prim_path="/World/Cube",
            material_path="/World/Materials/Gold",
        )

        # Probar group_prims
        res_group = controller.group_prims(["/World/Cube", "/World/Sphere"], "/World/PropsGroup")
        assert res_group["success"] is True
        omni.kit.commands.execute.assert_any_call(
            "GroupPrimsCommand",
            prim_paths=["/World/Cube", "/World/Sphere"],
            parent_path="/World/PropsGroup",
        )

        # Probar set_prim_attribute
        res_attr = controller.set_prim_attribute("/World/Light", "intensity", 5000.0)
        assert res_attr["success"] is True
        omni.kit.commands.execute.assert_any_call(
            "ChangePropertyCommand",
            prop_path="/World/Light.intensity",
            value=5000.0,
            prev=None,
        )

        # Probar protección de prim de sistema (/OmniverseKit_Root)
        res_prot = controller.transform_prim("/OmniverseKit_Root/Protected", translation=(0, 0, 0))
        assert res_prot["success"] is False
        assert "protegido por el sistema" in res_prot["error_msg"]

    def test_tc_edt_001_modify_all_lights_in_stage(self):
        """TC-EDT-001 (Plan 2): Modificación de intensidad de todas las luces del Stage sin alterar posición."""
        inspector = USDInspector()
        controller = USDController()

        class MockLightPrim:
            def __init__(self, path):
                self._path = path
                self._type = "DistantLight"

            def GetPath(self):
                return self._path

            def GetTypeName(self):
                return self._type

            def IsValid(self):
                return True

        lights = [MockLightPrim("/World/Lights/Sun"), MockLightPrim("/World/Lights/Fill")]
        mock_stage = MagicMock()
        mock_stage.Traverse.return_value = lights

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            found_lights = inspector.find_prims_by_query({"type": "Light"})
            assert len(found_lights) == 2

            for light_path in found_lights:
                res = controller.set_prim_attribute(light_path, "intensity", 3000.0)
                assert res["success"] is True

            omni.kit.commands.execute.assert_any_call(
                "ChangePropertyCommand",
                prop_path="/World/Lights/Sun.intensity",
                value=3000.0,
                prev=None,
            )
            omni.kit.commands.execute.assert_any_call(
                "ChangePropertyCommand",
                prop_path="/World/Lights/Fill.intensity",
                value=3000.0,
                prev=None,
            )

    def test_tc_edt_002_broken_texture_audit_with_windows_file_uri(self, tmp_path):
        """TC-EDT-002: Valida rutas file:///C:/... en Windows sin falsos positivos para archivos existentes."""
        inspector = USDInspector()
        real_file = tmp_path / "valid_texture.png"
        real_file.write_text("texture data")

        file_uri = f"file:///{str(real_file).replace(os.sep, '/')}"

        class MockAssetPath:
            def __init__(self, path):
                self.path = path
                self.resolvedPath = ""

        class MockAttr:
            def __init__(self, name, val):
                self._name = name
                self._val = MockAssetPath(val)

            def GetName(self):
                return self._name

            def GetTypeName(self):
                return "Asset"

            def Get(self):
                return self._val

        class MockPrim:
            def __init__(self, path, attrs):
                self._path = path
                self._attrs = attrs

            def GetPath(self):
                return self._path

            def IsValid(self):
                return True

            def GetAttributes(self):
                return self._attrs

        prim = MockPrim("/World/Mesh", [MockAttr("inputs:diffuse", file_uri)])
        mock_stage = MagicMock()
        mock_stage.Traverse.return_value = [prim]

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            missing = inspector.audit_missing_assets()
            # El archivo físico existe, por lo que missing debe estar vacío
            assert len(missing) == 0

    def test_tc_edt_003_reorganize_prims_under_furniture_scope(self):
        """TC-EDT-003 (Plan 2): Reorganización de prims sueltos bajo un Scope /World/Furniture."""
        controller = USDController()
        loose_furniture = ["/World/Chair_01", "/World/Table_01", "/World/Lamp_01"]

        res = controller.group_prims(loose_furniture, "/World/Furniture")
        assert res["success"] is True
        assert res["grouped_count"] == 3
        assert res["parent_path"] == "/World/Furniture"
        omni.kit.commands.execute.assert_any_call(
            "GroupPrimsCommand",
            prim_paths=loose_furniture,
            parent_path="/World/Furniture",
        )

    def test_tc_edt_004_mass_edit_undo_compound_block(self):
        """TC-EDT-004 (Plan 2): Deshacer (Ctrl+Z) de edición masiva agrupada en un solo bloque undo."""
        controller = USDController()
        omni.kit.undo.begin.reset_mock()
        omni.kit.undo.end.reset_mock()

        script = """
for i in range(10):
    controller.set_prim_attribute(f'/World/Prop_{i}', 'visibility', 'invisible')
"""
        res = controller.execute_code(script)
        assert res["success"] is True

        # Debe abrir y cerrar exactamente un bloque undo para los 10 cambios
        omni.kit.undo.begin.assert_called_once()
        omni.kit.undo.end.assert_called_once()

    def test_layer_stack_real_usd_is_dirty_and_property_support(self):
        """Verifica que el estado de capas detecte tanto IsDirty() de pxr como propiedad dirty."""
        inspector = USDInspector()

        # Capa estilo C++ USD: método IsDirty()
        layer_method = MagicMock()
        layer_method.identifier = "scene_layer.usd"
        del layer_method.isDirty
        del layer_method.dirty
        layer_method.IsDirty = MagicMock(return_value=True)

        # Capa estilo property: layer.dirty = True
        layer_prop = MagicMock()
        layer_prop.identifier = "sublayer.usd"
        del layer_prop.isDirty
        del layer_prop.IsDirty
        layer_prop.dirty = True

        mock_stage = MagicMock()
        mock_stage.GetRootLayer.return_value = layer_method
        mock_stage.GetSessionLayer.return_value = None
        mock_stage.GetLayerStack.return_value = [layer_method, layer_prop]

        with patch.object(inspector, "_get_stage", return_value=mock_stage):
            status = inspector.get_layer_stack_status()
            assert status["total_layers"] == 2
            assert "scene_layer.usd" in status["dirty_layers"]
            assert "sublayer.usd" in status["dirty_layers"]
            assert status["has_unsaved_changes"] is True
