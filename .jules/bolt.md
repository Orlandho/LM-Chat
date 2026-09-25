## 2026-03-30 - Compact USD Context JSON Serialization & Prim Traversal

**Learning:** OpenUSD stage hierarchy context serialization can involve thousands of prims in complex Omniverse scenes. Indented and sorted JSON serialization (`indent=2, sort_keys=True`) creates substantial CPU overhead and inflates LLM context payload sizes by ~40%. Furthermore, per-prim attribute loops that re-check `hasattr(prim, "GetAttribute")` inside the loop incur thousands of redundant attribute lookups during stage traversal.

**Action:** Always serialize stage context using compact `json.dumps()` without `indent=2`, and hoist `hasattr(prim, "GetAttribute")` checks outside of attribute iterations over pre-defined tuple constants.

## 2026-03-30 - Concurrent MCP Tool Discovery & StreamReader EOF Handling

**Learning:** Querying multiple stdio Model Context Protocol (MCP) servers sequentially in a loop blocks tool catalog discovery with cumulative network/IPC latency ($O(N \cdot T)$). In addition, checking `if not line: await asyncio.sleep(0.01)` on an `asyncio.StreamReader` causes infinite 10ms timer spin when process stdout closes (`b''` EOF).

**Action:** Use `asyncio.gather()` to fetch tool schemas across all registered MCP servers concurrently ($O(\max(T))$), and always `break` immediately on `b''` EOF when reading subprocess streams.
