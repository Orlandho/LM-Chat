# Changelog

Todas las modificaciones notables de este proyecto serán documentadas en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto se adhiere a [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-14

### Añadido (Features)
- **Marca Comercial LM-Chat™:** Estandarización de la marca comercial y del ID técnico oficial `omni.lm_chat` para NVIDIA Omniverse Kit.
- **Configuración de Extensión Kit:** Creación de `config/extension.toml` compatible con Omniverse Kit SDK 105, 106 y 107+.
- **CLI Empresarial LM-Chat:** Implementación de `cli/lmchat_cli.py` con consola interactiva REPL, comandos slash (`/switch`, `/model`, `/url`, `/key`, `/status`, `/clear`, `/exit`) y ejecución directa *headless*.
- **Router Multi-Proveedor de Inferencia:** Soporte streaming asíncrono para LM Studio (`:1234`), Ollama (`:11434`), vLLM (`:8000`) y APIs Cloud (Google Gemini 3.6 Flash/Pro, OpenAI, Anthropic).
- **Serializador de Contexto Espacial OpenUSD:** Extracción en tiempo real de jerarquías de prims, matrices de transformación, propiedades de iluminación y materiales MDL.
- **Bucle ReAct y Self-Healing:** Intercepción de excepciones (`Sdf.PathError`, `Tf.DiagnosticMark`) con autorreflexión y autocorrección automática del código Python.
- **Registro de Herramientas MCP (Model Context Protocol):** Cliente JSON-RPC 2.0 para lectura de especificaciones de diseño y documentos externos.
- **Suite de Pruebas Unitarias:** 37 pruebas automatizadas de caja blanca y de integración cubriendo interfaz gráfica, router, MCP y OpenUSD.
- **Documentación de Producto:** Especificación oficial en Markdown (`docs/PRODUCT_BRANDING.md`) y formato Word (`docs/LM_Chat_Product_Specification.docx`).

### Corregido (Fixes)
- Soporte para codificación UTF-8 en terminales de Windows 11 sin errores por emojis o caracteres multilingües.
- Corrección de la aplicación de masa dinámica en PhysX (`UsdPhysics.MassAPI`).
- Mocks aislados de Omniverse para ejecución multiplataforma sin depender del entorno 3D abierto.
