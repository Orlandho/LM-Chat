/**
 * jules-verdict-processor.js
 * 
 * Procesador reactivo de veredictos emitidos por el Agente Jules en su Sandbox Virtual
 * para el repositorio LM-Chat (NVIDIA Omniverse).
 */

const fs = require('fs');

const GITHUB_TOKEN = process.env.GITHUB_TOKEN || process.env.GITHUB_PERSONAL_ACCESS_TOKEN;
const GITHUB_REPOSITORY = process.env.GITHUB_REPOSITORY || 'Orlandho/LM-Chat';
const GITHUB_API_URL = process.env.GITHUB_API_URL || 'https://api.github.com';

const STATUS_CONTEXT = 'Veredicto de Auditoría en Sandbox de Jules';

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
    'User-Agent': 'LM-Chat-Jules-Verdict-Processor/1.0',
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

// Actualiza el status check del commit
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

// Extrae metadatos del comentario oculto en el Issue
function parseMetadata(issueBody) {
  if (!issueBody) return null;
  const match = issueBody.match(/<!--\s*JULES_AUDIT_METADATA\s*([\s\S]*?)-->/);
  if (!match) return null;

  const metadata = {};
  const lines = match[1].split('\n');
  for (const line of lines) {
    const parts = line.split(':');
    if (parts.length >= 2) {
      const key = parts[0].trim();
      const val = parts.slice(1).join(':').trim();
      metadata[key] = val;
    }
  }
  return metadata;
}

async function main() {
  console.log('================================================================');
  console.log('🤖 PROCESANDO COMENTARIO DEL AGENTE JULES PARA VEREDICTO DE LM-CHAT');
  console.log('================================================================');

  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !fs.existsSync(eventPath)) {
    console.error('❌ No se encontró GITHUB_EVENT_PATH.');
    process.exit(1);
  }

  const eventData = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
  const issue = eventData.issue;
  const comment = eventData.comment;

  if (!issue || !comment) {
    console.log('ℹ️ El evento no contiene issue o comment. Finalizando.');
    process.exit(0);
  }

  const metadata = parseMetadata(issue.body);
  if (!metadata || !metadata.PR_NUMBER || !metadata.COMMIT_SHA) {
    console.log('ℹ️ El Issue no contiene metadatos de auditoría de Jules. Ignorando.');
    process.exit(0);
  }

  const prNumber = metadata.PR_NUMBER;
  const commitSha = metadata.COMMIT_SHA;
  const branch = metadata.BRANCH;
  const commentAuthor = comment.user?.login || 'desconocido';
  const commentBody = comment.body || '';
  const commentUrl = comment.html_url || issue.html_url;

  console.log(`📋 Metadatos identificados: PR #${prNumber} | Commit: ${commitSha} | Rama: ${branch}`);

  const isApproved = /(?:VEREDICTO|VERDICT):\s*(?:APROBADO|APPROVED)/i.test(commentBody);
  const isRejected = /(?:VEREDICTO|VERDICT):\s*(?:RECHAZADO|REJECTED|FALLIDO|FAILED)/i.test(commentBody);

  if (isApproved) {
    console.log('🎉 [VEREDICTO DETECTADO]: APROBADO por el Agente Jules.');

    await setCommitStatus(
      commitSha,
      'success',
      '✅ Aprobado por el Agente Jules en entorno virtual',
      commentUrl
    );

    const prApprovalComment = `### 🟢 [Agente Jules] Auditoría Virtual APROBADA

El Agente Jules ha completado la auditoría de este Pull Request en su entorno virtual con resultado favorable:
- **Veredicto:** \`VEREDICTO: APROBADO\`
- **Status Check:** \`${STATUS_CONTEXT}\` -> **SUCCESS (🟢 Aprobado)**
- **Detalle de la Evaluación:** [Ver análisis completo en el Issue #${issue.number}](${commentUrl})

> ✨ *La validación en sandbox de NVIDIA Omniverse concluyó con éxito. Requisito de protección desbloqueado.*
`;
    await postComment(prNumber, prApprovalComment);

  } else if (isRejected) {
    console.log('🛑 [VEREDICTO DETECTADO]: RECHAZADO por el Agente Jules.');

    await setCommitStatus(
      commitSha,
      'failure',
      '❌ Rechazado por el Agente Jules. Se detectaron problemas en el código.',
      commentUrl
    );

    const prRejectionComment = `### 🔴 [Agente Jules] Auditoría Virtual RECHAZADA

El Agente Jules ha analizado la rama \`${branch}\` en su sandbox virtual y **ha detectado inconsistencias o fallos técnicos**:
- **Veredicto:** \`VEREDICTO: RECHAZADO\`
- **Status Check:** \`${STATUS_CONTEXT}\` -> **FAILURE (🔴 Bloqueado)**
- **Reporte Completo:** [Ver hallazgos detallados en el Issue #${issue.number}](${commentUrl})
`;
    await postComment(prNumber, prRejectionComment);

  } else {
    console.log('ℹ️ Comentario recibido sin veredicto conclusivo. Se mantiene en PENDING.');
  }

  process.exit(0);
}

main().catch(err => {
  console.error(`💥 Error no controlado en el procesador de veredictos: ${err.stack || err.message}`);
  process.exit(1);
});
