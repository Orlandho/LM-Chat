# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-31 - Overly Permissive Credentials Storage in SettingsManager
**Vulnerability:** Persistent settings file containing API keys and provider authentication tokens was created with default umask permissions (e.g. 0o664/0o644), leaving secrets readable by other local users on shared multi-user workstations or shared Kit nodes.
**Learning:** Standard Python `open(path, "w")` and `os.makedirs(path)` inherit system default umasks, resulting in world/group readable permissions on disk for files storing sensitive authentication secrets.
**Prevention:** Enforce restrictive permissions (`0o700` for directory via `os.makedirs(mode=0o700)` and `0o600` for files via `os.open` with `O_WRONLY | O_CREAT | O_TRUNC`) during atomic persistence of configuration files containing credentials.
