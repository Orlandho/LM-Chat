# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# -*- coding: utf-8 -*-

import asyncio
import omni.ext
if __package__:
    try:
        from .ui.chat_window import ChatWindow
        from .ui.models import ChatModel
        from .logic.agent_manager import AgentManager
        from .logic.chat_history import LocalChatHistoryManager
    except (ImportError, AttributeError):
        from ui.chat_window import ChatWindow
        from ui.models import ChatModel
        from logic.agent_manager import AgentManager
        from logic.chat_history import LocalChatHistoryManager
else:
    from ui.chat_window import ChatWindow
    from ui.models import ChatModel
    from logic.agent_manager import AgentManager
    from logic.chat_history import LocalChatHistoryManager
    from logic.diagnostics import diagnose_inference_failure
    from logic.logger import get_logger

logger = get_logger("Extension")


class LMChatExtension(omni.ext.IExt):
    """NVIDIA Omniverse Extension for LM-Chat: Autonomous Spatial AI Assistant & Copilot."""

    def on_startup(self, _ext_id):
        """Called when the extension is enabled."""
        print("[orlandodorival.lm_chat] LM-Chat Extension startup")

        self._history_manager = LocalChatHistoryManager()
        self._agent_manager = AgentManager()
        self._model = ChatModel(history_manager=self._history_manager)
        self._model.subscribe(self._on_model_updated)

        self._chat_window = ChatWindow(
            on_send_callback=self._on_send_message_callback,
            model=self._model,
        )
        self._chat_window.set_session_changed_callback(self._on_session_changed)
        self._chat_window.delegate.set_plan_action_callback(self._on_plan_action)

        # Sync active model configuration to AgentManager
        self._on_model_updated()

        # Auto-load latest session if available to restore conversational state
        sessions = self._history_manager.list_sessions()
        if sessions:
            latest_id = sessions[0]["session_id"]
            if self._model.load_session(latest_id):
                self._chat_window.rebuild_messages_ui()
                self._on_session_changed(self._model.current_session)

    def _on_plan_action(self, action: str):
        """Maneja las acciones interactivas de confirmación o cancelación de planes (PLAN 3)."""
        if action == "execute":
            res = self._agent_manager.execute_pending_code()
            if res.get("success"):
                msg = "✓ Código OpenUSD ejecutado exitosamente en el Stage."
                self._chat_window.add_message_bubble("assistant", msg)
                self._chat_window.finalize_last_assistant_message(msg)
            else:
                err = res.get("error_msg", "Error desconocido")
                msg = f"⚠️ Error al ejecutar en Stage: {err}"
                self._chat_window.add_message_bubble("assistant", msg)
                self._chat_window.finalize_last_assistant_message(msg)
        elif action == "cancel":
            self._agent_manager.cancel_pending_code()
            msg = "✕ Ejecución cancelada por el usuario. Escena OpenUSD intacta."
            self._chat_window.add_message_bubble("assistant", msg)
            self._chat_window.finalize_last_assistant_message(msg)

    def _on_model_updated(self):
        """Synchronizes AgentManager provider, model, execution mode and turbo mode whenever ChatModel changes."""
        if self._agent_manager and self._model:
            if hasattr(self._model, "execution_mode"):
                self._agent_manager.set_execution_mode(self._model.execution_mode)
            if hasattr(self._model, "turbo_mode"):
                self._agent_manager.set_turbo_mode(self._model.turbo_mode)

            prov = self._model.current_provider
            mod = self._model.current_model
            if prov:
                norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                sm = getattr(self._model, "settings_manager", None)
                base_url = None
                api_key = None
                if sm and norm_prov not in ("vllm", "cloud"):
                    can_name = sm._canonicalize_provider_name(prov)
                    cfg = sm.get_provider_config(can_name)
                    norm_prov = cfg.get("provider_key", norm_prov)
                    base_url = cfg.get("base_url")
                    api_key = sm.get_effective_api_key(can_name)

                valid_providers = [
                    "lm_studio", "ollama", "vllm", "cloud",
                    "openai", "claude", "anthropic", "nvidia_spark", "nemotron",
                    "gemini", "google",
                ]
                if norm_prov in valid_providers:
                    self._agent_manager.set_provider(
                        provider=norm_prov,
                        base_url=base_url,
                        model=mod,
                        api_key=api_key,
                    )

    def _on_session_changed(self, session):
        """Synchronizes AgentManager context when user switches or creates a session."""
        if self._agent_manager and session:
            self._agent_manager.load_session_messages(session.messages)
            if session.metadata:
                prov = session.metadata.get("provider")
                mod = session.metadata.get("model")
                if prov:
                    norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                    sm = getattr(self._model, "settings_manager", None)
                    base_url = None
                    api_key = None
                    if sm and norm_prov not in ("vllm", "cloud"):
                        can_name = sm._canonicalize_provider_name(prov)
                        cfg = sm.get_provider_config(can_name)
                        norm_prov = cfg.get("provider_key", norm_prov)
                        base_url = cfg.get("base_url")
                        api_key = sm.get_effective_api_key(can_name)

                    valid_providers = [
                        "lm_studio", "ollama", "vllm", "cloud",
                        "openai", "claude", "anthropic", "nvidia_spark", "nemotron",
                        "gemini", "google",
                    ]
                    if norm_prov in valid_providers:
                        self._agent_manager.set_provider(
                            provider=norm_prov,
                            base_url=base_url,
                            model=mod,
                            api_key=api_key,
                        )


    def _on_send_message_callback(self, prompt: str):
        """Callback triggered by the UI when the user clicks 'Enviar'."""
        self._chat_window.add_message_bubble("user", prompt)
        self._chat_window.add_message_bubble("assistant", "")
        self._chat_window.set_button_state(processing=True)

        # Launch the async task in the background
        asyncio.ensure_future(self._process_message_async(prompt))

    async def _process_message_async(self, prompt: str):
        """Background task to handle prompt processing without blocking UI."""
        try:
            # We pass callbacks so the AgentManager can update the UI dynamically
            final_response = await self._agent_manager.process_prompt(
                prompt,
                append_callback=self._chat_window.append_to_last_message,
                ui_feedback_callback=self._chat_window.add_message_bubble,
                reasoning_callback=self._chat_window.append_reasoning,
                confirmation_callback=lambda code, meta: self._chat_window.show_plan_confirmation_card(code, meta.get("plan", "")),
            )

            # If final response is an unformatted error message not caught by streaming
            if (final_response.startswith("Excepción") or final_response.startswith("Error")) and "Diagnóstico" not in final_response:
                diag = diagnose_inference_failure(
                    provider=self._model.current_provider if self._model else "LM Studio",
                    model=self._model.current_model if self._model else "local-model",
                    error_type="OrchestratorError",
                    raw_error=final_response,
                )
                final_response = diag.to_markdown()
                self._chat_window.append_to_last_message(final_response)

            # Finalize and persist assistant response in session history
            self._chat_window.finalize_last_assistant_message(final_response)

        except Exception as e:
            logger.error(f"Excepción grave en el orquestador: {e}", exc_info=e)
            diag = diagnose_inference_failure(
                provider=self._model.current_provider if self._model else "LM Studio",
                model=self._model.current_model if self._model else "local-model",
                error_type=type(e).__name__,
                raw_error=str(e),
            )
            diag_md = diag.to_markdown()
            self._chat_window.append_to_last_message(diag_md)
            self._chat_window.finalize_last_assistant_message(diag_md)
        finally:
            if self._chat_window:
                self._chat_window.set_button_state(processing=False)
                self._chat_window.update_status("Listo", is_loading=False)

    def on_shutdown(self):
        """Called when the extension is disabled."""
        print("[orlandodorival.lm_chat] LM-Chat Extension shutdown")
        if hasattr(self, "_chat_window") and self._chat_window:
            self._chat_window.destroy()
            self._chat_window = None
        if hasattr(self, "_model") and self._model:
            self._model.unsubscribe(self._on_model_updated)
        self._agent_manager = None
        self._history_manager = None
        self._model = None


# Backwards compatibility alias for Omniverse Kit module loader
MyExtension = LMChatExtension
