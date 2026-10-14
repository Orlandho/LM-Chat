# Changelog

Todas las modificaciones notables de este proyecto serán documentadas en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto se adhiere a [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-10-14

### Añadido (Features)
- **Estandarización Omniverse Kit Layout & Registro Comunitario:**
  - Migración al layout estándar `exts/orlandodorival.lm_chat/` para cumplimiento estricto con NVIDIA Community Registry.
  - Actualización del namespace técnico a `orlandodorival.lm_chat` evitando colisiones con prefijos reservados de NVIDIA.
  - Incorporación de recursos visuales oficiales `data/icon.png` (256x256) y `data/preview.png` (800x450).
  - Configuración multicanal de instalación en Omniverse Extension Manager (Git URL, Community Registry con topic `omniverse-kit-extension`, Release ZIP).
- **Soporte Nativo para Modelos de Razonamiento (Reasoning Models):**
  - Detección automática mediante regex de modelos tipo o1, o3, DeepSeek R1 y Claude Thinking (`is_reasoning_model`).
  - Adaptación transparente de payload (omisión de `temperature` y mapeo a `max_completion_tokens`).
  - Parseo asíncrono en tiempo real de etiquetas `<think>...</think>` y campos nativos `reasoning_content`.
  - Componente de interfaz colapsable `CollapsibleFrame` para visualizar el flujo de pensamiento sin saturar el chat.
  - Aislamiento de seguridad: el extractor de código ReAct ignora estrictamente bloques dentro de `<think>`.
- **Inspección y Edición Avanzada de OpenUSD:**
  - `USDInspector` (`IUSDInspector`): auditoría automática de texturas y referencias rotas (`audit_missing_assets`), consulta jerárquica por tipo, ruta o atributo (`find_prims_by_query`), y estado de la pila de capas (`get_layer_stack_status`).
  - `USDController` (`IUSDController`): transformaciones 3D matriciales (`transform_prim`), enlace de materiales MDL (`bind_material`), y agrupación jerárquica de prims (`group_prims`).
  - Transacciones atómicas de mutación USD encapsuladas en `omni.kit.undo` con soporte total para `Ctrl+Z` y `Ctrl+Y`.
- **Modos Duales de Ejecución (Inmediato vs Planificación y Confirmación):**
  - Selector interactivo en cabecera de chat: ⚡ Inmediato vs 📝 Plan.
  - Generación de tarjetas estructuradas de previsualización de cambios USD (`PlanCard`) con botones de acción `[✓ Ejecutar en Stage]` y `[✕ Cancelar]`.
  - Verificación previa del Stage antes de cualquier mutación destructiva.
- **Políticas de Seguridad Espacial (Spatial Security Policies):**
  - `SpatialSecurityPolicy` (`IAgentPolicy`): análisis estático de código Python mediante AST.
  - Bloqueo preventivo de módulos peligrosos (`subprocess`, `socket`, `shutil`, `pty`, etc.).
  - Límites de iteración para bucles `for` y `while` previniendo cuelgues del bucle de renderizado a 60 FPS.
  - Protección de rutas críticas reservadas del escenario (`/OmniverseKit_Root`, `/Render`, etc.).
- **Modo Turbo & Arquitectura de Herramientas MCP:**
  - Micro-lotes de tokens streaming en bucle asíncrono para maximizar rendimiento sin bloquear el renderizado Kit a 60 FPS.
  - Registro dinámico y configuración de servidores Model Context Protocol (`MCPServerConfig`).
- **Ventana de Ajustes Multi-Proveedor y Diagnóstico Avanzado:**
  - Ventana modal `SettingsWindow` para configuración de credenciales y endpoints (LM Studio, Ollama, Gemini, OpenAI, Claude).
  - Descubrimiento dinámico de modelos en caliente (`fetch_remote_models`).
  - Motor de diagnósticos inteligentes (`DiagnosticsEngine`) y registro circular estructurado (`LMStructuredLogger`).
- **Alineación de Catálogo Octubre 2026:**
  - Integración de Gemini 3.8 / 3.7 Flash, Claude Opus 5.5 / Sonnet 5.5, OpenAI GPT-6 Astra / Sol, DeepSeek V4 / R1, Llama 4, Qwen 3.6 y Nemotron 3.5.

### Corregido (Fixes)
- Resiliencia en lectura de sesiones de historial ante bloqueos transitorios de archivos en Windows (`PermissionError [WinError 13]`).
- Limpieza de corrutinas asíncronas huérfanas en cierre de ventana de ajustes.
- Validación de esquemas URL no HTTP en cliente de red.
- Aislamiento estricto del entorno de ejecución dinámica OpenUSD con enlace explícito de `__builtins__` en `USDController`.
- Optimización de búsqueda de historial de chat a una sola pasada en disco y persistencia JSON compacta sin sobrecoste de formato.
- Sanitización de rutas e identificadores de sesión en importación JSON previniendo directory traversal, con permisos restrictivos `0o600`/`0o700`.
- Incorporación de botón para liberación de VRAM en LM Studio y selector de balanceo de carga para clústeres locales.

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
