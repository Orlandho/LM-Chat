# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-31 - URL Scheme Validation in Network Utilities
**Vulnerability:** `urllib.request` in `NetworkClient` allowed non-HTTP schemes (e.g. `file://`, `ftp://`), exposing the system to local file inclusion (LFI) and Server-Side Request Forgery (SSRF).
**Learning:** `InferenceRouter` had scheme checks (`http://`, `https://`), but `NetworkClient` was missing similar validation, creating an architectural gap between network utility layers.
**Prevention:** Always enforce strict `http://` and `https://` scheme checks and CRLF sanitization on input URLs in low-level network handlers before delegating to `urllib`.
