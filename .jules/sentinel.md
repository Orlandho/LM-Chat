# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-31 - Unvalidated URL Schemes in urllib Network Clients
**Vulnerability:** `NetworkClient` used `urllib.request.urlopen` without scheme validation, allowing potential SSRF and Local File Read via `file://` or non-HTTP URLs.
**Learning:** Python's standard `urllib.request` natively handles non-network schemes (e.g., `file://`), making any raw `urllib.request.urlopen` call vulnerable to local resource access unless explicitly restricted.
**Prevention:** Always validate that incoming URLs start with `http://` or `https://` before passing them to `urllib.request.urlopen` or other network transport clients.
