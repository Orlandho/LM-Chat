# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-31 - Permissive File Permissions on Credentials Config
**Vulnerability:** Standard `open()` during JSON configuration save wrote API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) with default umask permissions (`0o644`), leaving plaintext credentials world/group-readable on local filesystems.
**Learning:** Default file creation methods in Python inherit process umask without restricting access modes for sensitive credential files.
**Prevention:** Use `os.open` with creation flags and mode `0o600` (and `os.chmod`) when saving files containing secret keys or auth tokens to guarantee owner-only read/write access.
