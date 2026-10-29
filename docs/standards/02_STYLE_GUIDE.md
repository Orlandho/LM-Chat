---
title: "Guía de Estilo de Código, Docstrings y Documentación Técnica"
tipo: "normativa"
modulo: "standards"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "Guía de Estilo"
  - "Style Guide"
  - "Estándares de Código"
tags:
  - "estilo"
  - "docstrings"
  - "pep8"
  - "openusd"
  - "standards"
---

# Guía de Estilo de Código, Docstrings y Documentación Técnica

## 1. Estándares de Codificación en Python

El código de **LM-Chat™** se adhiere a **PEP 8** y a las directivas de código moderno para Python 3.10+:

1. **Tipado Estricto (Type Annotations):**
   Todas las funciones públicas, métodos de clases y atributos de dataclasses deben declarar tipos explícitos para argumentos y retornos:
   ```python
   async def chat_stream(
       self,
       messages: List[ChatMessage],
       config: InferenceConfig
   ) -> AsyncIterator[str]:
   ```
2. **Uso de Dataclasses Inmutables o Fuertemente Tipadas:**
   Prefiera `@dataclass` para entidades de dominio sobre diccionarios sin tipar. Todo modelo de datos debe implementar métodos de serialización `to_dict()` y deserialización `@classmethod from_dict()`.
3. **Manejo Exclusivo de Codificación UTF-8:**
   Todos los archivos `.py` deben incluir `# -*- coding: utf-8 -*-` o garantizar la compatibilidad con caracteres internacionales en consolas de Windows 11.

---

## 2. Convención de Docstrings (Google Python Style Guide)

Toda clase, método y función pública debe documentarse siguiendo el estándar **Google Python Style Guide**:

```python
def transform_prim(
    self,
    prim_path: str,
    translation: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Transforma un prim existente en el Stage mediante el Command Pattern de Omniverse.

    Valida previamente que la ruta no pertenezca a la jerarquía de prims protegidos
    del sistema y encapsula la operación dentro del historial nativo de Undo.

    Args:
        prim_path (str): Ruta absoluta del prim en el Stage (ej. '/World/Cube').
        translation (Optional[List[float]]): Vector de traslación [x, y, z].
        rotation (Optional[List[float]]): Ángulos de rotación en Euler [rx, ry, rz].
        scale (Optional[List[float]]): Factores de escala [sx, sy, sz].

    Returns:
        Dict[str, Any]: Diccionario con las claves 'success' (bool) y 'error_msg' (str opcional).

    Raises:
        ValueError: Si prim_path es una cadena vacía o no cumple el formato OpenUSD.
    """
```

---

## 3. Invariantes Específicas de OpenUSD y NVIDIA Omniverse

1. **Prohibición de Escrituras Directas a OpenUSD (Bypass de Historial):**
   ```python
   # ❌ INCORRECTO: Escritura destructiva sin registrar en el historial
   stage = omni.usd.get_context().get_stage()
   prim = stage.DefinePrim("/World/Cubo", "Cube")

   # ✅ CORRECTO: Mutación encapsulada en omni.kit.commands con Undo
   omni.kit.commands.execute(
       'CreateMeshPrimWithDefaultXform',
       prim_type='Cube',
       prim_path='/World/Cubo',
       select_new_prim=True
   )
   ```
2. **Aislamiento del Bucle de 60 FPS:**
   Cualquier cómputo intensivo, llamada de red o procesamiento SSE debe ejecutarse en corrutinas asíncronas (`asyncio`) o delegarse a hilos secundarios (`asyncio.run_in_executor`).
3. **Captura Estructurada de Excepciones:**
   Intercepte excepciones especializadas de Pixar USD (`Sdf.PathError`, `Tf.DiagnosticMark`) y empaquete el traceback para alimentar el bucle ReAct de autocorrección.

---

## 4. Convenciones de Documentación y Diagramación (Docs-as-Code)

1. **Metadatos YAML Frontmatter:**
   Cada nota de la documentación debe iniciar con un encabezado estructurado:
   ```yaml
   ---
   title: "Título Descriptivo"
   tipo: "indice | arquitectura | especificacion | manual | auditoria | adr | normativa"
   modulo: "nombre_modulo"
   version: "1.2.0"
   estado: "vigente"
   fecha_revision: "YYYY-MM-DD"
   commit_referencia: "hash"
   autor: "Orlando Dorival"
   aliases: [...]
   tags: [...]
   ---
   ```
2. **Enlaces Relativos y Navegación Bidireccional:**
   Utilice siempre enlaces relativos estándar en Markdown (por ejemplo: `[Texto](../otra_carpeta/archivo.md)`). No utilice rutas absolutas del disco duro local que rompan la navegación en GitHub o en máquinas de otros desarrolladores.
3. **Diagramas Editables de Draw.io y Previsualizaciones:**
   - Todo diagrama debe contar con su archivo fuente `.drawio` en `docs/diagrams/src/`.
   - La previsualización vectorial `.svg` se almacena en `docs/diagrams/svg/` y la rasterizada `.png` en `docs/diagrams/png/`.
   - En las notas Markdown, incruste el SVG y proporcione un enlace de texto para editar el archivo `.drawio`.
   - Utilice la paleta de colores oscuros coherente con el proyecto (`#0b0f19` de fondo, nodos `#0f172a` y `#1e293b`, bordes `#38bdf8`, `#a855f7`, `#22c55e` y texto `#f8fafc`).
