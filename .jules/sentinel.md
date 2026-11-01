# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-04-01 - Sensitive Credential Storage POSIX Permissions
**Vulnerability:** Default umask permissions when saving configuration files containing API keys and server tokens allowed group- and world-read access on local disks.
**Learning:** `SettingsManager.save()` relied on standard `open(..., "w")` and `os.makedirs()` without permission flags, persisting plaintext API keys in world-readable files (`0o664`/`0o644`) on multi-user systems.
**Prevention:** When saving configuration files containing credentials or tokens, enforce restrictive permissions (`0o700` for directory and `0o600` via `os.open` with flags and `os.chmod`) to prevent local information leakage.
