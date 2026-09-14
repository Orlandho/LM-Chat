# Reglas de Colaboración Agéntica - Proyecto LM-Chat (NVIDIA Omniverse)

Este documento rige la interacción, directivas y arquitectura para todos los agentes de Inteligencia Artificial que operan en este repositorio, respetando la voluntad y configuración de nuestro creador, Orlando Dorival.

## 🤝 1. Filosofía de Camaradería y Delegación
- **Trabajo en Equipo Perpetuo:** Los agentes (Atenea, Hermes, Supervisor) nunca operan solos. Mantenemos comunicación estrecha, activa y de apoyo mutuo.
- **Esfuerzo Máximo ("Mejor que sobre a que falte"):** Priorizamos invariablemente modelos de razonamiento avanzado (`Pro` o `Inherit`) con alto esfuerzo cognitivo.
- **Delegación Universal y Concurrencia (Swarm de Jules):** Las tareas técnicas complejas se descomponen activamente en módulos independientes y desacoplados basados en los contratos estrictos de `core/interfaces.py`. Múltiples instancias de Jules trabajan en paralelo sobre ramas aisladas (`feature/*`) para acelerar el desarrollo con cero conflictos de fusión.
- **Revisión Rigurosa:** Ningún Pull Request (PR) de Jules será fusionado sin una revisión estricta y exhaustiva que asegure la calidad empresarial, la seguridad y la correcta arquitectura.

## 🏗️ 2. Directivas Arquitectónicas del Proyecto
- **Paradigma MDV y Command Pattern:** Es obligatorio el uso de la arquitectura Desacoplada *Model-Delegate-View* (MDV). La Inteligencia artificial **NUNCA** modificará el Stage USD de forma destructiva directa. Siempre debe emitir operaciones a través de `omni.kit.commands.execute` para garantizar el soporte nativo de *Undo/Redo* de Omniverse.
- **Prioridad de Interfaces:**
  1. **PRIMARIA (GUI nativa):** La interfaz construida con `omni.ui` es la prioridad absoluta y el método principal de interacción para el usuario final.
  2. **SECUNDARIA (CLI Harness):** Interfaz para automatizaciones, empresas y usuarios avanzados de terminal.

## 🛡️ 3. Resiliencia, Testing (CI/CD) y Red
- **Bucle ReAct y Self-Healing:** El arnés agéntico debe capturar excepciones de Python y errores de `pxr.Usd` para retroalimentar al LLM, forzando la corrección automática sin colgar la sesión del usuario.
- **Pruebas (Jules CI):** Es mandatorio aislar la lógica agéntica del motor pesado de Omniverse. Todas las pruebas unitarias y de integración que corran en GitHub Actions (`jules-ci.yml`) deben utilizar *mocks* de las librerías `pxr` y `omni.kit`.
- **Seguridad Bitdefender:** Prohibido el escaneo agresivo de puertos o ejecución remota sospechosa. Toda comunicación entre nodos locales (Titan ↔ Laptop) debe darse mediante sincronización de estado (GitHub MCP) o transferencias SFTP/locales limpias.
