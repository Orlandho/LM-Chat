# -*- coding: utf-8 -*-

"""
Unit tests for logic.usd_controller.USDController.
Verifies code execution, input validation, DoS limits, and error handling.
"""

import pytest
from unittest.mock import patch
import omni.kit.undo
import omni.kit.commands
from core.interfaces import IUSDController
from logic.usd_controller import USDController


class TestUSDController:
    """Tests for USDController class."""

    def test_execute_code_success(self):
        """Test executing valid Python code."""
        controller = USDController()
        code = "result = 2 + 2"
        res = controller.execute_code(code)
        assert res["success"] is True

    def test_execute_code_invalid_type(self):
        """Test input validation for non-string inputs."""
        controller = USDController()
        res = controller.execute_code(12345)
        assert res["success"] is False
        assert "Input validation error" in res["error_msg"]

    def test_execute_code_empty_string(self):
        """Test input validation for empty or whitespace-only code."""
        controller = USDController()
        res = controller.execute_code("   ")
        assert res["success"] is False
        assert "Input validation error" in res["error_msg"]

    def test_execute_code_exceeds_max_size(self):
        """Test DoS payload length restriction."""
        controller = USDController()
        oversized_code = "# test\n" + ("x = 1\n" * 20_000)
        assert len(oversized_code) > controller.MAX_CODE_SIZE
        res = controller.execute_code(oversized_code)
        assert res["success"] is False
        assert "Security limit exceeded" in res["error_msg"]

    def test_execute_code_runtime_error(self):
        """Test handling of runtime syntax or execution errors."""
        controller = USDController()
        bad_code = "raise ValueError('Custom USD execution error')"
        res = controller.execute_code(bad_code)
        assert res["success"] is False
        assert "Custom USD execution error" in res["error_msg"]

    def test_execute_code_restricted_globals(self):
        """Test that execution environment has explicit builtins and isolated scope."""
        controller = USDController()
        # Verify that builtins like len work, but undeclared outer variables raise NameError
        code = "val = len([1, 2, 3])"
        res = controller.execute_code(code)
        assert res["success"] is True

        code_undefined = "x = outer_undefined_var"
        res_undefined = controller.execute_code(code_undefined)
        assert res_undefined["success"] is False
        assert "is not defined" in res_undefined["error_msg"]

    def test_controller_implements_iusdcontroller_interface(self):
        """Verifies USDController is a proper instance of IUSDController."""
        controller = USDController()
        assert isinstance(controller, IUSDController)

    def test_strict_kit_undo_double_rejects_begin_and_end(self):
        """Verifies that accessing nonexistent begin/end raises AttributeError as per Kit 107.3.7."""
        assert hasattr(omni.kit.undo, "begin") is False
        assert hasattr(omni.kit.undo, "end") is False
        assert hasattr(omni.kit.undo, "begin_group") is True
        assert hasattr(omni.kit.undo, "end_group") is True
        assert hasattr(omni.kit.undo, "group") is True

        with pytest.raises(AttributeError, match="has no attribute 'begin'"):
            _ = omni.kit.undo.begin

        with pytest.raises(AttributeError, match="has no attribute 'end'"):
            _ = omni.kit.undo.end

        with pytest.raises(AttributeError, match="has no attribute 'fake_attr'"):
            _ = omni.kit.undo.fake_attr

    def test_execute_code_invokes_begin_group_and_end_group(self):
        """Verifies execute_code wraps execution in begin_group and end_group."""
        controller = USDController()
        omni.kit.undo.begin_group.reset_mock()
        omni.kit.undo.end_group.reset_mock()

        res = controller.execute_code("answer = 42")
        assert res["success"] is True

        omni.kit.undo.begin_group.assert_called_once()
        omni.kit.undo.end_group.assert_called_once()

    def test_execute_code_atomic_rollback_on_partial_failure(self):
        """Verifies that an exception during execution triggers end_group and omni.kit.undo.undo()."""
        controller = USDController()
        omni.kit.undo.begin_group.reset_mock()
        omni.kit.undo.end_group.reset_mock()
        omni.kit.undo.undo.reset_mock()

        failing_code = """
controller.create_prim('Cube', '/World/Cube1')
raise RuntimeError('Stage mutation crashed halfway')
"""
        res = controller.execute_code(failing_code)
        assert res["success"] is False
        assert "Stage mutation crashed halfway" in res["error_msg"]
        assert res.get("partial_changes_rolled_back") is True

        omni.kit.undo.begin_group.assert_called_once()
        omni.kit.undo.end_group.assert_called_once()
        omni.kit.undo.undo.assert_called_once()

    def test_create_prim_command_reversibility(self):
        """Verifies create_prim executes CreatePrimWithDefaultXform command."""
        controller = USDController()
        omni.kit.commands.execute.reset_mock()

        res = controller.create_prim("Cube", "/World/ReversibleCube", attributes={"size": 2.0})
        assert res["success"] is True
        assert res["prim_path"] == "/World/ReversibleCube"
        assert res["prim_type"] == "Cube"

        omni.kit.commands.execute.assert_called_with(
            "CreatePrimWithDefaultXform",
            prim_type="Cube",
            prim_path="/World/ReversibleCube",
            attributes={"size": 2.0},
        )

    def test_create_prim_rejects_protected_path(self):
        """Verifies create_prim prevents creating prims under protected paths like /Render."""
        controller = USDController()
        res = controller.create_prim("Cube", "/Render/UnauthorizedCube")
        assert res["success"] is False
        assert "está protegido por el sistema" in res["error_msg"]

    def test_commands_handle_execution_failure(self):
        """Verifies commands handle failure tuple from omni.kit.commands.execute gracefully."""
        controller = USDController()

        with patch.object(omni.kit.commands, "execute", return_value=(False, "Failed in Kit")):
            res_create = controller.create_prim("Sphere", "/World/Sphere")
            assert res_create["success"] is False
            assert "Failed in Kit" in res_create["error_msg"]

            res_trans = controller.transform_prim("/World/Sphere", translation=[0, 10, 0])
            assert res_trans["success"] is False
            assert "Error ejecutando TransformPrimCommand" in res_trans["error_msg"]

            res_mat = controller.bind_material("/World/Sphere", "/World/Mat")
            assert res_mat["success"] is False
            assert "Error ejecutando BindMaterialCommand" in res_mat["error_msg"]

            res_grp = controller.group_prims(["/World/Sphere"], "/World/Group")
            assert res_grp["success"] is False
            assert "Error ejecutando GroupPrimsCommand" in res_grp["error_msg"]

            res_attr = controller.set_prim_attribute("/World/Sphere", "visibility", "invisible")
            assert res_attr["success"] is False
            assert "Error ejecutando ChangePropertyCommand" in res_attr["error_msg"]
