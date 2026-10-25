# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-30 - AST Policy Bypass via getattr Dynamic Attribute Retrieval
**Vulnerability:** Static AST inspection checking `ast.Attribute` nodes for dangerous OS functions (such as `os.system` or `os.remove`) could be bypassed using `getattr(os, 'system')`.
**Learning:** Relying solely on `ast.Attribute` checks in AST analysis allowed dynamic attribute resolution via built-in function calls to escape policy enforcement.
**Prevention:** Inspect `ast.Call` nodes where `func` is `getattr` and validate that string literal arguments do not reference forbidden attributes or dangerous operations.
