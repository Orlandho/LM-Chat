# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Motor de Diagnóstico Inteligente de Fallos e Inferencia para LM-Chat™.

Analiza exhaustivamente las causas de errores durante la comunicación con
modelos LLM (locales o en la nube), clasificándolos con precisión y generando
reportes estructurados con instrucciones accionables paso a paso para el usuario
en lugar de mensajes genéricos de error.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class DiagnosticCategory(str, Enum):
    """Categorías estándar de diagnóstico de incidencias de inferencia."""
    CONNECTION_REFUSED = "connection_refused"
    AUTHENTICATION_ERROR = "authentication_error"
    MODEL_NOT_FOUND = "model_not_found"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    EMPTY_RESPONSE = "empty_response"
    CONFIGURATION_ERROR = "configuration_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorDiagnostic:
    """Diagnóstico detallado y accionable de un fallo de inferencia o conexión."""

    category: DiagnosticCategory
    title: str
    summary: str
    provider: str
    model: str
    base_url: str
    troubleshooting_steps: List[str]
    technical_details: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = "open_settings"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        """Genera una tarjeta de diagnóstico visual en formato Markdown para la UI."""
        steps_md = "\n".join(f"{i+1}. {step}" for i, step in enumerate(self.troubleshooting_steps))
        
        status_code = self.technical_details.get("status_code")
        status_badge = f"`HTTP {status_code}`" if status_code else "`Red / Conexión`"

        raw_err = self.technical_details.get("raw_error")
        raw_err_block = f"\n> **Detalle del servidor:** `{raw_err}`" if raw_err else ""

        return (
            f"### ⚠️ Diagnóstico LM-Chat: {self.title}\n\n"
            f"**Estado:** {status_badge} | **Proveedor:** `{self.provider}` | **Modelo:** `{self.model}`\n\n"
            f"**¿Por qué ocurrió esto?**\n"
            f"{self.summary}{raw_err_block}\n\n"
            f"**Servidor consultado:** `{self.base_url}`\n\n"
            f"**Pasos recomendados para solucionarlo:**\n"
            f"{steps_md}\n\n"
            f"*💡 Puedes pulsar el botón **⚙ Settings** en la barra superior para revisar la configuración.*"
        )

    def to_plain_text(self) -> str:
        """Genera una versión en texto plano para consolas CLI y portapapeles."""
        lines = [
            "=" * 65,
            f"[DIAGNÓSTICO LM-Chat] {self.title}",
            "=" * 65,
            f"Proveedor: {self.provider}",
            f"Modelo:    {self.model}",
            f"Endpoint:  {self.base_url}",
            f"Causa:     {self.summary}",
        ]
        if self.technical_details.get("raw_error"):
            lines.append(f"Detalle:   {self.technical_details['raw_error']}")
        lines.append("\nPasos recomendados:")
        for i, step in enumerate(self.troubleshooting_steps, 1):
            lines.append(f"  {i}. {step}")
        lines.append("=" * 65)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el diagnóstico a un diccionario nativo."""
        return {
            "category": self.category.value,
            "title": self.title,
            "summary": self.summary,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "troubleshooting_steps": self.troubleshooting_steps,
            "technical_details": self.technical_details,
            "suggested_action": self.suggested_action,
            "timestamp": self.timestamp,
        }


def _safe_str(val: Any) -> str:
    """Convierte de forma segura cualquier valor a cadena de caracteres primitiva."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return ""
    if isinstance(val, Exception):
        return str(val)
    type_name = type(val).__name__
    if "Mock" in type_name or "coroutine" in type_name:
        return ""
    try:
        s = str(val)
        if s.startswith("<") and ("Mock" in s or "coroutine" in s):
            return ""
        return s
    except Exception:
        return ""


def diagnose_inference_failure(
    provider: str,
    model: str,
    base_url: str = "",
    error_type: Optional[str] = None,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    raw_error: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ErrorDiagnostic:
    """Analiza los metadatos de un error y produce un diagnóstico específico y accionable.

    Args:
        provider: Identificador o nombre del proveedor (ej. 'lm_studio', 'ollama', 'openai', 'claude').
        model: Identificador del modelo solicitado (ej. 'local-model', 'gpt-4o', 'deepseek-r1:8b').
        base_url: URL base configurada.
        error_type: Tipo de error reportado ('ConnectionError', 'HTTPError', 'TimeoutError', etc.).
        status_code: Código de estado HTTP si aplica.
        error_message: Mensaje legible del error.
        raw_error: Mensaje crudo retornado por el servidor o la excepción.
        timeout: Timeout configurado en segundos.

    Returns:
        ErrorDiagnostic: Diagnóstico estructurado y detallado.
    """
    prov_clean = _safe_str(provider or "LM Studio").strip().lower()
    model_clean = _safe_str(model or "desconocido").strip() or "desconocido"
    url_clean = _safe_str(base_url).strip()
    raw_s = _safe_str(raw_error)
    err_s = _safe_str(error_message)
    msg = (err_s or raw_s).lower()
    raw = raw_s or err_s

    # Determinar si el proveedor es un servidor local
    is_local_provider = any(k in prov_clean for k in ("lm_studio", "lmstudio", "lm studio", "ollama", "vllm", "localhost", "127.0.0.1"))

    # 1. Error de Conexión Rehusada / Servidor Local Apagado
    if (
        error_type == "ConnectionError"
        or "connection refused" in msg
        or "connectorerror" in msg
        or "cannot connect" in msg
        or "winerror 10061" in msg
        or "err_connection_refused" in msg
    ):
        if "ollama" in prov_clean:
            title = "Servidor Ollama no detectado o apagado"
            summary = (
                f"No se pudo conectar al daemon de Ollama en {base_url}. "
                "El servicio no está en ejecución o el puerto está ocupado."
            )
            steps = [
                "Verifica que Ollama esté en ejecución abriendo una terminal y ejecutando `ollama serve`.",
                f"Confirma que el modelo `{model}` esté descargado con `ollama pull {model}` o prueba un modelo de razonamiento open-weight con `ollama pull deepseek-r1:8b` o `ollama pull qwen2.5-coder:7b`.",
                f"Comprueba en el navegador o curl que `{base_url}` o `http://localhost:11434` responda.",
                "En LM-Chat, abre '⚙ Settings' y pulsa 'Probar Conexión' para validar que el servicio esté listo.",
            ]
        elif any(k in prov_clean for k in ("lm_studio", "lmstudio", "lm studio")):
            title = "Servidor LM Studio apagado o inalcanzable"
            summary = (
                f"No se pudo conectar a LM Studio en {base_url}. "
                "La aplicación LM Studio no tiene encendido el servidor local de inferencia."
            )
            steps = [
                "Abre la aplicación de escritorio LM Studio.",
                "En la barra lateral izquierda, haz clic en la pestaña de 'Local Server' (icono <-> o Developer).",
                "Asegúrate de que haya un modelo cargado en memoria (ej. `qwen2.5-coder-7b` o `local-model`).",
                "Presiona el botón verde 'Start Server' y verifica que el puerto sea el 1234.",
                "Regresa a LM-Chat y abre '⚙ Settings' -> 'Probar Conexión'.",
            ]
        else:
            title = "Servidor de Inferencia no disponible o desconectado"
            summary = (
                f"No se pudo establecer conexión HTTP con el servicio ({provider}) en {base_url}."
            )
            steps = [
                f"Verifica que el servicio esté ejecutándose localmente o en la red en `{base_url}`.",
                "Revisa que tu firewall o antivirus no esté bloqueando las peticiones locales.",
                "Comprueba la URL configurada en '⚙ Settings' y presiona 'Probar Conexión'.",
            ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.CONNECTION_REFUSED,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"status_code": status_code, "raw_error": raw, "error_type": error_type},
            suggested_action="open_settings",
        )

    # 2. Error de Autenticación / API Key (HTTP 401 o 403)
    if status_code in (401, 403) or "unauthorized" in msg or "forbidden" in msg or "invalid api key" in msg or "incorrect api key" in msg:
        env_var = "OPENAI_API_KEY"
        if "claude" in prov_clean or "anthropic" in prov_clean:
            env_var = "ANTHROPIC_API_KEY"
        elif "nvidia" in prov_clean or "spark" in prov_clean:
            env_var = "NVIDIA_API_KEY"
        elif "gemini" in prov_clean:
            env_var = "GEMINI_API_KEY"

        title = f"Autenticación fallida con {provider} (HTTP {status_code or 401})"
        summary = (
            f"El servidor rechazó la solicitud debido a credenciales faltantes o clave de API inválida."
        )
        steps = [
            f"Abre la ventana '⚙ Settings' en LM-Chat y escribe tu clave de API en el campo 'API Key'.",
            f"O define la variable de entorno del sistema `{env_var}` con tu clave y reinicia Omniverse.",
            "Verifica que la clave no tenga espacios adicionales al inicio o final.",
            "Comprueba en el panel de tu proveedor que tu cuenta tenga créditos activos y esté habilitada.",
        ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.AUTHENTICATION_ERROR,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"status_code": status_code or 401, "raw_error": raw, "expected_env": env_var},
            suggested_action="open_settings",
        )

    # 3. Modelo no encontrado o no cargado (HTTP 404)
    if status_code == 404 or "model not found" in msg or "model does not exist" in msg or "not loaded" in msg:
        title = f"Modelo '{model}' no encontrado o no cargado en memoria (HTTP 404)"
        summary = (
            f"El servidor en {base_url} respondió pero indicó que el modelo solicitado (`{model}`) "
            "no está disponible o no ha sido cargado en el runtime."
        )
        if "ollama" in prov_clean:
            steps = [
                f"Descarga el modelo ejecutando en tu terminal: `ollama pull {model}`.",
                "O prueba un modelo moderno para agentes locales como `ollama pull deepseek-r1:8b` o `ollama pull qwen2.5-coder:7b`.",
                "Selecciona el modelo correcto en el selector desplegable superior de LM-Chat.",
            ]
        elif any(k in prov_clean for k in ("lm_studio", "lmstudio", "lm studio")):
            steps = [
                f"En LM Studio, ve a la sección de búsqueda y asegúrate de haber descargado el modelo `{model}`.",
                "Carga el modelo en memoria RAM/VRAM en la barra superior de LM Studio antes de enviar mensajes.",
                "Si estás usando el identificador genérico `local-model`, LM Studio usará el modelo que tengas cargado.",
            ]
        else:
            steps = [
                f"Verifica que el identificador del modelo `{model}` sea correcto para {provider}.",
                "Para OpenAI, prueba modelos como `gpt-4o`, `gpt-4o-mini`, `o3-mini` o `gpt-4.5-preview`.",
                "Para Claude, prueba modelos como `claude-3-7-sonnet-latest`, `claude-3-5-sonnet-latest` o `claude-3-5-haiku-latest`.",
                "Puedes cambiar de modelo en el desplegable superior o agregar uno personalizado en '⚙ Settings'.",
            ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.MODEL_NOT_FOUND,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"status_code": 404, "raw_error": raw},
            suggested_action="switch_model",
        )

    # 4. Límite de Cuota o Rate Limit Excedido (HTTP 429)
    if status_code == 429 or "rate limit" in msg or "quota" in msg or "too many requests" in msg:
        title = f"Límite de peticiones o cuota excedida en {provider} (HTTP 429)"
        summary = (
            f"Has alcanzado el límite de velocidad (RPM/TPM) o se ha agotado el saldo/cuota de tu cuenta en {provider}."
        )
        steps = [
            "Espera unos segundos antes de enviar una nueva consulta para permitir que se restablezca el límite de velocidad.",
            "Revisa el panel de control y facturación de tu proveedor para verificar tu saldo disponible.",
            "Si necesitas inferencia continua ilimitada sin costo, cambia a un proveedor local como LM Studio u Ollama con modelos locales (`deepseek-r1:8b`, `qwen2.5-coder:7b`).",
        ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.RATE_LIMIT_EXCEEDED,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"status_code": 429, "raw_error": raw},
            suggested_action="check_billing",
        )

    # 5. Tiempo de Espera Agotado / Timeout
    if (
        error_type == "TimeoutError"
        or "timeout" in msg
        or status_code in (504, 408)
        or "timed out" in msg
    ):
        t_val = timeout or 600.0
        title = f"Tiempo de espera de inferencia agotado ({t_val:.0f}s)"
        summary = (
            f"El servidor en {base_url} tardó más de {t_val:.0f} segundos en generar una respuesta."
        )
        if is_local_provider:
            steps = [
                "Los modelos locales grandes (ej. 30B/70B) pueden tardar en cargar sus pesos en la VRAM de la GPU en la primera consulta (arranque en frío).",
                "Verifica en el Administrador de Tareas que tu GPU o CPU no esté al 100% saturada o en swap de memoria.",
                "En '⚙ Settings', puedes aumentar el tiempo de timeout o seleccionar un modelo más ágil como `qwen2.5-coder:7b` o `llama-3.2-3b`.",
            ]
        else:
            steps = [
                "El servicio en la nube tardó demasiado en responder debido a alta demanda o latencia de red.",
                "Comprueba la estabilidad de tu conexión a Internet.",
                "Reintenta enviar el mensaje en unos instantes.",
            ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.TIMEOUT,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"timeout_seconds": t_val, "status_code": status_code, "raw_error": raw},
            suggested_action="check_server",
        )

    # 6. Error Interno del Servidor / Colapso o Falta de VRAM (HTTP 500, 502, 503)
    if (status_code and status_code >= 500) or "internal server error" in msg or "cuda out of memory" in msg or "oom" in msg:
        is_oom = "out of memory" in msg or "cuda" in msg or "vram" in msg
        title = f"Fallo interno en el motor de inferencia ({'Falta de VRAM GPU' if is_oom else f'HTTP {status_code}'})"
        summary = (
            f"El servidor backend de {provider} experimentó un error crítico interno durante el procesamiento del prompt."
        )
        if is_oom:
            steps = [
                "Tu tarjeta gráfica se ha quedado sin memoria de video (VRAM) suficiente para el modelo o el contexto actual.",
                "En LM Studio u Ollama, reduce el tamaño de contexto (`max_tokens`) o el número de capas GPU descargadas.",
                "Carga una cuantización más ligera (ej. Q4_K_M) o un modelo optimizado como `qwen2.5-coder:7b` o `deepseek-r1:8b`.",
            ]
        else:
            steps = [
                "Revisa la consola o ventana del terminal donde se ejecuta tu servidor local para ver el traceback exacto.",
                "Reinicia el servidor local de inferencia (LM Studio / Ollama).",
                "Si usas un servicio en la nube, comprueba el estado oficial de la plataforma de la API.",
            ]

        return ErrorDiagnostic(
            category=DiagnosticCategory.SERVER_ERROR,
            title=title,
            summary=summary,
            provider=provider,
            model=model,
            base_url=base_url,
            troubleshooting_steps=steps,
            technical_details={"status_code": status_code, "raw_error": raw, "is_oom": is_oom},
            suggested_action="check_server",
        )

    # 7. URL Inválida o Esquema No Soportado
    if "invalid base_url" in msg or "scheme" in msg or (url_clean and not (url_clean.startswith("http://") or url_clean.startswith("https://"))):
        title = "Dirección de servidor (Base URL) inválida o malformada"
        summary = f"La URL configurada '{url_clean}' no es válida. Debe comenzar estrictamente con 'http://' o 'https://'."
        steps = [
            "Abre '⚙ Settings' y verifica el campo 'URL Base'.",
            "Usa uno de los botones de presets de 1 clic (ej. 'Local (:1234)' o 'Local (:11434)').",
            "Guarda los cambios y prueba nuevamente.",
        ]
        return ErrorDiagnostic(
            category=DiagnosticCategory.CONFIGURATION_ERROR,
            title=title,
            summary=summary,
            provider=provider or "LM Studio",
            model=model_clean,
            base_url=url_clean,
            troubleshooting_steps=steps,
            technical_details={"raw_error": raw},
            suggested_action="open_settings",
        )

    # 8. Fallo Genérico / Desconocido
    title = f"Error en la comunicación con {provider or 'LM Studio'}"
    summary = f"Ocurrió un problema inesperado al procesar la solicitud con el modelo `{model_clean}`."
    steps = [
        "Verifica que el servicio seleccionado en el encabezado esté correctamente configurado.",
        "Abre '⚙ Settings' y presiona 'Probar Conexión' para obtener un diagnóstico de red en tiempo real.",
        "Revisa los logs del sistema para más detalles técnicos.",
    ]

    return ErrorDiagnostic(
        category=DiagnosticCategory.UNKNOWN,
        title=title,
        summary=summary,
        provider=provider or "LM Studio",
        model=model_clean,
        base_url=url_clean,
        troubleshooting_steps=steps,
        technical_details={"status_code": status_code, "raw_error": raw, "error_type": error_type},
        suggested_action="open_settings",
    )
