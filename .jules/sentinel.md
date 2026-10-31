# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-10-31 - Sensitive Credentials Storage Permissions
**Vulnerability:** Overly permissive default file and directory permissions on persistent settings storing LLM API keys and credentials.
**Learning:** `SettingsManager.save()` created the configuration directory and file via standard `open()` without specifying restrictive file mode flags, relying on ambient system umask which often allows group or world read access (e.g., 0o644 / 0o755) in shared workstation or multi-tenant Omniverse environments.
**Prevention:** Explicitly create configuration directories with `mode=0o700` and use `os.open(path, flags, 0o600)` with atomic replacement for files that store sensitive secrets and credentials.
