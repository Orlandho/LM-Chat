# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - NetworkClient SSRF / Protocol Manipulation Prevention
**Vulnerability:** Python's `urllib.request.urlopen` supports arbitrary URL schemes by default (such as `file://` or `ftp://`), allowing potential SSRF or Local File Inclusion if user-influenced URLs are passed directly without scheme validation.
**Learning:** Even when network clients are designed for HTTP/HTTPS endpoints, native Python `urllib` handles non-HTTP schemes unless explicitly restricted before creating requests.
**Prevention:** Always validate that incoming URLs explicitly begin with `http://` or `https://` before passing them to `urllib.request.Request` or `urllib.request.urlopen`.
