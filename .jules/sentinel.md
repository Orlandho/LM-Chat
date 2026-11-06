# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-30 - Restrictive Permissions for Persisted Settings Containing API Keys
**Vulnerability:** Storing LLM configuration and API keys with default umask permissions in local filesystem.
**Learning:** `SettingsManager.save()` created files using standard `open()`, making saved configuration files world-readable/group-readable depending on the host umask and exposing sensitive cloud API keys.
**Prevention:** Always use `os.open` with `0o600` flags and `os.chmod(..., 0o600)` when writing configuration files containing credentials, and create parent directories with `mode=0o700`.
