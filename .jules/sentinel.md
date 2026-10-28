# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-30 - AST Guardrail Bypass via Attribute Access
**Vulnerability:** AST static analysis for forbidden builtins was bypassed by attribute invocation like `__builtins__.eval(...)` or `builtins.exec(...)`.
**Learning:** AST inspection that only checks `ast.Name` nodes missed `ast.Attribute` function calls, allowing forbidden builtin functions to be called through module/object attribute access.
**Prevention:** When inspecting `ast.Call` nodes in static analysis, always validate attribute access (`node.func.attr`) against `forbidden_builtins` in addition to checking `node.func.id` on `ast.Name` nodes.
