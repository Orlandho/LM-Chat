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


class LMChatExtension(omni.ext.IExt):
    """NVIDIA Omniverse Extension for LM-Chat: Autonomous Spatial AI Assistant & Copilot."""

    def on_startup(self, _ext_id):
        """Called when the extension is enabled."""
        print("[omni.lm_chat] LM-Chat Extension startup")

        self._history_manager = LocalChatHistoryManager()
        self._agent_manager = AgentManager()
        self._model = ChatModel(history_manager=self._history_manager)
        self._model.subscribe(self._on_model_updated)

        self._chat_window = ChatWindow(
            on_send_callback=self._on_send_message_callback,
            model=self._model,
        )
        self._chat_window.set_session_changed_callback(self._on_session_changed)

        # Sync active model configuration to AgentManager
        self._on_model_updated()

        # Auto-load latest session if available to restore conversational state
        sessions = self._history_manager.list_sessions()
        if sessions:
            latest_id = sessions[0]["session_id"]
            if self._model.load_session(latest_id):
                self._chat_window.rebuild_messages_ui()
                self._on_session_changed(self._model.current_session)

    def _on_model_updated(self):
        """Synchronizes AgentManager provider and model whenever ChatModel changes."""
        if self._agent_manager and self._model:
            prov = self._model.current_provider
            mod = self._model.current_model
            if prov:
                norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                if norm_prov in ["lm_studio", "ollama", "vllm", "cloud"]:
                    self._agent_manager.set_provider(provider=norm_prov, model=mod)

    def _on_session_changed(self, session):
        """Synchronizes AgentManager context when user switches or creates a session."""
        if self._agent_manager and session:
            self._agent_manager.load_session_messages(session.messages)
            if session.metadata:
                prov = session.metadata.get("provider")
                mod = session.metadata.get("model")
                if prov:
                    norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                    if norm_prov in ["lm_studio", "ollama", "vllm", "cloud"]:
                        self._agent_manager.set_provider(provider=norm_prov, model=mod)

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
            )

            # If final response is an error message not caught by streaming
            if final_response.startswith("Excepción") or final_response.startswith("Error"):
                self._chat_window.append_to_last_message(f"\n\n[Error: {final_response}]")
                final_response = f"{final_response}\n\n[Error: {final_response}]"

            # Finalize and persist assistant response in session history
            self._chat_window.finalize_last_assistant_message(final_response)

        except Exception as e:
            error_msg = f"\n\nExcepción grave en el orquestador: {str(e)}"
            print(f"[omni.lm_chat] {error_msg}")
            self._chat_window.append_to_last_message(error_msg)
            self._chat_window.finalize_last_assistant_message(error_msg)
        finally:
            if self._chat_window:
                self._chat_window.set_button_state(processing=False)
                self._chat_window.update_status("Listo", is_loading=False)

    def on_shutdown(self):
        """Called when the extension is disabled."""
        print("[omni.lm_chat] LM-Chat Extension shutdown")
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
