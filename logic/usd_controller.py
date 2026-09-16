# -*- coding: utf-8 -*-

import omni.ext
import pxr
from pxr import Usd, UsdGeom, Gf

class USDController:
    """Handles execution of dynamic USD python code."""

    # Maximum payload limit (100KB) to prevent DoS via memory/CPU exhaustion
    MAX_CODE_SIZE: int = 100_000

    def execute_code(self, python_code: str) -> dict:
        """
        Dynamically executes extracted python code within the Omniverse context.

        Args:
            python_code (str): The code block to execute.

        Returns:
            dict: Structured response indicating success or failure.
        """
        # Security: Input validation to prevent non-string or empty code execution
        if not isinstance(python_code, str) or not python_code.strip():
            return {"success": False, "error_msg": "Input validation error: Code payload must be a non-empty string."}

        # Security: DoS prevention by restricting maximum code size length
        if len(python_code) > self.MAX_CODE_SIZE:
            return {
                "success": False,
                "error_msg": f"Security limit exceeded: Code payload length exceeds maximum allowed limit of {self.MAX_CODE_SIZE} characters."
            }

        # Prepare execution environment
        exec_globals = {
            "omni": __import__('omni'),
            "pxr": pxr,
            "Usd": Usd,
            "UsdGeom": UsdGeom,
            "Gf": Gf
        }

        try:
            exec(python_code, exec_globals)
            return {"success": True}
        except Exception as exec_err:
            return {"success": False, "error_msg": str(exec_err)}
