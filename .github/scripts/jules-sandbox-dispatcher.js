/**
 * jules-sandbox-dispatcher.js
 * 
 * Despachador de sesiones en Sandbox Virtual de Google Jules (jules.google.com)
 * para el repositorio LM-Chat (NVIDIA Omniverse Kit Spatial AI Copilot).
 */

const fs = require('fs');

const GITHUB_TOKEN = process.env.GITHUB_TOKEN || process.env.GITHUB_PERSONAL_ACCESS_TOKEN;
const GITHUB_REPOSITORY = process.env.GITHUB_REPOSITORY || 'Orlandho/LM-Chat';
const GITHUB_API_URL = process.env.GITHUB_API_URL || 'https://api.github.com';

const STATUS_CONTEXT = 'Veredicto de Auditoría en Sandbox de Jules';
const WATCHDOG_TIMEOUT_MINUTES = parseInt(process.env.WATCHDOG_TIMEOUT_MINUTES || '10', 10);
const POLL_INTERVAL_SECONDS = parseInt(process.env.POLL_INTERVAL_SECONDS || '25', 10);

if (!GITHUB_TOKEN) {
  console.error('❌ ERROR CRÍTICO: GITHUB_TOKEN no está definido en el entorno.');
  process.exit(1);
}

// Cliente HTTP para GitHub API
async function ghRequest(endpoint, method = 'GET', body = null) {
  const url = `${GITHUB_API_URL}${endpoint}`;
  const headers = {
    'Authorization': `Bearer ${GITHUB_TOKEN}`,
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'LM-Chat-Jules-Sandbox-Dispatcher/1.0',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json'
  };

  const options = { method, headers };
  if (body) {
    options.body = JSON.stringify(body);
  }

  const res = await fetch(url, options);
  const responseData = await res.json().catch(() => null);

  if (!res.ok) {
    const errorMsg = responseData?.message || `HTTP ${res.status} ${res.statusText}`;
    throw new Error(`GitHub API [${method} ${endpoint}] falló: ${errorMsg}`);
  }

  return responseData;
}

// Establece el status check del commit
async function setCommitStatus(sha, state, description, targetUrl = null) {
  console.log(`📡 Actualizando Status Check [${STATUS_CONTEXT}] -> ${state.toUpperCase()}: "${description}"`);
  const payload = {
    state,
    description: description.substring(0, 140),
    context: STATUS_CONTEXT
  };
  if (targetUrl) {
    payload.target_url = targetUrl;
  }
  return await ghRequest(`/repos/${GITHUB_REPOSITORY}/statuses/${sha}`, 'POST', payload);
}

// Publica un comentario en un Issue o PR
async function postComment(issueOrPrNumber, body) {
  return await ghRequest(`/repos/${GITHUB_REPOSITORY}/issues/${issueOrPrNumber}/comments`, 'POST', { body });
}

// Obtiene el estado actual del check
async function getCommitStatusState(sha) {
  const statuses = await ghRequest(`/repos/${GITHUB_REPOSITORY}/statuses/${sha}`, 'GET');
  if (Array.isArray(statuses)) {
    const match = statuses.find(s => s.context === STATUS_CONTEXT);
    if (match) {
      return match.state;
    }
  }
  return null;
}

async function main() {
  console.log('================================================================');
  console.log('🤖 INICIANDO DESPACHADOR DE SESIÓN EN SANDBOX DE JULES PARA LM-CHAT');
  console.log('================================================================');

  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !fs.existsSync(eventPath)) {
    console.error('❌ No se encontró GITHUB_EVENT_PATH válido.');
    process.exit(1);
  }

  const eventData = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
  const pr = eventData.pull_request;

  if (!pr) {
    console.log('ℹ️ El evento no corresponde a un Pull Request. Finalizando sin acción.');
    process.exit(0);
  }

  const prNumber = pr.number;
  const prTitle = pr.title;
  const headSha = pr.head.sha;
  const headRef = pr.head.ref;
  const baseRef = pr.base.ref;
  const author = pr.user?.login || 'desconocido';
  const prUrl = pr.html_url;

  console.log(`📋 PR Detectado: #${prNumber} - "${prTitle}"`);
  console.log(`📌 Rama origen: ${headRef} | Commit SHA: ${headSha}`);
  console.log(`🎯 Rama destino: ${baseRef} | Autor: @${author}`);

  // Paso 1: Poner el status check en PENDING
  await setCommitStatus(
    headSha,
    'pending',
    'Esperando veredicto del Agente Jules en sandbox virtual (jules.google.com)...'
  );

  // Paso 2: Construir el cuerpo del Issue para Google Jules con metadatos estructurados
  const issueTitle = `[jules] Auditoría de Arquitectura Omniverse, OpenUSD y Calidad para PR #${prNumber}: ${prTitle}`;
  const issueBody = `<!-- JULES_AUDIT_METADATA
PR_NUMBER: ${prNumber}
COMMIT_SHA: ${headSha}
BRANCH: ${headRef}
BASE: ${baseRef}
AUTHOR: ${author}
DISPATCHED_AT: ${new Date().toISOString()}
-->

# 🤖 [Google Jules] Misión de Auditoría en Entorno Virtual para LM-Chat (PR #${prNumber})

¡Hola Jules! Se requiere tu intervención como auditor y revisor senior de IA en tu sandbox virtual de la nube para el **Pull Request #${prNumber}** en el repositorio [\`${GITHUB_REPOSITORY}\`](${prUrl}).

---

### 📌 Metadatos del Pull Request
- **PR:** [#${prNumber} - ${prTitle}](${prUrl})
- **Rama de Trabajo:** \`${headRef}\`
- **Rama Base:** \`${baseRef}\`
- **Commit Evaluado:** \`${headSha}\`
- **Autor:** @${author}
- **Fecha:** ${new Date().toLocaleString('es-PE', { timeZone: 'America/Lima' })}

---

### 🎯 Directrices de Evaluación para Jules (según AGENTS.md):
1. **Invariantes Arquitectónicas de NVIDIA Omniverse:**
   - **Mutaciones No Destructivas en USD:** Verificar que las operaciones sobre el Stage de OpenUSD utilicen el Command Pattern (\`omni.kit.commands.execute\`) y preserven deshacer/rehacer (\`Ctrl+Z\` / \`Ctrl+Y\`).
   - **Bucle Sagrado Asíncrono de 60 FPS:** El hilo principal de renderizado de la UI de Omniverse NUNCA debe bloquearse con I/O síncrono o streaming de LLMs.
   - **Autocorrección ReAct:** Manejo seguro de excepciones con captura de tracebacks para recuperación de errores.
2. **Registro de Clientes MCP (Model Context Protocol):**
   - Verificar que los servidores y herramientas MCP en \`mcp/\` se registren y comuniquen de forma asíncrona y segura.
3. **Ejecución y Verificación de la Suite de Pruebas:**
   - Ejecuta la suite de pruebas en tu máquina virtual:
     \`pytest tests/ -v --tb=short\`
   - Confirma que las 37+ pruebas con mocks de Omniverse pasen al 100% sin excepciones no controladas.
4. **SemVer y Convención de Commits:**
   - Verificar que los mensajes respeten la especificación Conventional Commits (\`feat:\`, \`fix:\`, etc.).

---

### ⚖️ Emisión Obligatoria del Veredicto
Para que el sistema capture tu veredicto y desbloquee la fusión del PR, concluye tu evaluación con una de las siguientes líneas exactas:

* Si todo está correcto y cumple las invariantes:
  \`\`\`text
  VEREDICTO: APROBADO
  \`\`\`

* Si detectas fallos, regresiones o violación de las reglas de Omniverse:
  \`\`\`text
  VEREDICTO: RECHAZADO
  \`\`\`
  *(Detallando las inconsistencias encontradas y los pasos de corrección).*

---
> 🤖 **Nota de Sistema:** Este Issue fue generado automáticamente para el agente Jules en [jules.google.com](https://jules.google.com).
`;

  // Paso 3: Crear el Issue en GitHub asignado con la etiqueta 'jules'
  let issueUrl = null;
  let issueNumber = null;
  try {
    console.log(`📤 Creando Issue de auditoría con etiquetas ["jules", "audit-sandbox"]...`);
    const createdIssue = await ghRequest(`/repos/${GITHUB_REPOSITORY}/issues`, 'POST', {
      title: issueTitle,
      body: issueBody,
      labels: ['jules', 'audit-sandbox']
    });

    issueUrl = createdIssue.html_url;
    issueNumber = createdIssue.number;
    console.log(`✅ Issue de Auditoría creado exitosamente: #${issueNumber} (${issueUrl})`);

    // Actualizar el status check con la URL directa del Issue
    await setCommitStatus(
      headSha,
      'pending',
      `Sesión Jules despachada (#${issueNumber}). Esperando veredicto...`,
      issueUrl
    );

    // Publicar comentario informativo en el PR
    const prNotice = `### 🤖 [Agente Jules] Sesión de Auditoría Despachada en Entorno Virtual

Se ha iniciado el proceso de auditoría y revisión en sandbox para este Pull Request:
- **Issue de Auditoría Asignado a Jules:** [#${issueNumber} - ${issueTitle}](${issueUrl})
- **Entorno de Trabajo:** [Google Jules Dashboard (jules.google.com/session)](https://jules.google.com/session)
- **Status Check:** \`${STATUS_CONTEXT}\` -> **PENDING (🟡 En espera)**

> ⏳ *Jules clonará la rama \`${headRef}\` en su contenedor virtual, ejecutará las pruebas de Omniverse y emitirá su veredicto. Este Pull Request permanecerá bloqueado hasta recibir \`VEREDICTO: APROBADO\`.*
`;
    await postComment(prNumber, prNotice);

  } catch (err) {
    console.error(`❌ Error al crear el Issue para Jules: ${err.message}`);
    await setCommitStatus(
      headSha,
      'error',
      `Fallo al despachar Issue a Jules: ${err.message.substring(0, 80)}`
    );
    await postComment(prNumber, `### ❌ [Alerta] Error al Despachar Sesión a Jules
No se pudo crear el Issue de auditoría en GitHub.
**Detalle del error:** \`${err.message}\`
Por favor verifica los permisos del workflow (\`issues: write\`) y reintenta.`);
    process.exit(1);
  }

  // Paso 4: Watchdog de Espera con Detección de Timeouts y Manejo de Errores Asíncronos
  console.log(`\n⏳ INICIANDO WATCHDOG DE VEREDICTO (Límite: ${WATCHDOG_TIMEOUT_MINUTES} minutos, sondeo cada ${POLL_INTERVAL_SECONDS}s)...`);
  const startTime = Date.now();
  const maxWaitTime = WATCHDOG_TIMEOUT_MINUTES * 60 * 1000;

  let finalState = 'pending';
  let iteration = 0;

  while (Date.now() - startTime < maxWaitTime) {
    iteration++;
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_SECONDS * 1000));

    const elapsedSeconds = Math.round((Date.now() - startTime) / 1000);
    try {
      // 1. Verificar si el Status Check ya fue actualizado externamente
      const currentState = await getCommitStatusState(headSha);
      console.log(`[Watchdog T+${elapsedSeconds}s | Iteración ${iteration}] Estado del status check: ${currentState?.toUpperCase() || 'NO_ENCONTRADO'}`);

      if (currentState === 'success') {
        console.log('🎉 ¡VEREDICTO APROBADO DETECTADO! El check se encuentra en SUCCESS.');
        finalState = 'success';
        break;
      } else if (currentState === 'failure') {
        console.log('❌ VEREDICTO RECHAZADO DETECTADO. El check se encuentra en FAILURE.');
        finalState = 'failure';
        break;
      } else if (currentState === 'error') {
        console.log('⚠️ ESTADO DE ERROR DETECTADO EN EL STATUS CHECK.');
        finalState = 'error';
        break;
      }

      // 2. Respaldo directo: Consultar comentarios en el Issue de auditoría
      if (issueNumber) {
        const comments = await ghRequest(`/repos/${GITHUB_REPOSITORY}/issues/${issueNumber}/comments`, 'GET');
        if (Array.isArray(comments) && comments.length > 0) {
          for (const comment of comments) {
            const body = comment.body || '';
            const commentUrl = comment.html_url || issueUrl;

            if (/(?:VEREDICTO|VERDICT):\s*(?:APROBADO|APPROVED)/i.test(body)) {
              console.log(`🎉 [Watchdog]: Detectado VEREDICTO: APROBADO en comentarios del Issue #${issueNumber}`);
              await setCommitStatus(headSha, 'success', '✅ Aprobado por el Agente Jules en entorno virtual', commentUrl);
              await postComment(prNumber, `### 🟢 [Agente Jules] Auditoría Virtual APROBADA (Detectada por Watchdog)\n\nEl Agente Jules completó la auditoría en su entorno virtual con resultado favorable:\n- **Veredicto:** \`VEREDICTO: APROBADO\`\n- **Status Check:** \`${STATUS_CONTEXT}\` -> **SUCCESS (🟢 Aprobado)**\n- **Detalle:** [Ver análisis en Issue #${issueNumber}](${commentUrl})`);
              finalState = 'success';
              break;
            } else if (/(?:VEREDICTO|VERDICT):\s*(?:RECHAZADO|REJECTED|FALLIDO|FAILED)/i.test(body)) {
              console.log(`🛑 [Watchdog]: Detectado VEREDICTO: RECHAZADO en comentarios del Issue #${issueNumber}`);
              await setCommitStatus(headSha, 'failure', '❌ Rechazado por el Agente Jules. Requiere correcciones.', commentUrl);
              await postComment(prNumber, `### 🔴 [Agente Jules] Auditoría Virtual RECHAZADA (Detectada por Watchdog)\n\nEl Agente Jules detectó inconsistencias en su sandbox virtual:\n- **Veredicto:** \`VEREDICTO: RECHAZADO\`\n- **Status Check:** \`${STATUS_CONTEXT}\` -> **FAILURE (🔴 Bloqueado)**\n- **Detalle:** [Ver observaciones en Issue #${issueNumber}](${commentUrl})`);
              finalState = 'failure';
              break;
            }
          }
          if (finalState === 'success' || finalState === 'failure') {
            break;
          }
        }
      }
    } catch (pollErr) {
      console.warn(`⚠️ Error transitorio durante el sondeo del status (se reintentará): ${pollErr.message}`);
    }
  }

  // Si terminó el ciclo y aún está en pending, ocurrió un TIMEOUT asíncrono
  if (finalState === 'pending') {
    const elapsedMinutes = (Date.now() - startTime) / (60 * 1000);
    console.error('\n================================================================');
    console.error(`🚨 ALERTA: TIMEOUT DE AUDITORÍA ASÍNCRONA (${elapsedMinutes.toFixed(1)} min transcurridos)`);
    console.error('El agente Jules no emitió su veredicto dentro del tiempo límite establecido.');
    console.error('================================================================');

    console.error('📋 REPORTE DE DIAGNÓSTICO DEL SISTEMA:');
    console.error(`- Repositorio: ${GITHUB_REPOSITORY}`);
    console.error(`- Pull Request: #${prNumber} (Rama: ${headRef})`);
    console.error(`- Commit SHA: ${headSha}`);
    console.error(`- Issue de Auditoría: #${issueNumber} (${issueUrl})`);
    console.error(`- Duración de espera: ${elapsedMinutes.toFixed(1)} minutos`);

    // Marcar status check como FAILURE
    await setCommitStatus(
      headSha,
      'failure',
      `Timeout en Sandbox de Jules (${WATCHDOG_TIMEOUT_MINUTES}m). Consulta guía en el PR.`,
      issueUrl
    );

    // Notificación con Guía de Remediación
    const failureNotice = `### 🚨 [Alerta de Sistema] Timeout en Auditoría Asíncrona de Jules

El status check \`${STATUS_CONTEXT}\` ha sido marcado como **FAILURE (🔴)** debido a que transcurrieron **${WATCHDOG_TIMEOUT_MINUTES} minutos** sin recibir el veredicto del Agente Jules.

---

#### 🔍 Diagnóstico del Fallo Asíncrono:
- **Issue Creado:** [#${issueNumber} - ${issueTitle}](${issueUrl})
- **Estado:** No se registró respuesta conclusiva con \`VEREDICTO: APROBADO\` o \`VEREDICTO: RECHAZADO\`.

#### 🛠️ Pasos de Remediación Inmediata:
1. **Verificar Vinculación del Repositorio:**
   - Ingresa a [jules.google.com/session](https://jules.google.com/session).
   - En la parte superior derecha, haz clic en **"Configure repo"** (ícono de engranaje).
   - Confirma que el repositorio \`${GITHUB_REPOSITORY}\` esté seleccionado y autorizado para la GitHub App de Jules.
2. **Verificar Cuota Diaria Disponible:**
   - En la esquina inferior izquierda de [jules.google.com](https://jules.google.com), revisa el contador **"Daily session limit"** para confirmar que no hayas alcanzado el límite de 100 sesiones.
3. **Inspeccionar la Sesión en la Web:**
   - Busca en el historial de sesiones si Jules inició la tarea \`[jules] Auditoría... para PR #${prNumber}\`.
4. **Cómo Reintentar la Auditoría sin hacer nuevos commits:**
   - Agrega la etiqueta **\`reintentar-jules\`** a este Pull Request, o ejecuta manualmente el workflow desde la pestaña Actions.

> 🔒 *El Pull Request permanece protegido e inaccesible para fusión hasta que se complete una auditoría satisfactoria.*
`;
    await postComment(prNumber, failureNotice);
    process.exit(1);
  }

  if (finalState === 'failure' || finalState === 'error') {
    console.log(`\n🛑 El veredicto de Jules resultó en ${finalState.toUpperCase()}. PR bloqueado.`);
    process.exit(1);
  }

  console.log('\n✅ Proceso completado exitosamente. Veredicto aprobado.');
  process.exit(0);
}

main().catch(err => {
  console.error(`💥 Error no controlado en el despachador: ${err.stack || err.message}`);
  process.exit(1);
});
