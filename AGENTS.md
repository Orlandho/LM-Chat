# 🤖 Universal Charter for AI & Human Collaboration (AGENTS.md)
**Project: LM-Chat™ — Autonomous Spatial AI Copilot for NVIDIA Omniverse**

This document establishes the universal development laws, architectural invariants, code quality standards, and automated release protocols for **all contributors**—whether autonomous AI coding agents (Antigravity, Jules, Claude Code, Codex, Devin, Aider), AI-assisted IDEs (Cursor, GitHub Copilot), or human software engineers.

---

## 🌟 1. Core Mission & Technical Identity

- **Commercial Brand:** `LM-Chat™`
- **NVIDIA Omniverse Extension ID:** `omni.lm_chat`
- **Target Runtime:** NVIDIA Omniverse Kit SDK 105 / 106 / 107+ (USD Composer, Isaac Sim, Omniverse Code)
- **Primary Interface:** Native `omni.ui` dockable chat window (GUI).
- **Secondary Interface:** Headless/REPL Terminal CLI (`cli/lmchat_cli.py`).
- **Philosophy:** *"Mejor que sobre a que falte"* — We prioritize depth, maximum cognitive reasoning, and bulletproof engineering over hasty, incomplete shortcuts.

---

## 🏛️ 2. Omniverse Architectural Invariants (Non-Negotiable)

Any contribution, fork, or variant of this codebase MUST comply with the following architectural invariants:

### 2.1. Non-Destructive USD Mutations (Command Pattern)
- **Hard Rule:** Never mutate the `pxr.Usd` Stage directly via destructive writes that bypass Omniverse history.
- **Implementation:** All prim creation, transformation, shading, or physics operations must be executed via `omni.kit.commands.execute()` or wrapped in reversible undo blocks. Native `Ctrl+Z` / `Ctrl+Y` support must always remain intact.

### 2.2. Sacred 60 FPS Async Execution Loop
- **Hard Rule:** Heavy computation, network I/O, or LLM token streaming must **NEVER** block the Omniverse main rendering thread.
- **Implementation:** Utilize `asyncio.run_in_executor()` or native asynchronous streams (`async for`). Any dropped UI frame caused by synchronous blocking is treated as a critical architectural defect.

### 2.3. ReAct Self-Healing & Traceback Reflection
- **Hard Rule:** When AI-generated Python or OpenUSD code fails during execution, the system must not crash or leave the user stranded.
- **Implementation:** Intercept exceptions (`sys.exc_info()`, `Sdf.PathError`, `Tf.DiagnosticMark`), package the traceback into an internal reflection prompt, and re-query the model for autonomous self-correction (up to 3 retries).

### 2.4. Contract-First Modular Decomposition (Swarm & Jules Ready)
- **Hard Rule:** All major features must define typed interface contracts in `core/interfaces.py` before writing concrete logic.
- **Purpose:** Enables concurrent, parallel development by autonomous swarms (e.g. multiple concurrent Jules instances) on separate branches with zero merge conflicts.

---

## 📦 3. Versioning, SemVer 2.0.0 & Release Pipeline

We enforce an automated, deterministic, and free release lifecycle powered by **Semantic Versioning (SemVer 2.0.0)** and **Commitizen**:

### 3.1. Conventional Commits Format
Every git commit message MUST strictly adhere to the Conventional Commits specification:
```
<type>(<scope>): <short summary in imperative mood>

[optional body explaining rationale]
```
Allowed types:
- `feat:` New user-facing feature or capability (Triggers **Minor** version bump: `1.0.0` -> `1.1.0`).
- `fix:` Bug fix or error resolution (Triggers **Patch** version bump: `1.0.0` -> `1.0.1`).
- `refactor:` Code restructuring without changing behavior or adding features.
- `docs:` Documentation updates, branding specifications, changelogs.
- `test:` Adding or updating unit tests and mocks.
- `chore:` Maintenance, dependency updates, CI/CD workflows.
- `BREAKING CHANGE:` Incompatible architectural change (Triggers **Major** version bump: `1.0.0` -> `2.0.0`).

### 3.2. Strict Multi-File Version Synchronization
The software version MUST remain 100% identical across all target files:
1. `config/extension.toml` (`version = "X.Y.Z"`)
2. `__init__.py` (`__version__ = "X.Y.Z"`)
3. `CITATION.cff` (`version: X.Y.Z` and `date-released: YYYY-MM-DD`)
4. `pyproject.toml` (`version = "X.Y.Z"`)
5. `docs/CHANGELOG.md` (Structured according to *Keep a Changelog*)

> ⚠️ **Sanity Check Rule:** Never edit version numbers manually in only one file. Always run `python scripts/release.py [patch|minor|major] --dry-run` to verify synchronization across all files before cutting a release.

### 3.3. Automated Packaging for NVIDIA Omniverse
In `.github/workflows/release.yml`, releases automatically build a zip archive where the top-level directory is strictly named `omni.lm_chat/`. Never use dynamic repository names or versions in the root folder, as NVIDIA Omniverse Kit requires exact directory matching for its Extension Manager.

---

## 🧪 4. Testing, Mocks & CI/CD Invariants

- **100% Passing Tests Required:** No Pull Request shall be merged if any test fails in the suite (`python -m pytest tests/ -v`).
- **Engine-Independent Mocks:** All tests must run cleanly in headless environments (e.g., Ubuntu CI runners, local consoles without GPUs) by relying on the mock architecture in `tests/conftest.py`.
- **Pre-Commit Verification:** Run `uvx --from commitizen cz check --message "<your message>"` or use `pre-commit` to prevent committing invalid git messages.

---

## 🔀 5. Git Workflow & Branching Strategy

1. **Branch Protection:** Pushing directly to `main` is strictly prohibited by repository rules.
2. **Feature Branches:** All work must originate from dedicated branches:
   - `feat/<feature-name>` for new features.
   - `fix/<bug-name>` for bug fixes.
   - `jules/<task-description>` for autonomous tasks dispatched to Jules.
3. **Pull Request & Code Review:**
   - Every PR must detail: (1) Problem solved, (2) Architectural changes, (3) Testing evidence.
   - All AI-generated PRs must undergo human/supervisory code review prior to merge.
4. **Merge Method:** Always use **Squash and Merge** to maintain a clean, linear, and bisect-friendly git history on `main`.

---

## 🤝 6. Camaraderie & Multi-Agent Collaboration Protocol

For multi-agent swarms operating within this repository:
- **No Agent Works Alone:** Always collaborate, review, and validate with peer agents (e.g. Supervisor, Atenea, Hermes, Jules).
- **Mutual Responsibility:** Double-check configurations, respect host security rules (e.g. Bitdefender Total Security safe practices, no port scans or chained remote PowerShell bursts), and preserve workspace integrity.
