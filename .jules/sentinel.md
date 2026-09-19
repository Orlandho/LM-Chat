## 2026-03-31 - URL Scheme Validation for LLM Provider Endpoints
**Vulnerability:** Unvalidated base URL schemes in `InferenceRouter` allowed potential SSRF / protocol manipulation via non-HTTP schemes (e.g. `file://`, `gopher://`).
**Learning:** External or custom provider URLs passed to LLM routers must be strictly constrained to `http://` and `https://` protocols before initializing `aiohttp.ClientSession` requests.
**Prevention:** Validate URL schemes explicitly when setting endpoint base URLs and raise `ValueError` for unsupported or insecure protocols.
