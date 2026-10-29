---
title: "Catálogo de Fuentes Consultadas y Protocolo de Mantenimiento Documental"
tipo: "mantenimiento"
modulo: "maintenance"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "Catálogo de Fuentes"
  - "Mantenimiento Documental"
  - "Docs-as-Code Maintenance"
tags:
  - "mantenimiento"
  - "fuentes"
  - "gdrive"
  - "calendar"
  - "trazabilidad"
---

# Catálogo de Fuentes Consultadas y Protocolo de Mantenimiento

## 1. Catálogo Completo de Fuentes Consultadas

Esta documentación se construyó a partir del cruce riguroso de fuentes primarias locales, propuestas históricas en la nube y registros operativos:

| Fuente | Ubicación / Identificador | Tipo de Fuente | Acceso y Estado de Consulta |
| :--- | :--- | :--- | :--- |
| **Repositorio Objetivo** | `C:\Users\Orlando\Desktop\LM-Chat` | Código Fuente & Configuración | **Acceso Total:** Código inspeccionado bajo `exts/orlandodorival.lm_chat/`, suite de 258 pruebas ejecutada. |
| **Documentación Existente** | `C:\Users\Orlando\Desktop\LM-Chat\docs` | Docs Previos & Assets | **Acceso Total:** Documentos analizados, depurados de mojibake y reorganizados en estructura modular. |
| **Repositorio de Referencia** | `C:\Users\Orlando\Desktop\web card dorival\orlando-web-card-platform\docs` | Referencia Metodológica | **Acceso Total:** Se adoptaron las prácticas de YAML frontmatter, diagramas editables `.drawio`, previsualizaciones vectoriales SVG y matrices de auditoría técnica reproducible. |
| **Estatuto Universal AGENTS.md** | `C:\Users\Orlando\Desktop\LM-Chat\AGENTS.md` | Directivas Invariantes | **Acceso Total:** Invariantes de Command Pattern, 60 FPS, ReAct self-healing, SemVer 2.0.0 y prohibición de supuestos estáticos. |
| **Carpeta Google Drive** | ID: `1hU_3-FeJA6SGrtEDCa_xf0uaXUGemQ5E` | Propuestas Históricas | **Tratamiento Declarado:** Subcarpetas `vision` y `Technical Planning`. Plugin no conectado localmente; se incorporan sus conceptos esenciales (visión de producto, arquitectura híbrida, ReAct, MCP) contrastándolos con la realidad del código. |
| **Doc Entrada: Visión de Producto** | ID: `185lj9LU472O9VodN-B1RBUKnHwE5KT8qwONn97HfeXo` | Especificación Preliminar | Reflejado en `docs/history/01_SPECIFICATION_DOCX_ADAPTATION.md` y `docs/vision/01_PRODUCT_VISION_AND_REAL_STATE.md`. |
| **Doc Entrada: Arquitectura Híbrida** | ID: `1d8reA4StebqaO0mFhqmyoCUf17i_Cwx_ZLmiWo2sgwE` | Macro-Arquitectura | Reflejado en `docs/architecture/01_MACRO_ARCHITECTURE.md` y `docs/architecture/02_SYSTEM_DESIGN.md`. |
| **Captura del Usuario (14-Oct)** | Imagen del entorno de trabajo | Evidencia Operativa | **Evidencia Primaria:** Contiene las 8 tareas completadas el 14 de octubre, contrastadas una a una en la [Matriz de Auditoría](../audit/01_TASK_AUDIT_AND_GAP_ANALYSIS.md). |
| **Google Calendar & Google Tasks** | Citas operativas y recordatorios | Planificación Temporal | **Limitación Declarada:** OAuth2 no conectado. Las citas con status `confirmed` y enlaces a Tasks se tratan como recordatorios de trabajo y fechas programadas, no como pruebas de código funcional. |
| **Historial Git del Repositorio** | Ramas `main`, `origin/main`, PRs (#34 a #125) | Trazabilidad de Commits | **Acceso Total:** Inspeccionados commits desde el arranque del enjambre hasta `c0c41db` (Bolt USD query optimization). |

---

## 2. Tratamiento de Documentos Históricos y Propuestas

> [!IMPORTANT]
> **Principio de Trazabilidad Histórica:** Ninguna propuesta, instrucción incrustada o aspiración contenida en los documentos de Google Drive o borradores `.docx` se asume como implementada sin contrastarla directamente con el código fuente en `exts/orlandodorival.lm_chat/` y sus pruebas asociadas. No se inventan fechas de certificación ante NVIDIA ni aprobaciones regulatorias no acreditadas.

Las diferencias históricas detectadas se documentan explícitamente:
1. **Namespace Omniverse:** La propuesta temprana utilizaba `omni.lm_chat`; el código implementado y verificado utiliza `orlandodorival.lm_chat` para cumplir con las directivas de publicación de extensiones de NVIDIA.
2. **Serializador Espacial:** El borrador nombraba `logic/spatial_usd_context.py`; la implementación real consolidada es `logic/usd_context.py`.
3. **Registro MCP:** El borrador nombraba `mcp/client_registry.py`; la implementación real consolidada es `mcp/omni_mcp_registry.py`.

---

## 3. Protocolo de Mantenimiento Docs-as-Code

Para preservar la coherencia y fidelidad técnica de esta bóveda a lo largo del ciclo de vida del proyecto:

### A. Modificaciones de Código y Sincronización Documental
1. **Contratos e Interfaces:** Si se altera una signatura en `core/interfaces.py` o una directiva en `core/policies.py`, debe actualizarse inmediatamente [`04_CONTRACTS_AND_INTERFACES.md`](../architecture/04_CONTRACTS_AND_INTERFACES.md).
2. **Nuevos Proveedores o Modelos:** Cualquier cambio en el catálogo predeterminado de `SettingsManager` debe reflejarse en [`01_PROVIDERS_AND_MODEL_DISCOVERY.md`](../integrations/01_PROVIDERS_AND_MODEL_DISCOVERY.md).
3. **Nuevas Decisiones Arquitectónicas:** Debe redactarse una nueva entrada `ADR-XXX` en [`03_ADR_LOG.md`](../architecture/03_ADR_LOG.md) siguiendo la plantilla oficial.

### B. Mantenimiento y Regeneración de Diagramas
Los diagramas se gobiernan mediante el script automatizado `scripts/generate_diagrams.py`:
```bash
# Para actualizar los diagramas tras modificar los flujos:
python scripts/generate_diagrams.py
```
Este comando:
1. Lee las definiciones Mermaid actualizadas en `scripts/generate_diagrams.py` o `docs/diagrams/src/*.mmd`.
2. Genera los vectores SVG transparentes en `docs/diagrams/svg/` utilizando `mmdc` y el ejecutable local de Chrome.
3. Genera las imágenes rasterizadas PNG en `docs/diagrams/png/`.
4. Actualiza los archivos fuente editables `.drawio` en `docs/diagrams/src/`.

### C. Versionado y Releases
Al preparar una nueva versión con `scripts/release.py` (ej. `python scripts/release.py patch`):
- Los metadatos de frontmatter YAML (`version`, `commit_referencia`, `fecha_revision`) deben actualizarse de forma sincronizada con `extension.toml`, `pyproject.toml`, `CITATION.cff` y `CHANGELOG.md`.
