# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-10-03 - Path Traversal & Type Pollution in Chat Session Imports
**Vulnerability:** `import_session_json` accepted raw `session_id` fields from JSON payloads without verifying type or applying strict sanitization before setting `session.session_id`, allowing path traversal sequences or non-string types to persist into saved sessions and memory.
**Learning:** Checking for file existence before sanitizing input allowed path traversal strings to bypass duplicate checks when the target path did not exist. Non-string inputs also caused `TypeError` in regex sanitization.
**Prevention:** Always validate data types (e.g. `isinstance(raw_id, str)`) and sanitize raw inputs *before* performing database or filesystem existence lookups.
