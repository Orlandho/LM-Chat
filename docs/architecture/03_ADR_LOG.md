---
title: "Registro de Decisiones Arquitectónicas (ADR Log)"
tipo: "adr"
modulo: "architecture"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "ADR Log"
  - "Registro de Decisiones"
  - "Architecture Decision Records"
tags:
  - "adr"
  - "arquitectura"
  - "decisiones"
  - "historia"
---

# Registro de Decisiones Arquitectónicas (ADR Log)

Este registro documenta formalmente las decisiones arquitectónicas clave adoptadas en la suite **LM-Chat™**, proporcionando trazabilidad técnica, contexto del problema, alternativas consideradas y compromisos asumidos.

---

### Plantilla Estándar ADR

```markdown
### ADR-XXX: [Título de la Decisión]
**Fecha:** YYYY-MM-DD | **Estado:** [Propuesto | Aceptado | Obsoleto | Reemplazado]
**Decisores:** Orlando Dorival, Enjambre de Arquitectura

**Contexto:**
> Descripción del problema técnico o requisito funcional/no funcional que motivó la decisión.

**Decisión Tomada:**
> Qué patrón, estándar o arquitectura se implementó de forma estricta.

**Consecuencias:**
> Ventajas obtenidas, compromisos (trade-offs) asumidos y deuda técnica prevenida.
```

---

## Índice Histórico de Decisiones

| ID | Fecha | Título de la Decisión | Estado | Impacto Técnico |
| :---: | :---: | :--- | :---: | :--- |
| **ADR-001** | 2024-05-08 | Separación de Preocupaciones y Estructura Modular (`ui/` vs `logic/`) | **Aceptado** | ISO/IEC 25010 en mantenibilidad |
| **ADR-002** | 2026-09-14 | Estandarización de Layout Kit y Namespace Comunitario (`orlandodorival.lm_chat`) | **Aceptado** | Conformidad con NVIDIA Community Registry |
| **ADR-003** | 2026-09-20 | Sandbox de Gobernanza Espacial mediante Análisis Estático AST | **Aceptado** | Prevención de DoS, RCE y mutación de prims del sistema |
| **ADR-004** | 2026-10-02 | Modos Duales de Ejecución: Inmediato vs. Plan & Confirm con PlanCard | **Aceptado** | Control humano en el bucle para mutaciones USD críticas |
| **ADR-005** | 2026-10-06 | Parseo SSE Incremental de Razonamiento (`<think>`) y Widget Colapsable | **Aceptado** | Soporte transparente para DeepSeek R1, o1/o3 y Claude |
| **ADR-006** | 2026-10-10 | Persistencia Local Atómica de Sesiones con Permisos Restrictivos (`0o600`/`0o700`) | **Aceptado** | Resiliencia ante caídas y protección contra Directory Traversal |
| **ADR-007** | 2026-10-14 | Gestión de VRAM en LM Studio 0.4.x+ y Balanceo Multi-Nodo en ClusterManager | **Aceptado** | Liberación de memoria GPU para trazado de rayos RTX |

---

## Entradas Detalladas del Registro

### ADR-001: Separación de Preocupaciones y Estructura Modular (`ui/` vs `logic/`)
**Fecha:** 2024-05-08 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
Durante la concepción inicial de la extensión, surgió la necesidad de definir dónde viviría el agente IA local y cómo interactuaría con el sistema sin bloquear el proceso principal del motor gráfico, evitando arquitecturas monolíticas propensas a fallos en tiempo de ejecución.

**Decisión Tomada:**
Establecer la división modular estricta del código base imponiendo la Separación de Preocupaciones (SoC). Se decidió dividir el repositorio estructuralmente en los directorios `ui/` y `logic/`. El componente visual (`ui/`) es completamente independiente de las operaciones del agente y de las modificaciones directas a OpenUSD, tareas que recaen exclusivamente bajo la estructura de `logic/`.

**Consecuencias:**
- Cumplimiento de ISO/IEC 25010 en mantenibilidad y modularidad.
- Permite modificar la lógica del agente o sustituir librerías sin afectar el árbol de widgets de `omni.ui`.
- Exige una disciplina rigurosa de inyección de dependencias y delegación de callbacks para mantener el desacoplamiento.

---

### ADR-002: Estandarización de Layout Kit y Namespace Comunitario (`orlandodorival.lm_chat`)
**Fecha:** 2026-09-14 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
La extensión utilizaba identificadores tempranos dispersos como `omni.lm_chat` o `orlandoexplorer.ia_test`. De acuerdo con las normas de publicación de extensiones de NVIDIA Omniverse Kit y el Community Registry, los desarrolladores terceros **no deben utilizar el prefijo reservado `omni.*`**. Asimismo, Omniverse Kit exige una jerarquía física estricta bajo `exts/<package_id>/` para su correcto empaquetado y distribución.

**Decisión Tomada:**
Migrar todo el código de la extensión al directorio canónico `exts/orlandodorival.lm_chat/`, renombrar el módulo de configuración a `config/extension.toml` con el namespace Python `orlandodorival.lm_chat`, e incorporar los activos visuales normalizados `data/icon.png` (256x256) y `data/preview.png` (800x450).

**Consecuencias:**
- Compatibilidad nativa e inmediata con el Extension Manager de Kit SDK 105, 106 y 107+.
- Elegibilidad para publicación en el NVIDIA Omniverse Community Registry bajo el tópico `omniverse-kit-extension`.
- Ruptura de rutas de importación heredadas, mitigada manteniendo un alias retrocompatible `MyExtension = LMChatExtension` en la raíz del paquete.

---

### ADR-003: Sandbox de Gobernanza Espacial mediante Análisis Estático AST
**Fecha:** 2026-09-20 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
El modelo lingüístico puede generar código Python erróneo o peligroso que contenga bucles infinitos (`while True:` sin break), llamadas a librerías del sistema operativo (`subprocess`, `shutil.rmtree`), peticiones HTTP no autorizadas o mutaciones directas sobre prims reservados de la escena (`/OmniverseKit_Root`, `/Render`), lo cual podría colgar el hilo de renderizado o dañar la escena.

**Decisión Tomada:**
Implementar `SpatialSecurityPolicy` (`IAgentPolicy`) en `core/policies.py`. Todo script generado es analizado estáticamente mediante el módulo nativo `ast` antes de ejecutarse en `USDController.execute_code()`. Se restringen builtins peligrosos (`eval`, `exec`, `__import__`), se impone un límite estricto de longitud (100,000 bytes) y se limitan los rangos de iteración en bucles de creación geométrica (máximo 500 prims).

**Consecuencias:**
- Blindaje contra denegación de servicio (DoS) del bucle de 60 FPS y ejecución de comandos arbitrarios.
- Tiempo de validación despreciable (< 2 ms) que no degrada la latencia interactiva.
- Código Python que utilice patrones sintácticos excesivamente complejos o metadatos dinámicos puede requerir ajustes si activa falsos positivos de la política.

---

### ADR-004: Modos Duales de Ejecución: Inmediato vs. Plan & Confirm con PlanCard
**Fecha:** 2026-10-02 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
En entornos de producción industrial o escenarios USD complejos con cientos de dependencias, la ejecución automática directa de código ("Fast Act") entraña el riesgo de aplicar mutaciones indeseadas sin revisión previa humana, obligando al usuario a deshacer continuamente con `Ctrl+Z`.

**Decisión Tomada:**
Incorporar el enum `ExecutionMode` con dos estrategias operativas:
1. `IMMEDIATE`: Ejecución autónoma instantánea en cuanto el bloque Python es parseado.
2. `PLAN_AND_CONFIRM` (estilo Jules / Gemini CLI): El agente genera primero una descripción de los pasos a realizar y retiene el código en memoria (`_pending_code`). La interfaz gráfica presenta el componente interactivo `PlanCard` con botones explícitos `[Ejecutar en Stage]` y `[Cancelar]`.

**Consecuencias:**
- El usuario mantiene el control absoluto y puede inspeccionar visualmente el código propuesto antes de que cualquier vértice o prim se altere en la escena.
- Mayor transparencia y seguridad en etapas de modelado crítico.
- Requiere adaptación del prompt del sistema para orientar al LLM a emitir explicaciones paso a paso antes del bloque de código.

---

### ADR-005: Parseo SSE Incremental de Razonamiento (`<think>`) y Widget Colapsable
**Fecha:** 2026-10-06 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
La aparición de modelos con capacidades de razonamiento extendido (DeepSeek-R1, OpenAI o1/o3, Claude Thinking) introduce bloques de pensamiento intermedios (a menudo delimitados por etiquetas `<think>...</think>` o campos `reasoning_content`) que saturaban la ventana del chat e introducían fragmentos de código provisionales que el extractor confundía con el script final.

**Decisión Tomada:**
Implementar `StreamingReasoningParser` en `logic/inference_router.py` para procesar chunks SSE de forma incremental, segregando los tokens de razonamiento de los tokens de contenido final. En la UI se implementó `CollapsibleFrame`, permitiendo plegar o desplegar el proceso cognitivo sin entorpecer la lectura. Asimismo, el extractor de código ReAct elimina explícitamente cualquier etiqueta `<think>` antes de buscar bloques ` ```python `.

**Consecuencias:**
- Experiencia de usuario limpia y profesional: el pensamiento profundo queda accesible pero colapsado.
- Se elimina por completo el riesgo de ejecutar código preliminar o descartado durante la fase de razonamiento del LLM.

---

### ADR-006: Persistencia Local Atómica de Sesiones con Permisos Restrictivos (`0o600`/`0o700`)
**Fecha:** 2026-10-10 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
La gestión del historial de chat requería un almacenamiento confiable que no dependiera de servicios externos en la nube, que soportara caídas abruptas del proceso sin corromper el historial JSON, y que previniera vulnerabilidades de recorrido de directorios (Directory Traversal).

**Decisión Tomada:**
Implementar `LocalChatHistoryManager` (`IChatHistoryManager`) con almacenamiento en `~/.omni_lm_chat/sessions/`. Cada sesión se almacena como un archivo JSON individual identificado por UUIDv4. La escritura se realiza en dos fases: primero a un archivo `.tmp` con permisos restrictivos `0o600` (archivos) y `0o700` (directorios), seguido de una operación atómica `os.replace`. Los identificadores de sesión son estrictamente sanitizados.

**Consecuencias:**
- Cero pérdida o corrupción de datos ante cortes eléctricos o cierres forzados de Omniverse.
- Cumplimiento de estándares de seguridad en sistemas multi-usuario.
- La búsqueda de sesiones en disco se optimizó a una sola pasada rápida con lectura de metadatos.

---

### ADR-007: Gestión de VRAM en LM Studio 0.4.x+ y Balanceo Multi-Nodo en ClusterManager
**Fecha:** 2026-10-14 | **Estado:** Aceptado  
**Decisores:** Orlando Dorival

**Contexto:**
En estaciones de trabajo con una sola GPU (por ejemplo, NVIDIA GeForce RTX 4070/5060), la ejecución simultánea de Omniverse RTX con trazado de rayos y un modelo LLM local de 8B o 14B parámetros en LM Studio provoca contención severa de memoria de vídeo (VRAM), ocasionando caídas del driver gráfico o reducción drástica de la tasa de cuadros.

**Decisión Tomada:**
Implementar `LMStudioVRAMManager` en `logic/lm_studio_vram.py` con integración nativa a la API REST de LM Studio (`POST /api/v1/models/unload`), añadiendo un botón de acción rápida en `SettingsWindow` para liberar VRAM a demanda. En paralelo, se incorporó `ClusterManager` (`IClusterManager`) para permitir delegar la inferencia a máquinas secundarias o clusters locales mediante estrategias de failover (`priority`, `round_robin`, `lowest_latency`).

**Consecuencias:**
- Elimina el riesgo de cuelgues del motor gráfico por OOM en la GPU durante sesiones complejas de renderizado.
- Habilita topologías híbridas donde la inferencia se procesa en un nodo dedicado de la red local mientras la estación de trabajo concentra el 100% de su GPU en Omniverse.
