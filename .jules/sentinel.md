# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-29 - NetworkClient URL Scheme Validation
**Vulnerability:** `urllib.request.urlopen` handles arbitrary schemes such as `file://` or `ftp://` by default, allowing local file inclusion (LFI) and SSRF if unvalidated URLs are passed to `NetworkClient`.
**Learning:** Always validate that incoming network request URLs explicitly use `http://` or `https://` schemes before initializing `urllib.request.Request`.
**Prevention:** Implement a central `_validate_url` check in any client component interacting with `urllib` or external endpoints.
