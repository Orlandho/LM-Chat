# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-29 - Path Traversal Prevention in Persistent Chat Sessions
**Vulnerability:** Chat session IDs imported from untrusted JSON or constructed externally could contain relative path traversal sequences (`../../`), causing file operations to target files outside the session directory or contaminate session object state.
**Learning:** `_sanitize_session_id` was previously called when constructing file paths in `LocalChatHistoryManager`, but `ChatSession` objects and `save_session`/`import_session_json` retain raw `session_id` strings, causing exported/imported JSON and stored `session.session_id` attributes to remain unsanitized.
**Prevention:** Sanitize `session_id` using regex `[^a-zA-Z0-9_\-]` directly within `ChatSession.from_dict` and during `LocalChatHistoryManager` import/save methods.
