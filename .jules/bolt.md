## 2026-03-30 - Compact USD Context JSON Serialization & Prim Traversal

**Learning:** OpenUSD stage hierarchy context serialization can involve thousands of prims in complex Omniverse scenes. Indented and sorted JSON serialization (`indent=2, sort_keys=True`) creates substantial CPU overhead and inflates LLM context payload sizes by ~40%. Furthermore, per-prim attribute loops that re-check `hasattr(prim, "GetAttribute")` inside the loop incur thousands of redundant attribute lookups during stage traversal.

**Action:** Always serialize stage context using compact `json.dumps()` without `indent=2`, and hoist `hasattr(prim, "GetAttribute")` checks outside of attribute iterations over pre-defined tuple constants.
