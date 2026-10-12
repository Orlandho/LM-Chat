# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Session Import Path Traversal & Type Validation
**Vulnerability:** Untrusted JSON imports in `LocalChatHistoryManager` allowed un-sanitized `session_id` fields containing path traversal sequences (e.g. `../../../`) or non-string types.
**Learning:** Checking file existence prior to sanitization or using raw session IDs in JSON parsing bypasses confinement checks in `_get_session_path`.
**Prevention:** Always run user-supplied/imported session IDs through `_sanitize_session_id` before constructing file paths or performing session lookups.
