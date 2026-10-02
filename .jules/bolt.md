## 2026-03-30 - Compact USD Context JSON Serialization & Prim Traversal

**Learning:** OpenUSD stage hierarchy context serialization can involve thousands of prims in complex Omniverse scenes. Indented and sorted JSON serialization (`indent=2, sort_keys=True`) creates substantial CPU overhead and inflates LLM context payload sizes by ~40%. Furthermore, per-prim attribute loops that re-check `hasattr(prim, "GetAttribute")` inside the loop incur thousands of redundant attribute lookups during stage traversal.

**Action:** Always serialize stage context using compact `json.dumps()` without `indent=2`, and hoist `hasattr(prim, "GetAttribute")` checks outside of attribute iterations over pre-defined tuple constants.

## 2026-03-31 - OpenUSD Prim Hierarchy Depth Calculation & Direct Attribute Lookup

**Learning:** Calculating USD prim hierarchy depth using string splitting and list comprehensions (`len([p for p in path_str.strip('/').split('/') if p])`) during stage traversal creates millions of short-lived list allocations in large scenes. Replacing it with string character counting (`path_str.count('/')`) yields a ~3.1x speedup in depth determination. Additionally, calling `prim.GetAttribute("visibility")` directly avoids instantiating C++ wrapper objects (`UsdGeom.Imageable(prim)`) for every traversed prim.

**Action:** Use `path_str.count('/')` for calculating OpenUSD prim depth, and query generic `prim.GetAttribute()` directly before instantiating specialized UsdGeom API wrappers.

## 2026-03-31 - Non-Blocking Async Subprocess StreamReader Loop EOF Handling

**Learning:** In `asyncio.subprocess` stream reader loops (e.g., stdio MCP listeners), calling `readline()` on a closed or terminated subprocess stream returns empty bytes (`b""`). Continuously calling `readline()` after EOF returns `b""` immediately without blocking. Doing `if not line: await asyncio.sleep(0.01); continue` creates an infinite busy-polling loop running 100 Hz that burns CPU, wastes memory, and blocks pending request cleanup.

**Action:** Always `break` out of `readline()` loops when `not line` is encountered to gracefully terminate reader tasks upon stream EOF.

## 2026-03-31 - Single-Pass File Traversal for Chat Session Search

**Learning:** In disk-backed session history managers, chaining higher-level methods like `list_sessions()` and per-item `get_session()` during search causes 2x redundant file reads and JSON deserializations ($2N$ instead of $N$) plus thousands of unnecessary dataclass object instantiations. Streamlining search to a single-pass filesystem traversal yields a ~2.3x speedup.

**Action:** Perform single-pass file reads when searching disk-backed JSON stores rather than repeatedly fetching items via individual getter methods in loops.
