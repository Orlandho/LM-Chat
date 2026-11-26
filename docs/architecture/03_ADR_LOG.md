# Registro de Decisiones Arquitectónicas (ADR Log)

> **Fuente oficial vigente (SSOT):** A partir de la migración documental a Atlassian (`LMCHAT-12`), el registro vivo de Decisiones Arquitectónicas (ADR-001 en adelante) se mantiene oficialmente en Confluence: **[02.3 — Registro de Decisiones Arquitectónicas (ADR)](https://orlandodorival.atlassian.net/wiki/spaces/LMCHAT/pages/8552449)** (seguimiento en Jira **[LMCHAT-28](https://orlandodorival.atlassian.net/browse/LMCHAT-28)**). Este archivo se conserva en el repositorio únicamente como referencia histórica local de `ADR-001`.

Este archivo consolida las decisiones arquitectónicas clave del Agente Híbrido en NVIDIA Omniverse, para mantener la transparencia en la evolución técnica del ecosistema. Todo nuevo patrón de diseño o alteración estructural debe ser registrado en Confluence `LMCHAT` usando la plantilla oficial.

---

### Plantilla ADR

*Para registrar un nuevo cambio, añade una nueva entrada usando el formato a continuación:*

**ID:** `ADR-XXX`
**Fecha:** `YYYY-MM-DD`
**Estado:** `[Propuesto | Aceptado | Obsoleto]`

**Contexto:**
> *Descripción del problema que motivó la decisión técnica o el cambio.*

**Decisión Tomada:**
> *Qué se decidió implementar de forma estricta (Patrones, Librerías, Cambios en Capas).*

**Consecuencias:**
> *Ventajas operativas y técnicas obtenidas, así como los compromisos (trade-offs) asumidos tras aplicar el cambio.*

---

## Entradas ADR

### ADR-001
**Fecha:** 2024-05-08
**Estado:** Aceptado

**Contexto:**
> Durante el arranque del diseño de la extensión, surgió la necesidad de definir dónde viviría el agente IA local y cómo interactuaría con el sistema sin bloquear el proceso principal del motor, evitando un diseño monolítico propenso a fallas.

**Decisión Tomada:**
> Establecer de forma permanente la división modular del código base imponiendo la Separación de Preocupaciones (SoC). Se decidió dividir el repositorio estructuralmente en los directorios `ui/` y `logic/`. El componente visual (`ui/`) será completamente independiente de las operaciones, orquestaciones del agente y modificaciones a USD, tareas que recaerán exclusivamente bajo la estructura subyacente en `logic/`.

**Consecuencias:**
> El entorno alcanza el cumplimiento ISO/IEC 25010 en mantenibilidad. Permite modificar las librerías o interacciones del Agente ReAct en la capa `logic/` sin temor a romper los flujos renderizados de `omni.ui`. Sin embargo, esto requiere una disciplina estricta de inyección de dependencias y callbacks (Dependency Injection) para establecer la comunicación asincrónica sin generar un acoplamiento directo entre los archivos.
