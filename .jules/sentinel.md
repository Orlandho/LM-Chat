# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-04-01 - Sensitive Credential Persistence File Permissions
**Vulnerability:** World/group-readable file permissions on serialized settings files containing API keys and provider credentials.
**Learning:** Persisting settings using standard `open()` and `os.makedirs()` inherits system umask defaults, which commonly creates files with `0o644` or `0o664` permissions, exposing plaintext API keys (e.g. OpenAI, Anthropic, NVIDIA Spark) to other local processes on shared or multi-user workstations.
**Prevention:** Always use `os.open(temp_path, flags, 0o600)` and `os.makedirs(config_dir, mode=0o700, exist_ok=True)` combined with `os.chmod()` to guarantee strict `0o600` file permissions and `0o700` directory permissions when storing secrets on disk.
