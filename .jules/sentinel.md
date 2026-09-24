# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Defensive Input Validation for MCP Client Registry
**Vulnerability:** Unvalidated inputs in `register_server` and `call_tool` could lead to attempts to spawn empty or non-string subprocess commands, or send malformed JSON-RPC payloads.
**Learning:** MCP server connections rely on external system command execution (`asyncio.create_subprocess_exec`). Lacking input validation at the entrypoint risks process crash exceptions and invalid execution states.
**Prevention:** Always enforce strict type checks and non-empty string validations on server names, commands, and arguments before invoking subprocesses or formatting protocol requests.
