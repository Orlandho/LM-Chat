# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Restrictive File Permissions for Credentials and Settings Persistence
**Vulnerability:** Overly permissive POSIX file and directory permissions when persisting sensitive API keys and provider credentials to disk (`settings.json`).
**Learning:** Standard `open(path, 'w')` and `os.makedirs(path)` inherit system umask, creating world-readable files or directories (`0o644`/`0o755`) that expose cloud API keys to other local users or compromised processes on shared workstations.
**Prevention:** Always enforce `mode=0o700` when creating directories for credentials and create temporary/destination files using `os.open(path, flags, 0o600)` with `os.fsync()` prior to atomic renaming.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).
