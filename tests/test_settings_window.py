# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for SettingsWindow (omni.ui) and its integration with ChatWindow.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from ui.settings_window import SettingsWindow
from ui.chat_window import ChatWindow
from ui.models import ChatModel
from logic.settings_manager import SettingsManager


class TestSettingsWindow(unittest.TestCase):
    """Pruebas unitarias para SettingsWindow y su integración con ChatWindow."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.temp_dir.name, "settings.json")
        self.settings_manager = SettingsManager(config_path=self.config_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_window_creation(self):
        """Verifica la instanciación de la ventana de configuración."""
        save_cb = MagicMock()
        window = SettingsWindow(
            settings_manager=self.settings_manager,
            on_save_callback=save_cb,
        )
        self.assertIsNotNone(window.window)
        self.assertEqual(window.selected_provider, "LM Studio")
        self.assertEqual(window.selected_model, "local-model")

    def test_provider_change_updates_selected_provider_and_model(self):
        """Verifica que cambiar de proveedor actualice el proveedor y modelo seleccionados."""
        window = SettingsWindow(settings_manager=self.settings_manager)

        # Simular selección del 3er proveedor (OpenAI API)
        providers = self.settings_manager.get_all_providers()
        openai_idx = providers.index("OpenAI API")

        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = openai_idx

        window._on_provider_changed(item_model_mock, None)
        self.assertEqual(window.selected_provider, "OpenAI API")
        self.assertEqual(window.selected_model, "gpt-4o")

    def test_set_as_default_button_persists(self):
        """Verifica que el botón de fijar como predeterminado actualice el SettingsManager."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        window._selected_provider = "Claude API"
        window._on_set_as_default_clicked()

        self.assertEqual(self.settings_manager.get_default_provider(), "Claude API")

    def test_save_clicked_persists_and_calls_callback(self):
        """Verifica que guardar invoque el callback y guarde en el manager."""
        save_cb = MagicMock()
        window = SettingsWindow(
            settings_manager=self.settings_manager,
            on_save_callback=save_cb,
        )

        window._selected_provider = "NVIDIA Spark"
        window._selected_model = "meta/llama-3.1-405b-instruct"
        window._url_field.model.get_value_as_string.return_value = "https://integrate.api.nvidia.com/v1"
        window._api_key_field.model.get_value_as_string.return_value = "nvapi-save-test"

        window._on_save_clicked()

        cfg = self.settings_manager.get_provider_config("NVIDIA Spark")
        self.assertEqual(cfg["api_key"], "nvapi-save-test")
        self.assertEqual(cfg["default_model"], "meta/llama-3.1-405b-instruct")
        self.assertEqual(self.settings_manager.get_default_provider(), "NVIDIA Spark")
        save_cb.assert_called_once_with("NVIDIA Spark", "meta/llama-3.1-405b-instruct")

    def test_set_provider_respects_settings_manager_default_model(self):
        """Verifica que ChatModel.set_provider respete el modelo por defecto configurado en SettingsManager."""
        self.settings_manager.set_default_model("OpenAI API", "o3-mini")
        chat_model = ChatModel(settings_manager=self.settings_manager)

        # Cambiar de proveedor en el modelo
        chat_model.set_provider("OpenAI API")
        self.assertEqual(chat_model.current_provider, "OpenAI API")
        self.assertEqual(chat_model.current_model, "o3-mini")

    def test_show_hide_destroy_lifecycle(self):
        """Verifica el ciclo de vida de visualización y destrucción."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        window.show()
        self.assertTrue(window.window.visible)

        window.hide()
        self.assertFalse(window.window.visible)

        window.destroy()
        self.assertIsNone(window._window)

    def test_chat_window_has_settings_button_and_opens_window(self):
        """Verifica que ChatWindow incluya el botón Settings y abra SettingsWindow."""
        chat_model = ChatModel(settings_manager=self.settings_manager)
        chat_window = ChatWindow(model=chat_model)

        self.assertTrue(hasattr(chat_window, "_settings_button"))
        self.assertIsNotNone(chat_window._settings_button)

        # Abrir ventana de configuración
        chat_window._open_settings_dialog()
        self.assertIsNotNone(chat_window._settings_window)
        self.assertIsInstance(chat_window._settings_window, SettingsWindow)

        # Limpiar
        chat_window.destroy()
        self.assertIsNone(chat_window._window)

    def test_chat_window_on_settings_saved_syncs_model(self):
        """Verifica que _on_settings_saved en ChatWindow sincronice ChatModel."""
        chat_model = ChatModel(settings_manager=self.settings_manager)
        chat_window = ChatWindow(model=chat_model)

        chat_window._on_settings_saved("Claude API", "claude-3-7-sonnet-latest")
        self.assertEqual(chat_model.current_provider, "Claude API")
        self.assertEqual(chat_model.current_model, "claude-3-7-sonnet-latest")

        chat_window.destroy()


if __name__ == "__main__":
    unittest.main()
