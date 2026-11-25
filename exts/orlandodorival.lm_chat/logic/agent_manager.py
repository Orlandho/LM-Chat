# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

# -*- coding: utf-8 -*-

"""
Agent Manager Module for Omniverse Agentic AI System.

Orchestrates conversation history, inference routing across providers,
structured logging, diagnostic error handling, reasoning model awareness (Plan 01),
spatial governance policies, execution mode selection (Plan 03: Immediate vs Plan & Confirm),
Turbo Mode, and MCP tools integration.
"""

import asyncio
import json
import time
import re
from typing import Optional, Callable, Dict, Any, List

from core.interfaces import (
    CancellationToken,
    ExecutionBudget,
    ExecutionMode,
    ExecutionResult,
    IExecutionEngine,
    IMCPClientRegistry,
)
from core.policies import redact_secrets
from .inference_router import InferenceRouter
from .usd_controller import USDController
from logic.logger import get_logger
from logic.diagnostics import diagnose_inference_failure, ErrorDiagnostic

# Pre-compiled regular expression pattern for Python code block extraction
_PYTHON_CODE_PATTERN = re.compile(r"```python\s*(.*?)\s*```", re.DOTALL)
logger = get_logger("AgentManager")


class AgentManager(IExecutionEngine):
    """Orchestrates conversations, provider routing, reasoning streams, and bounded execution modes."""

    def __init__(
        self,
        router: Optional[InferenceRouter] = None,
        provider: str = "lm_studio",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        execution_mode: str = ExecutionMode.IMMEDIATE.value,
        mcp_registry: Optional[IMCPClientRegistry] = None,
        usd_controller: Optional[USDController] = None,
        execution_budget: Optional[ExecutionBudget] = None,
    ) -> None:
        """
        Initializes the AgentManager with inference router, USD controller, and execution mode.

        Args:
            router (Optional[InferenceRouter]): Pre-configured InferenceRouter instance.
            provider (str): Inference provider identifier if router is not supplied.
            base_url (Optional[str]): Custom base URL if router is not supplied.
            api_key (Optional[str]): API key for authentication if router is not supplied.
            model (Optional[str]): Model name if router is not supplied.
            execution_mode (str): 'immediate' or 'plan_and_confirm'.
            mcp_registry (Optional[IMCPClientRegistry]): Registry for MCP tools.
            usd_controller (Optional[USDController]): USDController instance for stage execution.
            execution_budget (Optional[ExecutionBudget]): Presupuesto cooperativo de ejecución.
        """
        if router:
            self._router = router
        else:
            self._router = InferenceRouter(
                provider=provider, base_url=base_url, api_key=api_key, model=model
            )

        self._usd_controller = usd_controller or USDController()
        self._execution_mode: str = execution_mode
        self._execution_budget: ExecutionBudget = execution_budget or ExecutionBudget()
        self._active_cancellation_tokens: List[CancellationToken] = []
        self._pending_code: Optional[str] = None
        self._turbo_mode: bool = False
        self._mcp_registry: Optional[IMCPClientRegistry] = mcp_registry

        self._system_prompt = self._get_system_prompt_for_mode(self._execution_mode)
        self._messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        logger.info(
            f"AgentManager inicializado con router={self._router.provider} ({self._router.model}) "
            f"| modo={self._execution_mode}"
        )

    def _get_system_prompt_for_mode(self, mode: str) -> str:
        """Genera la directiva del sistema adaptada al modo de ejecución activo."""
        reversible_guidance = (
            "Usa siempre comandos reversibles mediante `controller.create_prim(...)`, "
            "`controller.transform_prim(...)`, `controller.set_prim_attribute(...)`, "
            "`controller.bind_material(...)`, `controller.group_prims(...)` o "
            "`omni.kit.commands.execute(...)` para preservar el historial Ctrl+Z/Ctrl+Y; "
            "evita escrituras directas sobre el Stage (`stage.DefinePrim`, `UsdGeom.*.Define`) "
            "y llamadas bloqueantes como `time.sleep`."
        )
        if mode == ExecutionMode.PLAN_AND_CONFIRM.value or mode == "plan_and_confirm":
            return (
                "Eres un asistente de IA avanzado para NVIDIA Omniverse. Operas en MODO PLAN & REVISIÓN (Jules / Gemini CLI style). "
                "Cuando el usuario te solicite crear, instanciar o modificar objetos 3D: "
                "1. Presenta primero una breve lista numerada con los pasos de tu plan de acción. "
                "2. Muestra el bloque de código Python dentro de un bloque delimitado por ```python y ``` "
                f"sin asumir que ya ha sido ejecutado. {reversible_guidance} "
                "Espera la confirmación interactiva del usuario antes de aplicar cambios en el Stage."
            )
        return (
            "Eres un asistente de IA avanzado para NVIDIA Omniverse. Puedes conversar libremente y ayudar al usuario con cualquier duda. "
            "SIN EMBARGO, si el usuario te pide crear, instanciar o modificar objetos 3D, debes cumplir su orden escribiendo el código en Python "
            f"dentro de un bloque delimitado por ```python y ```. {reversible_guidance} "
            "Puedes acompañar el código con una explicación amigable."
        )

    @property
    def router(self) -> InferenceRouter:
        """Returns the current InferenceRouter instance."""
        return self._router

    @property
    def usd_controller(self) -> USDController:
        """Acceso al controlador de ejecución OpenUSD."""
        return self._usd_controller

    @property
    def execution_mode(self) -> str:
        """Modo de ejecución actual ('immediate' o 'plan_and_confirm')."""
        return self._execution_mode

    def set_execution_mode(self, mode: str) -> None:
        """Actualiza el modo de ejecución y sincroniza el system prompt."""
        self._execution_mode = mode
        self._system_prompt = self._get_system_prompt_for_mode(mode)
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = self._system_prompt
        logger.info(f"Modo de ejecución actualizado a: {mode}")

    @property
    def turbo_mode(self) -> bool:
        """Indica si el modo turbo con micro-batching está activo."""
        return self._turbo_mode

    def set_turbo_mode(self, enabled: bool) -> None:
        """Habilita o deshabilita el modo turbo."""
        self._turbo_mode = enabled
        logger.info(f"Modo Turbo establecido en: {enabled}")

    @property
    def mcp_registry(self) -> Optional[IMCPClientRegistry]:
        """Registro de clientes MCP activo."""
        return self._mcp_registry

    def set_mcp_registry(self, registry: Optional[IMCPClientRegistry]) -> None:
        """Configura el registro de herramientas MCP."""
        self._mcp_registry = registry

    def set_provider(
        self,
        provider: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """Updates the underlying inference provider configuration."""
        logger.info(f"Cambiando proveedor de AgentManager a {provider} ({model})")
        self._router.set_provider(
            provider=provider, base_url=base_url, model=model, api_key=api_key
        )

    def load_session_messages(self, messages: List[Any]) -> None:
        """Sincroniza el contexto conversacional del LLM con una sesión cargada."""
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
        self._pending_code = None
        self._messages = [{"role": "system", "content": self._system_prompt}]
        logger.info("Conversación reiniciada reteniendo system prompt")

    @staticmethod
    def _coerce_execution_result(raw: Any) -> ExecutionResult:
        """Normaliza resultados dict o ExecutionResult provenientes del controlador o dobles de prueba."""
        if isinstance(raw, ExecutionResult):
            return raw
        if isinstance(raw, dict):
            return ExecutionResult(
                success=bool(raw.get("success", False)),
                error_msg=redact_secrets(raw.get("error_msg")),
                error_type=raw.get("error_type"),
                line_number=raw.get("line_number"),
                traceback_str=redact_secrets(raw.get("traceback_str")),
                cancelled=bool(raw.get("cancelled", False)),
                execution_time_ms=float(raw.get("execution_time_ms", 0.0)),
                partial_changes_rolled_back=bool(raw.get("partial_changes_rolled_back", False)),
                metadata=raw.get("metadata"),
            )
        return ExecutionResult(success=bool(raw))

    def _is_execute_code_overridden(self) -> bool:
        """Detecta si un doble de prueba sobrescribió `execute_code` directamente en la instancia."""
        ctrl = self._usd_controller
        return (
            hasattr(ctrl, "__dict__")
            and "execute_code" in ctrl.__dict__
            and "execute_code_async" not in ctrl.__dict__
        )

    def execute_script(
        self,
        python_code: str,
        dry_run: bool = False,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ExecutionResult:
        """Ejecuta código síncronamente de forma acotada (contrato IExecutionEngine)."""
        if dry_run:
            is_valid, err = self._usd_controller.policy.validate_code(python_code)
            return ExecutionResult(
                success=is_valid,
                error_msg=redact_secrets(err),
                error_type=None if is_valid else "SecurityPolicyError",
                metadata={"dry_run": True},
            )

        token = cancellation_token or CancellationToken()
        eff_budget = budget or self._execution_budget
        self._active_cancellation_tokens.append(token)
        try:
            if self._is_execute_code_overridden():
                raw = self._usd_controller.execute_code(python_code)
            else:
                raw = self._usd_controller.execute_code(
                    python_code,
                    budget=eff_budget,
                    cancellation_token=token,
                )
            return self._coerce_execution_result(raw)
        finally:
            if token in self._active_cancellation_tokens:
                self._active_cancellation_tokens.remove(token)

    async def execute_script_async(
        self,
        python_code: str,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ExecutionResult:
        """Ejecuta código de forma acotada, cancelable y sin bloquear la UI de Kit (contrato IExecutionEngine)."""
        token = cancellation_token or CancellationToken()
        eff_budget = budget or self._execution_budget
        self._active_cancellation_tokens.append(token)
        try:
            if self._is_execute_code_overridden():
                await asyncio.sleep(0)
                if token.is_cancellation_requested:
                    return ExecutionResult(
                        success=False,
                        error_msg="La ejecución fue cancelada por el usuario.",
                        error_type="ExecutionCancelledError",
                        cancelled=True,
                    )
                raw = self._usd_controller.execute_code(python_code)
                return self._coerce_execution_result(raw)

            return await self._usd_controller.execute_code_async(
                python_code,
                budget=eff_budget,
                cancellation_token=token,
            )
        finally:
            if token in self._active_cancellation_tokens:
                self._active_cancellation_tokens.remove(token)

    def format_reflection_prompt(self, failed_code: str, traceback_str: str) -> str:
        """Construye un prompt de autorreflexión seguro y redactado para corrección ReAct."""
        safe_tb = redact_secrets(traceback_str or "Error de ejecución desconocido") or ""
        return (
            f"El código falló con este error:\n{safe_tb}\n\n"
            "Por favor, analiza el problema y devuelve el código corregido "
            "dentro de las etiquetas ```python y ```, utilizando comandos reversibles "
            "(`controller.create_prim`, `controller.transform_prim`, `controller.set_prim_attribute` "
            "u `omni.kit.commands.execute`) y evitando llamadas bloqueantes."
        )

    def cancel_active_execution(self) -> bool:
        """Solicita la cancelación cooperativa de cualquier script actualmente en ejecución."""
        cancelled_any = False
        for token in list(self._active_cancellation_tokens):
            if not token.is_cancellation_requested:
                token.cancel()
                cancelled_any = True
        if cancelled_any:
            logger.info("Cancelación cooperativa solicitada para la ejecución activa.")
        return cancelled_any

    def has_pending_code(self) -> bool:
        """Retorna True si hay un bloque de código propuesto esperando confirmación del usuario."""
        return self._pending_code is not None

    def get_pending_code(self) -> Optional[str]:
        """Retorna el código propuesto pendiente de confirmación."""
        return self._pending_code

    def execute_pending_code(
        self,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta síncronamente en el Stage OpenUSD el código propuesto en Modo Plan & Confirm.
        Preferir `execute_pending_code_async` desde el bucle de eventos GUI de Kit.
        """
        if not self._pending_code:
            return {"success": False, "error_msg": "No hay código pendiente de confirmación para ejecutar."}

        code_to_exec = self._pending_code
        self._pending_code = None
        logger.info("Ejecutando código propuesto tras confirmación interactiva del usuario...")
        if self._is_execute_code_overridden():
            return self._usd_controller.execute_code(code_to_exec)
        res = self.execute_script(
            code_to_exec,
            dry_run=False,
            budget=budget,
            cancellation_token=cancellation_token,
        )
        return res.to_dict()

    async def execute_pending_code_async(
        self,
        budget: Optional[ExecutionBudget] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ExecutionResult:
        """
        Ejecuta de forma acotada, cancelable y no bloqueante el código propuesto en Modo Plan & Confirm.
        """
        if not self._pending_code:
            return ExecutionResult(
                success=False,
                error_msg="No hay código pendiente de confirmación para ejecutar.",
                error_type="ValueError",
            )

        code_to_exec = self._pending_code
        self._pending_code = None
        logger.info("Ejecutando código propuesto de forma asíncrona tras confirmación del usuario...")
        return await self.execute_script_async(
            code_to_exec,
            budget=budget,
            cancellation_token=cancellation_token,
        )

    def cancel_pending_code(self) -> Dict[str, Any]:
        """
        Descarta el código propuesto en Modo Plan & Confirm y solicita cancelar ejecución activa si existe.
        """
        active_cancelled = self.cancel_active_execution()
        self._pending_code = None
        logger.info("Propuesta de código descartada por el usuario. Escena OpenUSD intacta.")
        return {"success": True, "cancelled": True, "active_execution_cancelled": active_cancelled}

    async def process_prompt(
        self,
        prompt: str,
        append_callback: Optional[Callable[[str], None]] = None,
        ui_feedback_callback: Optional[Callable[[str, str], None]] = None,
        reasoning_callback: Optional[Callable[[str], None]] = None,
        confirmation_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> str:
        """
        Asynchronously processes a prompt, communicates with LLM via router, handles reasoning
        token separation (Plan 01), and respects execution modes (Plan 03).

        Args:
            prompt (str): The user input prompt.
            append_callback (Optional[Callable[[str], None]]): Callback to append stream chunks to UI.
            ui_feedback_callback (Optional[Callable[[str, str], None]]): Callback for UI feedback bubbles.
            reasoning_callback (Optional[Callable[[str], None]]): Callback for thinking/reasoning chunks.
            confirmation_callback (Optional[Callable[[str, Dict[str, Any]], None]]): Callback when code needs confirmation.

        Returns:
            str: Final response string or error summary.
        """
        self._pending_code = None
        self._messages.append({"role": "user", "content": prompt})
        logger.info(f"Procesando prompt de usuario: '{prompt[:60]}...'")

        # Descubrir herramientas MCP activas para exponerlas al LLM / LM Studio
        tools_payload = None
        integrations_payload = None
        raw_tools: List[Dict[str, Any]] = []
        if self._mcp_registry:
            try:
                raw_tools = await self._mcp_registry.list_available_tools()
                if raw_tools:
                    tools_payload = []
                    for t in raw_tools:
                        if "function" in t:
                            tools_payload.append({"type": "function", "function": t["function"]})
                        elif "input_schema" in t or "parameters" in t:
                            tools_payload.append({
                                "type": "function",
                                "function": {
                                    "name": t.get("name", ""),
                                    "description": t.get("description", ""),
                                    "parameters": t.get("input_schema") or t.get("parameters", {}),
                                },
                            })
                        else:
                            tools_payload.append(t)

                    # Integrations nativas para LM Studio v1 REST API
                    if self._router.provider in ("lm_studio", "lmstudio"):
                        server_names = list({t.get("server", "default") for t in raw_tools if t.get("server")})
                        integrations_payload = [
                            {"type": "plugin", "id": f"mcp/{s_name}"}
                            for s_name in server_names
                        ]
            except Exception as e:
                logger.warning(f"Error listando herramientas MCP para AgentManager: {e}")

        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                full_content = ""
                full_reasoning = ""
                error_occurred = False
                error_message = ""
                accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

                stream_kwargs: Dict[str, Any] = {
                    "turbo_mode": self._turbo_mode,
                }
                if tools_payload:
                    stream_kwargs["tools"] = tools_payload
                if integrations_payload:
                    stream_kwargs["integrations"] = integrations_payload

                # Stream response via InferenceRouter with Turbo Mode and MCP tools support
                async for chunk_obj in self._router.stream_chat_completions(
                    self._messages,
                    **stream_kwargs,
                ):
                    if chunk_obj.get("success"):
                        data = chunk_obj.get("data", {})
                        choices = data.get("choices", [{}])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content_chunk = delta.get("content") or ""
                            reasoning_chunk = delta.get("reasoning_content") or delta.get("thought") or delta.get("reasoning") or ""
                            delta_tool_calls = delta.get("tool_calls", [])

                            # Acumular tool_calls en streaming
                            if delta_tool_calls:
                                for tc in delta_tool_calls:
                                    tc_idx = tc.get("index", 0)
                                    if tc_idx not in accumulated_tool_calls:
                                        accumulated_tool_calls[tc_idx] = {
                                            "id": tc.get("id", f"call_{tc_idx}_{int(time.time())}"),
                                            "type": tc.get("type", "function"),
                                            "function": {
                                                "name": tc.get("function", {}).get("name", ""),
                                                "arguments": tc.get("function", {}).get("arguments", ""),
                                            },
                                        }
                                    else:
                                        if tc.get("id"):
                                            accumulated_tool_calls[tc_idx]["id"] = tc["id"]
                                        fn = tc.get("function", {})
                                        if fn.get("name"):
                                            accumulated_tool_calls[tc_idx]["function"]["name"] += fn["name"]
                                        if fn.get("arguments"):
                                            accumulated_tool_calls[tc_idx]["function"]["arguments"] += fn["arguments"]

                            # Enviar tokens de razonamiento al widget de pensamiento
                            if reasoning_chunk:
                                full_reasoning += reasoning_chunk
                                if reasoning_callback:
                                    try:
                                        reasoning_callback(reasoning_chunk)
                                    except Exception as cb_err:
                                        logger.debug(f"Excepción en reasoning_callback: {cb_err}")

                            # Enviar tokens de respuesta final al chat principal
                            if content_chunk:
                                full_content += content_chunk
                                if append_callback:
                                    try:
                                        append_callback(content_chunk)
                                    except Exception as cb_err:
                                        logger.debug(f"Excepción en append_callback: {cb_err}")
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
                        try:
                            append_callback(error_message)
                        except Exception as cb_err:
                            logger.debug(f"Excepción en append_callback de error: {cb_err}")
                    return error_message

                # Wait briefly for UI refresh
                await asyncio.sleep(0.1)

                # Si el LLM emitió tool_calls, ejecutarlas vía MCP Client Registry y continuar ciclo ReAct
                if accumulated_tool_calls and self._mcp_registry:
                    tool_calls_list = list(accumulated_tool_calls.values())
                    logger.info(f"AgentManager: Procesando {len(tool_calls_list)} tool_calls del LLM...")

                    self._messages.append({
                        "role": "assistant",
                        "content": full_content or "",
                        "tool_calls": tool_calls_list,
                    })

                    for tc in tool_calls_list:
                        fn = tc.get("function", {})
                        tool_name = fn.get("name", "")
                        tool_args_raw = fn.get("arguments", "")
                        try:
                            parsed_args = json.loads(tool_args_raw) if tool_args_raw else {}
                        except Exception:
                            parsed_args = {}

                        server_name = next(
                            (t.get("server", "default") for t in raw_tools if t.get("name") == tool_name),
                            "default",
                        )

                        tool_notify = f"\n\n[Invocando herramienta MCP '{tool_name}' ({server_name})...]"
                        if append_callback:
                            append_callback(tool_notify)

                        tool_res = await self._mcp_registry.call_tool(server_name, tool_name, parsed_args)

                        tool_res_str = json.dumps(tool_res)
                        self._messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": tool_name,
                            "content": tool_res_str,
                        })

                        done_notify = f"\n[Herramienta MCP '{tool_name}' completada]"
                        if append_callback:
                            append_callback(done_notify)

                    # ReAct: Continuar al siguiente turno para que el LLM sintetice la respuesta final con el resultado de la herramienta
                    await asyncio.sleep(0.1)
                    continue

                # Check for python code to execute using pre-compiled regex
                # Strip reasoning thinking tags (<think>...</think>) from DeepSeek-R1 to avoid executing draft code
                cleaned_content = re.sub(r"<think>.*?</think>", "", full_content, flags=re.DOTALL)
                matches = _PYTHON_CODE_PATTERN.findall(cleaned_content)

                if matches:
                    extracted_code = matches[-1].strip()

                    # PLAN 03: Diferenciación de Modos de Ejecución
                    is_plan_mode = (
                        self._execution_mode == ExecutionMode.PLAN_AND_CONFIRM.value
                        or self._execution_mode == "plan_and_confirm"
                    )

                    if is_plan_mode:
                        # Modo Plan & Confirmación (Jules / Gemini CLI style)
                        # No ejecutar directamente. Guardar código y solicitar confirmación interactiva al usuario.
                        self._pending_code = extracted_code
                        self._messages.append({"role": "assistant", "content": full_content})
                        logger.info("Modo Plan & Confirm: Propuesta de código retenida en espera de confirmación interactiva.")

                        if confirmation_callback:
                            plan_desc = cleaned_content.split("```python")[0].strip()
                            confirmation_callback(extracted_code, {"plan": plan_desc or full_content})

                        confirm_prompt = "\n\n[Sistema: Plan y código listos. Esperando confirmación para ejecutar en escena...]"
                        if append_callback:
                            append_callback(confirm_prompt)

                        return full_content + confirm_prompt

                    # Modo Inmediato (⚡ Fast Act / Autónomo) — ejecución acotada y cancelable
                    logger.info("Modo Inmediato: Detectado bloque de código OpenUSD. Ejecutando de forma acotada...")
                    exec_result = await self.execute_script_async(
                        extracted_code,
                        budget=self._execution_budget,
                    )

                    if exec_result.get("success"):
                        self._messages.append({"role": "assistant", "content": full_content})
                        success_msg = "\n\n[Sistema: Código ejecutado exitosamente]"
                        if append_callback:
                            append_callback(success_msg)
                        logger.info("Código OpenUSD ejecutado con éxito")
                        return full_content + success_msg
                    elif exec_result.get("cancelled"):
                        self._messages.append({"role": "assistant", "content": full_content})
                        rb_note = (
                            " Cambios parciales revertidos."
                            if exec_result.get("partial_changes_rolled_back")
                            else ""
                        )
                        cancel_msg = f"\n\n[Sistema: Ejecución cancelada por el usuario.{rb_note}]"
                        if append_callback:
                            append_callback(cancel_msg)
                        logger.info("Ejecución OpenUSD cancelada cooperativamente por el usuario.")
                        return full_content + cancel_msg
                    else:
                        error_msg = redact_secrets(exec_result.get("error_msg")) or "Error desconocido"
                        error_context = redact_secrets(exec_result.get("traceback_str")) or error_msg
                        logger.warning(f"Error en ejecución OpenUSD: {error_msg}")

                        if attempt < max_retries:
                            retry_msg = f"\n\n[Sistema: Error detectado. Intento de autocorrección {attempt + 1} de {max_retries}...]"
                            if append_callback:
                                append_callback(retry_msg)

                            self._messages.append({"role": "assistant", "content": full_content})
                            self._messages.append({
                                "role": "user",
                                "content": self.format_reflection_prompt(extracted_code, error_context),
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
                    try:
                        append_callback(diag_md)
                    except Exception as cb_err:
                        logger.debug(f"Excepción en append_callback de diagnóstico: {cb_err}")
                return diag_md

        return "Flujo finalizado inesperadamente."
