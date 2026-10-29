---
title: "Guía de Auditoría por Muestreo para el Supervisor Codex"
tipo: "auditoria"
modulo: "audit"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "Guía de Auditoría Codex"
  - "Sampling Audit Guide"
  - "Codex Supervisor Guide"
tags:
  - "codex"
  - "supervisor"
  - "auditoria"
  - "muestreo"
  - "trazabilidad"
---

# Guía de Auditoría por Muestreo para el Supervisor Codex

## 1. Objetivo y Rol del Auditor

Esta guía proporciona al agente **Codex** (en su rol de **arquitecto supervisor y auditor independiente**) una ruta estructurada de muestreo técnico para contrastar de forma rápida y concluyente las afirmaciones de la documentación con las implementaciones reales del código base en `C:\Users\Orlando\Desktop\LM-Chat`.

---

## 2. Puntos Clave de Muestreo en Código Fuente

Para realizar una auditoría representativa y eficiente, se recomienda inspeccionar por muestreo los siguientes archivos, métodos y líneas específicas:

### Muestra 1: Bucle ReAct y Conteo de Intentos
- **Archivo:** `exts/orlandodorival.lm_chat/logic/agent_manager.py`
- **Símbolo:** `AgentManager.process_prompt()` (Líneas 273–275, 467–497)
- **Aspecto a Verificar:** Comprobar que `max_retries = 2` y `range(max_retries + 1)` ejecutan exactamente **3 intentos totales** (1 intento inicial + 2 reintentos de autocorrección), desmintiendo cualquier afirmación de "3 reintentos posteriores" (que sumarían 4).
- **Aislamiento de Razonamiento:** Inspeccionar las líneas 426–428 para verificar que `re.sub(r"<think>.*?</think>", "", full_content)` purga los borradores de pensamiento antes de extraer el bloque ` ```python `.

### Muestra 2: Bifurcación de Modos de Ejecución
- **Archivo:** `exts/orlandodorival.lm_chat/logic/agent_manager.py` y `ui/chat_window.py`
- **Símbolos:** `AgentManager.execute_pending_code()`, `AgentManager.cancel_pending_code()`, `ChatWindow.show_plan_confirmation_card()`
- **Aspecto a Verificar:** Comprobar que en modo `PLAN_AND_CONFIRM` el código no se ejecuta inmediatamente en el Stage, sino que se almacena en `_pending_code` y se despacha a la `PlanCard` de la UI hasta recibir confirmación explícita.

### Muestra 3: Sandbox AST y Gobernanza Espacial
- **Archivo:** `exts/orlandodorival.lm_chat/core/policies.py`
- **Símbolo:** `SpatialSecurityPolicy.validate_code()` (Líneas 91–224)
- **Aspecto a Verificar:** Comprobar la inspección del árbol AST: bloqueo de módulos prohibidos (`subprocess`, `shutil`, `socket`), detección de bucles `while True:` sin `break`, límite de tamaño (100,000 bytes) y protección contra mutaciones de `/OmniverseKit_Root` y `/Render`.

### Muestra 4: Controlador OpenUSD y Reversibilidad Undo
- **Archivo:** `exts/orlandodorival.lm_chat/logic/usd_controller.py`
- **Símbolo:** `USDController.execute_code()` (Líneas 60–120)
- **Aspecto a Verificar:** Comprobar el agrupamiento mediante `omni.kit.undo.begin()` y `omni.kit.undo.end()`. Constatar que la reversibilidad real con `Ctrl+Z` depende de que los métodos invoquen `omni.kit.commands.execute()`.

### Muestra 5: Detección Heurística de Modelos de Razonamiento
- **Archivo:** `exts/orlandodorival.lm_chat/logic/inference_router.py`
- **Símbolo:** `is_reasoning_model()` y `REASONING_MODEL_PATTERNS` (Líneas 30–65)
- **Aspecto a Verificar:** Confirmar que la detección de capacidades de razonamiento es puramente heurística por regex y no por un handshake introspectivo de la API.

### Muestra 6: Persistencia Atómica y Prevención de Directory Traversal
- **Archivo:** `exts/orlandodorival.lm_chat/logic/chat_history.py`
- **Símbolo:** `LocalChatHistoryManager.save_session()`, `_sanitize_session_id()` (Líneas 80–145)
- **Aspecto a Verificar:** Comprobar la escritura en dos fases (archivo `.tmp` temporal con permisos `0o600` seguido de `os.replace`), y la sanitización del ID contra secuencias `../` o `..\`.

### Muestra 7: Descarga de VRAM en LM Studio 0.4.x+
- **Archivo:** `exts/orlandodorival.lm_chat/logic/lm_studio_vram.py`
- **Símbolo:** `LMStudioVRAMManager.unload_model()` (Líneas 90–135)
- **Aspecto a Verificar:** Comprobar la llamada HTTP `POST /api/v1/models/unload` con payload `instance_id`.

---

## 3. Muestreo de Diagramas vs. Realidad de Código

| Diagrama | Archivo Preview | Archivo Fuente | Invariante a Contrastar con el Código |
| :--- | :--- | :--- | :--- |
| **D1: Contexto del Sistema** | [`diagrams/svg/01_system_context.svg`](../diagrams/svg/01_system_context.svg) | [`diagrams/src/01_system_context.drawio`](../diagrams/src/01_system_context.drawio) | Contrastar las fronteras entre el proceso host de Omniverse Kit (60 FPS), los subprocesos locales MCP (stdio) y los servidores de inferencia REST. |
| **D2: Arquitectura de Componentes** | [`diagrams/svg/02_component_architecture.svg`](../diagrams/svg/02_component_architecture.svg) | [`diagrams/src/02_component_architecture.drawio`](../diagrams/src/02_component_architecture.drawio) | Validar la relación de inyección entre `ChatDelegate` y `AgentManager`, así como los contratos tipados de `core/interfaces.py`. |
| **D3: Flujo Conversacional** | [`diagrams/svg/03_conversational_flow.svg`](../diagrams/svg/03_conversational_flow.svg) | [`diagrams/src/03_conversational_flow.drawio`](../diagrams/src/03_conversational_flow.drawio) | Contrastar la secuencia de bifurcación entre modo inmediato y modo plan con las líneas 433–455 de `agent_manager.py`. |
| **D5: Pipeline OpenUSD y ReAct** | [`diagrams/svg/05_usd_execution_and_error_recovery.svg`](../diagrams/svg/05_usd_execution_and_error_recovery.svg) | [`diagrams/src/05_usd_execution_and_error_recovery.drawio`](../diagrams/src/05_usd_execution_and_error_recovery.drawio) | Verificar que el flujo represente los 3 intentos máximos y la secuencia AST antes de `omni.kit.undo.begin()`. |

---

## 4. Verificación Automatizada Rápida

Para reproducir la validación técnica en el entorno local:
```bash
# 1. Ejecutar la suite completa de pruebas unitarias (258 pruebas)
python -m pytest tests/ -v

# 2. Verificar la estandarización del layout de extensión Kit y assets
python -m pytest tests/test_omniverse_extension_layout.py -v

# 3. Comprobar la sincronización estricta de versiones SemVer 2.0.0
python -c "from scripts.release import check_version_sanity; print('Version sanity:', check_version_sanity())"
```
