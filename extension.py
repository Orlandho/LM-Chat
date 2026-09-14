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
from .ui.chat_window import ChatWindow
from .logic.agent_manager import AgentManager

class LMChatExtension(omni.ext.IExt):
    """NVIDIA Omniverse Extension for LM-Chat: Autonomous Spatial AI Assistant & Copilot."""

    def on_startup(self, _ext_id):
        """Called when the extension is enabled."""
        print("[omni.lm_chat] LM-Chat Extension startup")
        
        self._agent_manager = AgentManager()
        self._chat_window = ChatWindow(on_send_callback=self._on_send_message_callback)

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
                ui_feedback_callback=self._chat_window.add_message_bubble
            )

            # If final response is an error message not caught by streaming
            if final_response.startswith("Excepción") or final_response.startswith("Error"):
                self._chat_window.append_to_last_message(f"\n\n[Error: {final_response}]")

        except Exception as e:
            error_msg = f"\n\nExcepción grave en el orquestador: {str(e)}"
            print(f"[omni.lm_chat] {error_msg}")
            self._chat_window.append_to_last_message(error_msg)
        finally:
            if self._chat_window:
                self._chat_window.set_button_state(processing=False)

    def on_shutdown(self):
        """Called when the extension is disabled."""
        print("[omni.lm_chat] LM-Chat Extension shutdown")
        if hasattr(self, '_chat_window') and self._chat_window:
            self._chat_window.destroy()
            self._chat_window = None
        self._agent_manager = None

# Backwards compatibility alias for Omniverse Kit module loader
MyExtension = LMChatExtension
