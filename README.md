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
  - **Local Privacy (Air-Gapped):** LM Studio (`:1234`), Ollama (`:11434`), vLLM (`:8000`) on NVIDIA RTX GPUs (RTX 40/50 Series) with auto-failover and cluster pooling.
  - **Cloud / Hybrid:** Google Gemini (3.8 / 3.7 Flash / Pro), OpenAI (GPT-4o/o3), Anthropic Claude (3.7 / 3.5 Sonnet) via standard OpenAI-compatible API endpoints.
* **OpenUSD Spatial Context Serializer:**
  - Real-time serialization of stage hierarchy, prims, transforms, lights, materials, and physics metadata into structured JSON for LLM spatial awareness.
* **Self-Healing ReAct Loop:**
  - Automatic detection and interception of runtime Python / OpenUSD exceptions (`Sdf.PathError`, `Tf.DiagnosticMark`). The agent analyzes the traceback and self-corrects autonomously up to configurable retries.
* **Model Context Protocol (MCP) Registry:**
  - Standard JSON-RPC 2.0 tool execution allowing the AI to read design docs, specifications, and external data sources (Google Drive, local files, CAD specs).

---

## 📐 Extension Metadata & Identification

* **Commercial Brand:** `LM-Chat™`
* **NVIDIA Omniverse Extension ID:** `orlandodorival.lm_chat`
* **Extension Title:** `LM-Chat: AI Agent & MCP Integration`
* **Official Entry Module:** `extension.py` (`LMChatExtension`)
* **Package Directory:** `exts/orlandodorival.lm_chat/`
* **Configuration Manifest:** `exts/orlandodorival.lm_chat/config/extension.toml`
* **CLI Entrypoint:** `cli/lmchat_cli.py` (or `cli/omni_harness.py`)
* **Visual Assets:** `data/icon.png`, `data/preview.png`

---

## 🚀 Installation & Usage in NVIDIA Omniverse

LM-Chat follows the official NVIDIA Omniverse Kit directory layout (`exts/` structure) and standard Community Registry guidelines.

### Method 1: Git URL via Extension Search Paths (Recommended for Developers)

1. In Omniverse Kit, USD Composer, Isaac Sim, or Omniverse Code, open **Window > Extensions** (or press `Ctrl + E`).
2. Click the gear icon (**Settings**) next to the search bar.
3. In **Extension Search Paths**, click the **+** button to add a new path and paste:
   ```text
   git://github.com/Orlandho/LM-Chat.git?branch=main&dir=exts
   ```
   *Alternative HTTPS URL:*
   ```text
   https://github.com/Orlandho/LM-Chat.git?branch=main&dir=exts
   ```
4. Omniverse Kit will clone and index the extension automatically.
5. In the **Community** tab of the Extension Manager, search for **LM-Chat** (ID: `orlandodorival.lm_chat`).
6. Toggle the extension **ON** (enable **AUTOLOAD** if you want it to start with the application).
7. The LM-Chat window docks automatically into your workspace.

### Method 2: NVIDIA Omniverse Community Registry

Because the repository is tagged with the GitHub topic `omniverse-kit-extension`, it is indexed in the Community Registry:
1. Open **Window > Extensions** in NVIDIA Omniverse.
2. Select the **Community** tab.
3. Search for `LM-Chat` or `orlandodorival.lm_chat`.
4. Click **Install** and toggle the extension **ON**.

### Method 3: Download Release ZIP Archive

1. Download the latest `orlandodorival.lm_chat-vX.Y.Z.zip` from [GitHub Releases](https://github.com/Orlandho/LM-Chat/releases).
2. Extract the archive into your preferred local extensions directory (e.g., `C:\Users\<user>\Documents\Omniverse\exts\orlandodorival.lm_chat` or `~/omni_exts/orlandodorival.lm_chat`).
3. In Omniverse **Window > Extensions > Settings**, add the parent directory containing `orlandodorival.lm_chat` to **Extension Search Paths**.
4. Search for `LM-Chat` and toggle it **ON**.

### Method 4: Local Git Clone

1. Clone the repository locally:
   ```bash
   git clone https://github.com/Orlandho/LM-Chat.git
   ```
2. In Omniverse **Window > Extensions > Settings**, add the `exts` folder of the cloned repository (e.g. `C:/Users/Orlando/Desktop/LM-Chat/exts`) to **Extension Search Paths**.
3. Toggle `orlandodorival.lm_chat` **ON**.

---

## 💻 Running via Enterprise CLI

To test models, evaluate reasoning streams, or run automated batch prompts directly in your terminal without launching the 3D GUI:
```bash
# Interactive REPL with local LM Studio
python cli/lmchat_cli.py --provider lm_studio

# Headless prompt with Google Gemini Cloud
python cli/lmchat_cli.py --provider gemini --model gemini-3.8-flash --prompt "Genera una celda robótica con cintas transportadoras en OpenUSD"

# Query local conversation history
python cli/lmchat_cli.py --history
```

---

## 🧪 Testing & Verification

Execute the complete 219+ automated unit and integration test suite with headless Omniverse mocks:
```bash
python -m pytest tests/ -v
```

---

## 📄 Documentation & Architecture
* [Product Branding & Specification](docs/PRODUCT_BRANDING.md)
* [System Architecture Diagram (SVG)](docs/diagrams/omni_agent_architecture.svg)
* [Universal Multi-Agent Charter (AGENTS.md)](AGENTS.md)
* [Changelog](docs/CHANGELOG.md)
