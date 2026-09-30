## 2026-03-30 - Compact USD Context JSON Serialization & Prim Traversal

**Learning:** OpenUSD stage hierarchy context serialization can involve thousands of prims in complex Omniverse scenes. Indented and sorted JSON serialization (`indent=2, sort_keys=True`) creates substantial CPU overhead and inflates LLM context payload sizes by ~40%. Furthermore, per-prim attribute loops that re-check `hasattr(prim, "GetAttribute")` inside the loop incur thousands of redundant attribute lookups during stage traversal.

**Action:** Always serialize stage context using compact `json.dumps()` without `indent=2`, and hoist `hasattr(prim, "GetAttribute")` checks outside of attribute iterations over pre-defined tuple constants.

## 2026-03-30 - Debounced Async Scroll Tasks During High-Frequency Token Streaming

**Learning:** In NVIDIA Omniverse Kit SDK UI extensions running on the 60 FPS rendering thread, high-frequency LLM response streaming invokes UI updates and `_scroll_to_bottom()` up to 200 times per second. Launching an unthrottled `asyncio` coroutine task (`asyncio.create_task(...)`) for every chunk creates heavy event loop task churn and CPU contention.

**Action:** Debounce UI scroll task creation during rapid streaming using a `_scroll_task_pending` flag that suppresses redundant asyncio task creation while a scroll task is already sleeping or scheduled.
