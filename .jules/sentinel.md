# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Dynamic USD Execution Context Scoping
**Vulnerability:** Unscoped execution environment in dynamic `exec()` calls for dynamic Python code execution.
**Learning:** When executing dynamic OpenUSD Python code in `USDController.execute_code`, omitting explicit `__builtins__` in `exec_globals` allowed code execution without explicitly bounded global scopes.
**Prevention:** Always explicitly set `"__builtins__": __builtins__` in the execution dictionary for `exec()` and scope exposed global modules tightly to required Omniverse SDK modules (`omni`, `pxr`, `Usd`, `UsdGeom`, `Gf`).

## 2026-03-31 - Permissive Credentials Store Permissions
**Vulnerability:** Default world-readable permissions (`0644`) on `settings.json` and config directory stored API keys insecurely on multi-user systems.
**Learning:** `SettingsManager.save()` written using standard `open()` created files under system umask, allowing other unprivileged local users to read plaintext API credentials stored in `~/.omni_lm_chat/settings.json`.
**Prevention:** Always enforce explicit owner-only file permissions (`0o600`) and directory permissions (`0o700`) when persisting sensitive credentials or secrets to disk using `os.open` with mode flags or `os.chmod`.
