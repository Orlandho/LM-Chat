# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-04-03 - Restricted Builtins in Dynamic Code Execution Environment
**Vulnerability:** Passing full `__builtins__` into `exec_globals` in dynamic Python execution (`USDController.execute_code`) allowed access to sensitive built-in functions like `open` and `eval` if AST checks were bypassed.
**Learning:** Providing unfiltered `__builtins__` to `exec()` gives runtime access to file system operations and dynamic execution builtins.
**Prevention:** Always copy and strip forbidden builtin functions (`eval`, `exec`, `compile`, `__import__`, `breakpoint`, `open`) from `__builtins__` before passing it to `exec_globals`.
