# LM-Chat™: Autonomous Spatial AI Assistant & Neural Copilot for NVIDIA Omniverse

[![Kit SDK](https://img.shields.io/badge/Omniverse%20Kit-107%2B-76B900?logo=nvidia)](https://www.nvidia.com/en-us/omniverse/)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?logo=python)](https://www.python.org/)
[![OpenUSD](https://img.shields.io/badge/OpenUSD-v23.11%2B-blue)](https://openusd.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**LM-Chat™** is an enterprise-grade Autonomous Spatial AI suite and neural copilot integrated natively within the **NVIDIA Omniverse** ecosystem. It bridges conversational Large Language Models (LLMs) with 3D **OpenUSD** (Universal Scene Description), enabling developers, engineers, and digital twin creators to generate, simulate, and manipulate complex 3D worlds through natural language.

---

## 🌟 Key Capabilities

* **Dual Interface Modality:**
  - **Native Omniverse GUI (`omni.ui`):** Modern dockable chat window with streaming Markdown output, dynamic status indicators, and one-click code execution.
  - **Enterprise CLI (`cli/lmchat_cli.py`):** Interactive REPL and headless pipeline execution for automation, CI/CD, and power users.
* **Multi-Provider Inference Router:**
  - **Local Privacy (Air-Gapped):** LM Studio (`:1234`), Ollama (`:11434`), vLLM (`:8000`) on NVIDIA RTX GPUs (RTX 40/50 Series).
  - **Cloud / Hybrid:** Google Gemini (3.6 Flash / Pro), OpenAI, Anthropic via standard OpenAI API format.
* **OpenUSD Spatial Context Serializer:**
  - Real-time serialization of stage hierarchy, prims, transforms, lights, materials, and physics metadata into structured JSON for LLM spatial awareness.
* **Self-Healing ReAct Loop:**
  - Automatic detection and interception of runtime Python / OpenUSD exceptions (`Sdf.PathError`, `Tf.DiagnosticMark`). The agent analyzes the traceback and self-corrects autonomously up to configurable retries.
* **Model Context Protocol (MCP) Registry:**
  - Standard JSON-RPC 2.0 tool execution allowing the AI to read design docs, specifications, and external data sources (Google Drive, local files, CAD specs).

---

## 📐 Extension Metadata & Identification

* **Commercial Brand:** `LM-Chat™`
* **NVIDIA Omniverse Extension ID:** `omni.lm_chat`
* **Official Entry Module:** `extension.py` (`LMChatExtension`)
* **Configuration:** `config/extension.toml`
* **CLI Entrypoint:** `cli/lmchat_cli.py` (or `cli/omni_harness.py`)

---

## 🚀 Quickstart & Usage

### 1. Running in NVIDIA Omniverse
1. Clone the repository into your local source folder.
2. In Omniverse Kit / USD Composer / Isaac Sim, navigate to **Window > Extensions**.
3. Add the repository root directory as an extension search path.
4. Search for **LM-Chat** (ID: `omni.lm_chat`) and toggle it **ON**.
5. The LM-Chat window will dock automatically in your workspace.

### 2. Running via Enterprise CLI
To test models or run automated prompts directly in your terminal:
```bash
# Interactive REPL with local LM Studio
python cli/lmchat_cli.py --provider lm_studio

# Headless prompt with Google Gemini Cloud
python cli/lmchat_cli.py --provider cloud --model gemini-2.5-flash --prompt "Genera una celda robótica con cintas transportadoras en OpenUSD"
```

---

## 🧪 Testing & Verification

Run the full automated test suite without requiring a live Omniverse GUI:
```bash
python -m pytest tests/ -v
```

---

## 📄 Documentation & Architecture
* [Product Branding & Specification](docs/PRODUCT_BRANDING.md)
* [System Architecture Diagram (SVG)](docs/diagrams/omni_agent_architecture.svg)
