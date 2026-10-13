# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - Enforce Strict Storage Permissions & Session ID Sanitization
**Vulnerability:** Local chat session files stored prompt/response history without restricting permissions (0o600/0o700), exposing sensitive chat data to other local users, and session imports allowed arbitrary `session_id` strings prior to serialization.
**Learning:** Default atomic file creation with standard `open()` in Python inherits umask (usually 0644/0666), making local session stores readable on shared systems. Additionally, `ChatSession.from_dict()` accepts raw session IDs which must be re-sanitized on import before file persistence.
**Prevention:** Use `os.open()` with `os.O_CREAT | os.O_WRONLY` and mode `0o600` for sensitive file creation, `os.chmod` for POSIX permissions on directories (`0o700`), and pass untrusted session IDs through `_sanitize_session_id()` on import.
