# -*- coding: utf-8 -*-

"""
Unit tests for logic.usd_controller.USDController.
Verifies code execution, input validation, DoS limits, and error handling.
"""

import pytest
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

    def test_execute_code_restricted_builtins_removed(self):
        """Test that dangerous builtins like eval and open are not accessible in execution scope."""
        controller = USDController()
        code_eval = "x = eval('1 + 1')"
        res_eval = controller.execute_code(code_eval)
        assert res_eval["success"] is False
        assert "forbidden builtin function 'eval()'" in res_eval["error_msg"]

        code_open = "f = open('/etc/passwd', 'r')"
        res_open = controller.execute_code(code_open)
        assert res_open["success"] is False
        assert "name 'open' is not defined" in res_open["error_msg"]
