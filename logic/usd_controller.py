# -*- coding: utf-8 -*-

try:
    import omni.ext
    import pxr
    from pxr import Usd, UsdGeom, Gf
except ImportError:
    omni = None
    pxr = None
    Usd = None
    UsdGeom = None
    Gf = None

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

        # Prepare execution environment with restricted builtins for sandbox defense-in-depth
        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "getattr": getattr,
            "hasattr": hasattr,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "print": print,
            "range": range,
            "repr": repr,
            "set": set,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "RuntimeError": RuntimeError,
            "AttributeError": AttributeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "True": True,
            "False": False,
            "None": None,
        }

        exec_globals = {
            "__builtins__": safe_builtins,
            "omni": __import__('omni') if omni is not None else None,
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
