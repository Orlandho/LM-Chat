# Sentinel Security Journal

This journal records critical security learnings and vulnerability patterns specific to this project.

## 2026-03-30 - NetworkClient URL Validation and CRLF Sanitization
**Vulnerability:** Unsanitized target URLs in `urllib.request` allow local file disclosure (LFI) via `file://` schemes and HTTP header injection via CRLF sequences (`\r`, `\n`).
**Learning:** Python's standard `urllib.request.urlopen` processes non-http schemes and arbitrary headers if URL strings are not explicitly restricted.
**Prevention:** Enforce strict `http://` or `https://` scheme checks and strip CRLF characters from URLs before passing them to `urllib.request.Request`.
