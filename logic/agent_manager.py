# -*- coding: utf-8 -*-

"""
Agent Manager Module for Omniverse Agentic AI System.

Orchestrates conversation history, inference routing across providers,
structured logging, diagnostic error handling, and the ReAct Reflection Loop
for autonomous OpenUSD code generation and execution.
"""

import asyncio
import re
from typing import Optional, Callable, Dict, Any, List
from .inference_router import InferenceRouter
from .usd_controller import USDController
from logic.logger import get_logger
from logic.diagnostics import diagnose_inference_failure, ErrorDiagnostic

# Pre-compiled regular expression pattern for Python code block extraction
_PYTHON_CODE_PATTERN = re.compile(r"```python\s*(.*?)\s*```", re.DOTALL)
logger = get_logger("AgentManager")


class AgentManager:
    """Orchestrates conversations, provider routing, and ReAct Reflection Loop logic."""

    def __init__(
        self,
        router: Optional[InferenceRouter] = None,
        provider: str = "lm_studio",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initializes the AgentManager with inference router and USD controller.

        Args:
            router (Optional[InferenceRouter]): Pre-configured InferenceRouter instance.
            provider (str): Inference provider identifier if router is not supplied.
            base_url (Optional[str]): Custom base URL if router is not supplied.
            api_key (Optional[str]): API key for authentication if router is not supplied.
            model (Optional[str]): Model name if router is not supplied.
        """
        if router:
            self._router = router
        else:
            self._router = InferenceRouter(
                provider=provider, base_url=base_url, api_key=api_key, model=model
            )

        self._usd_controller = USDController()
        self._system_prompt = (
            "Eres un asistente de IA avanzado para NVIDIA Omniverse. Puedes conversar libremente y ayudar al usuario con cualquier duda. "
            "SIN EMBARGO, si el usuario te pide crear, instanciar o modificar objetos 3D, debes cumplir su orden escribiendo el código en Python "
            "usando omni.usd y pxr dentro de un bloque delimitado por ```python y ```. Puedes acompañar el código con una explicación amigable."
        )
        self._messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        logger.info(f"AgentManager inicializado con router={self._router.provider} ({self._router.model})")

    @property
    def router(self) -> InferenceRouter:
        """Returns the current InferenceRouter instance."""
        return self._router

    def set_provider(
        self,
        provider: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Updates the underlying inference provider configuration.

        Args:
            provider (str): Provider identifier ('lm_studio', 'ollama', 'vllm', 'cloud', etc.).
            base_url (Optional[str]): Base URL override.
            model (Optional[str]): Model identifier.
            api_key (Optional[str]): API key for cloud providers.
        """
        logger.info(f"Cambiando proveedor de AgentManager a {provider} ({model})")
        self._router.set_provider(
            provider=provider, base_url=base_url, model=model, api_key=api_key
        )

    def load_session_messages(self, messages: List[Any]) -> None:
        """Sincroniza el contexto conversacional del LLM con una sesión cargada.

        Args:
            messages (List[Any]): Lista de ChatMessage o diccionarios con rol y contenido.
        """
        self._messages = [{"role": "system", "content": self._system_prompt}]
        for msg in messages:
            if hasattr(msg, "role") and hasattr(msg, "content"):
                role = msg.role
                content = msg.content
            elif isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
            else:
                continue

            if role in ("user", "assistant"):
                self._messages.append({"role": role, "content": content})
            elif role == "system" and content and content != self._system_prompt:
                self._messages[0]["content"] = content

        logger.debug(f"Contexto conversacional cargado: {len(self._messages)} mensajes en memoria")

    def reset_conversation(self) -> None:
        """Reinicia el contexto de conversación reteniendo el system prompt."""
        self._messages = [{"role": "system", "content": self._system_prompt}]
        logger.info("Conversación reiniciada reteniendo system prompt")

    async def process_prompt(
        self,
        prompt: str,
        append_callback: Optional[Callable[[str], None]] = None,
        ui_feedback_callback: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """
        Asynchronously processes a prompt, communicates with LLM via router, and handles ReAct loop.

        Args:
            prompt (str): The user input prompt.
            append_callback (Optional[Callable[[str], None]]): Callback to append stream chunks to UI.
            ui_feedback_callback (Optional[Callable[[str, str], None]]): Callback for UI feedback bubbles.

        Returns:
            str: Final response string or error summary.
        """
        self._messages.append({"role": "user", "content": prompt})
        logger.info(f"Procesando prompt de usuario: '{prompt[:60]}...'")

        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                full_content = ""
                error_occurred = False
                error_message = ""

                # Stream response via InferenceRouter
                async for chunk_obj in self._router.stream_chat_completions(self._messages):
                    if chunk_obj.get("success"):
                        data = chunk_obj.get("data", {})
                        choices = data.get("choices", [{}])
                        if choices:
                            delta = choices[0].get("delta", {})
                            chunk = delta.get("content", "")

                            if chunk:
                                full_content += chunk
                                if append_callback:
                                    append_callback(chunk)
                    else:
                        error_occurred = True
                        error_type = chunk_obj.get("error_type")
                        diagnostic_md = chunk_obj.get("diagnostic_md")

                        if diagnostic_md:
                            error_message = diagnostic_md
                        elif error_type == "HTTPError":
                            error_message = chunk_obj.get("message", "Error de HTTP")
                        elif error_type == "ConnectionError":
                            error_message = chunk_obj.get("message", "Error de conexión")
                        elif error_type == "TimeoutError":
                            error_message = chunk_obj.get("message", "Tiempo de espera agotado")
                        else:
                            raw_msg = chunk_obj.get("message", "Fallo desconocido")
                            error_message = f"Excepción en petición LLM: {raw_msg}"

                        logger.warning(
                            f"Fallo en inferencia streaming [{error_type}]: {chunk_obj.get('message', '')[:100]}"
                        )
                        break

                if error_occurred:
                    logger.error(f"Inferencia abortada por error en el proveedor {self._router.provider}")
                    if append_callback:
                        append_callback(error_message)
                    return error_message

                # Wait briefly for UI refresh
                await asyncio.sleep(0.1)

                # Check for python code to execute using pre-compiled regex
                # Strip reasoning thinking tags (<think>...</think>) from DeepSeek-R1 to avoid executing draft code
                cleaned_content = re.sub(r"<think>.*?</think>", "", full_content, flags=re.DOTALL)
                matches = _PYTHON_CODE_PATTERN.findall(cleaned_content)
                if matches:
                    extracted_code = matches[-1].strip()
                    logger.info("Detectado bloque de código OpenUSD generado por el modelo. Ejecutando...")
                    exec_result = self._usd_controller.execute_code(extracted_code)

                    if exec_result.get("success"):
                        self._messages.append({"role": "assistant", "content": full_content})
                        success_msg = "\n\n[Sistema: Código ejecutado exitosamente]"
                        if append_callback:
                            append_callback(success_msg)
                        logger.info("Código OpenUSD ejecutado con éxito")
                        return full_content + success_msg
                    else:
                        error_msg = exec_result.get("error_msg")
                        logger.warning(f"Error en ejecución OpenUSD: {error_msg}")

                        if attempt < max_retries:
                            retry_msg = f"\n\n[Sistema: Error detectado. Intento de autocorrección {attempt + 1} de {max_retries}...]"
                            if append_callback:
                                append_callback(retry_msg)

                            self._messages.append({"role": "assistant", "content": full_content})
                            self._messages.append({
                                "role": "user",
                                "content": (
                                    f"El código falló con este error: {error_msg}. "
                                    "Por favor, analiza el problema y devuelve el código corregido "
                                    "dentro de las etiquetas ```python y ```."
                                ),
                            })

                            # Give UI time to update before next attempt
                            await asyncio.sleep(0.5)

                            if ui_feedback_callback:
                                ui_feedback_callback("assistant", "")
                        else:
                            final_err = f"\n\n[Sistema: Se agotaron los reintentos. Último error: {error_msg}]"
                            if append_callback:
                                append_callback(final_err)
                            logger.error(f"Reintentos agotados en ReAct loop: {error_msg}")
                            return full_content + final_err
                else:
                    # Normal conversation without code
                    self._messages.append({"role": "assistant", "content": full_content})
                    return full_content

            except Exception as e:
                logger.error(f"Error asíncrono no controlado en AgentManager: {e}", exc_info=e)
                diag = diagnose_inference_failure(
                    provider=self._router.provider,
                    model=self._router.model,
                    base_url=self._router.base_url,
                    error_type=type(e).__name__,
                    raw_error=str(e),
                )
                diag_md = diag.to_markdown()
                if append_callback:
                    append_callback(diag_md)
                return diag_md

        return "Flujo finalizado inesperadamente."
