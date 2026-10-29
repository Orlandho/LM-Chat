---
title: "Patrones de Diseño en Omniverse (Micro-Arquitectura)"
tipo: "arquitectura"
modulo: "patterns"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "Patrones Omniverse"
  - "Model-Delegate-View"
  - "Command Pattern USD"
tags:
  - "patrones"
  - "omniverse"
  - "openusd"
  - "mdv"
  - "command_pattern"
---

# Patrones de Diseño en Omniverse (Micro-Arquitectura)

Este documento establece la micro-arquitectura y los patrones de diseño oficiales a seguir dentro de la capa del motor NVIDIA Omniverse, garantizando la predictibilidad, estabilidad y el control del estado dentro del entorno.

---

## 1. Patrón Model-Delegate-View (UI)

Toda interfaz gráfica creada dentro de la extensión debe regirse estrictamente bajo el patrón **Model-Delegate-View**, provisto y optimizado por la API nativa de `omni.ui`.

### Justificación Técnica
Debemos erradicar el concepto de la arquitectura Model-View-Controller (MVC) tradicional del desarrollo web al trabajar con la UI del motor de renderizado. En Omniverse, el objetivo fundamental es desacoplar el *estado* del chat o flujo de la *representación visual*:
- **Model (`ChatModel` en `ui/models.py`):** Actúa como la única fuente de verdad (Single Source of Truth) de los datos subyacentes (mensajes, estados de carga, badges).
- **Delegate (`ChatDelegate` en `ui/chat_window.py`):** Contiene la lógica responsable de conectar los eventos de usuario con las operaciones de negocio, utilizando *Dependency Injection* (Inyección de Dependencias) para propagar los callbacks hacia `AgentManager`.
- **View (`ChatWindow`):** Muestra la estructura visual construida a 60 FPS asíncronos sin albergar lógica de inferencia ni mutaciones de datos.

---

## 2. Patrón de Comando (Command Pattern para OpenUSD)

La Inteligencia Artificial y cualquier módulo de automatización tienen **estrictamente prohibido modificar la jerarquía OpenUSD directamente con scripts y métodos crudos de la API USD**. Cualquier mutación del estado geométrico o topológico de la escena debe ejecutarse a través de la API `omni.kit.commands.execute()`.

### Justificación de Reversibilidad
El uso del *Patrón de Comando* garantiza la persistencia segura de las operaciones. Envolver cada cambio de la IA en un comando de Omniverse es fundamental para registrar las alteraciones dentro del historial nativo (Undo Stack) del motor. Esto permite a los usuarios retroceder los cambios a través de **Ctrl+Z (Deshacer / Rehacer)** si los resultados de la IA son indeseados.

### Ejemplo de Comando en Omniverse (Snippet Oficial)

```python
import omni.kit.commands
from pxr import Sdf

def create_mesh_safely(prim_path: str):
    """Crea un mesh primitive registrándolo en el historial nativo de Undo."""
    success, result = omni.kit.commands.execute(
        'CreateMeshPrimWithDefaultXform',
        prim_type='Cube',
        prim_path=prim_path,
        select_new_prim=True,
        prepend_default_xform=True
    )

    if success:
        print(f"Prim creado y registrado en historial: {prim_path}")
    else:
        print(f"Fallo al ejecutar el comando OpenUSD en {prim_path}")
```
