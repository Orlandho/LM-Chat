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
from core.interfaces import ClusterFailoverStrategy


class TestSettingsWindow(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(window.selected_model, "deepseek-v4")

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
        self.assertEqual(window.selected_model, "gpt-6-astra")


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

    def test_discover_models_button_and_async_callback(self):
        """Verifica que SettingsWindow incluya el botón de descubrimiento y ejecute la tarea."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        self.assertTrue(hasattr(window, "_discover_models_btn"))
        self.assertIsNotNone(window._discover_models_btn)

        window._on_discover_models_clicked()
        self.assertIn("Consultando", window._discover_status_label.text)

        window.destroy()

    def test_lm_studio_vram_button_present(self):
        """Verifica que el botón 'Liberar VRAM' esté presente para LM Studio."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        self.assertEqual(window.selected_provider, "LM Studio")
        self.assertTrue(hasattr(window, "_unload_vram_btn"))
        self.assertIsNotNone(window._unload_vram_btn)
        self.assertIn("Liberar VRAM", window._unload_vram_btn.text)
        self.assertIsNotNone(window._vram_status_label)
        window.destroy()

    def test_lm_studio_on_unload_vram_clicked_triggers_task(self):
        """Verifica que al hacer clic en Liberar VRAM se active el feedback y se lance la tarea."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        window._on_unload_vram_clicked()
        self.assertIn("Liberando VRAM", window._vram_status_label.text)
        window.destroy()

    async def test_lm_studio_run_async_unload_vram_success(self):
        """Verifica la ejecución asíncrona exitosa de unload_all_models()."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        mock_vram_mgr = MagicMock()
        mock_vram_mgr.unload_all_models = AsyncMock(return_value={
            "success": True,
            "unloaded_instances": ["deepseek-v4", "qwen-7b"],
            "errors": [],
        })

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=mock_vram_mgr):
            res = await window._run_async_unload_vram()
            self.assertTrue(res["success"])
            self.assertEqual(len(res["unloaded_instances"]), 2)
            self.assertIn("2 modelo(s) descargado(s)", window._vram_status_label.text)

        window.destroy()

    async def test_lm_studio_run_async_unload_vram_already_free(self):
        """Verifica feedback cuando no hay modelos activos en LM Studio."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        mock_vram_mgr = MagicMock()
        mock_vram_mgr.unload_all_models = AsyncMock(return_value={
            "success": True,
            "unloaded_instances": [],
            "errors": [],
        })

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=mock_vram_mgr):
            res = await window._run_async_unload_vram()
            self.assertTrue(res["success"])
            self.assertIn("ya libre", window._vram_status_label.text.lower())

        window.destroy()

    async def test_lm_studio_run_async_unload_vram_failure(self):
        """Verifica manejo de errores reportados al descargar modelos de LM Studio."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        mock_vram_mgr = MagicMock()
        mock_vram_mgr.unload_all_models = AsyncMock(return_value={
            "success": False,
            "unloaded_instances": [],
            "errors": ["Connection reset by peer"],
        })

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=mock_vram_mgr):
            res = await window._run_async_unload_vram()
            self.assertFalse(res["success"])
            self.assertIn("Error liberando VRAM", window._vram_status_label.text)

        window.destroy()

    async def test_lm_studio_run_async_unload_vram_exception(self):
        """Verifica manejo de excepción no controlada en unload_all_models()."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        mock_vram_mgr = MagicMock()
        mock_vram_mgr.unload_all_models = AsyncMock(side_effect=RuntimeError("GPU timeout"))

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=mock_vram_mgr):
            res = await window._run_async_unload_vram()
            self.assertFalse(res["success"])
            self.assertIn("Error", window._vram_status_label.text)

        window.destroy()

    def test_local_cluster_controls_built_when_selected(self):
        """Verifica que al seleccionar Local Cluster se construyan los controles de cluster."""
        window = SettingsWindow(settings_manager=self.settings_manager)

        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")

        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx

        window._on_provider_changed(item_model_mock, None)
        self.assertEqual(window.selected_provider, "Local Cluster")
        self.assertIsNotNone(window._cluster_strategy_combo)
        self.assertIsNotNone(window._cluster_health_btn)
        self.assertIn("Salud del Clúster", window._cluster_health_btn.text)
        self.assertIsNotNone(window._cluster_health_status_label)
        self.assertIsNotNone(window._cluster_nodes_frame)
        self.assertEqual(window.selected_cluster_strategy, "priority")
        window.destroy()

    def test_local_cluster_strategy_change_and_persistence(self):
        """Verifica que cambiar la estrategia en el ComboBox actualice y persista."""
        window = SettingsWindow(settings_manager=self.settings_manager)

        # Cambiar a Local Cluster
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        # Cambiar estrategia a round_robin (índice 1)
        strat_model_mock = MagicMock()
        strat_model_mock.get_item_value_model.return_value.as_int = 1
        window._on_cluster_strategy_changed(strat_model_mock, None)
        self.assertEqual(window.selected_cluster_strategy, "round_robin")
        cfg = self.settings_manager.get_provider_config("Local Cluster")
        self.assertEqual(cfg["cluster_strategy"], "round_robin")

        # Cambiar estrategia a lowest_latency (índice 2)
        strat_model_mock = MagicMock()
        strat_model_mock.get_item_value_model.return_value.as_int = 2
        window._on_cluster_strategy_changed(strat_model_mock, None)
        self.assertEqual(window.selected_cluster_strategy, "lowest_latency")
        cfg = self.settings_manager.get_provider_config("Local Cluster")
        self.assertEqual(cfg["cluster_strategy"], "lowest_latency")

        # Guardar y verificar que persiste
        window._on_save_clicked()
        cfg_saved = self.settings_manager.get_provider_config("Local Cluster")
        self.assertEqual(cfg_saved["cluster_strategy"], "lowest_latency")

        window.destroy()

    def test_local_cluster_health_check_clicked_triggers_task(self):
        """Verifica que el clic en probar salud del clúster active feedback y tarea."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        window._on_cluster_health_check_clicked()
        self.assertIn("Sondeando", window._cluster_health_status_label.text)
        window.destroy()

    async def test_local_cluster_run_async_health_check_all_healthy(self):
        """Verifica sondeo asíncrono cuando todos los nodos están saludables."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        mock_cluster_mgr = MagicMock()
        mock_cluster_mgr.check_health_all = AsyncMock(return_value={
            "Primary Local Node": True,
            "Secondary LAN Node": True,
        })
        mock_cluster_mgr.get_nodes.return_value = []

        with patch.object(self.settings_manager, "get_cluster_manager", return_value=mock_cluster_mgr):
            res = await window._run_async_cluster_health_check()
            self.assertEqual(res, {"Primary Local Node": True, "Secondary LAN Node": True})
            self.assertIn("2/2", window._cluster_health_status_label.text)

        window.destroy()

    async def test_local_cluster_run_async_health_check_partial_failure(self):
        """Verifica sondeo asíncrono cuando algún nodo falla."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        mock_cluster_mgr = MagicMock()
        mock_cluster_mgr.check_health_all = AsyncMock(return_value={
            "Primary Local Node": True,
            "Secondary LAN Node": False,
        })
        mock_cluster_mgr.get_nodes.return_value = []

        with patch.object(self.settings_manager, "get_cluster_manager", return_value=mock_cluster_mgr):
            res = await window._run_async_cluster_health_check()
            self.assertIn("1/2", window._cluster_health_status_label.text)

        window.destroy()

    async def test_local_cluster_run_async_health_check_exception(self):
        """Verifica manejo de excepción al sondear salud del clúster."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        mock_cluster_mgr = MagicMock()
        mock_cluster_mgr.check_health_all = AsyncMock(side_effect=ConnectionError("Host unreachable"))

        with patch.object(self.settings_manager, "get_cluster_manager", return_value=mock_cluster_mgr):
            res = await window._run_async_cluster_health_check()
            self.assertEqual(res, {})
            self.assertIn("Error", window._cluster_health_status_label.text)

        window.destroy()

    def test_provider_switching_dynamically_swaps_extra_controls(self):
        """Verifica que cambiar de proveedor limpie e intercambie adecuadamente los controles específicos."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()

        # 1. LM Studio tiene botón VRAM
        self.assertIsNotNone(window._unload_vram_btn)

        # 2. Cambiar a OpenAI API: se limpia el frame extra y se resetean referencias
        openai_idx = providers.index("OpenAI API")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = openai_idx
        window._on_provider_changed(item_model_mock, None)
        self.assertEqual(window.selected_provider, "OpenAI API")
        self.assertIsNone(window._unload_vram_btn)
        self.assertIsNone(window._cluster_health_btn)
        self.assertIsNone(window._cluster_strategy_combo)

        # 3. Cambiar a Local Cluster: se generan controles de cluster
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)
        self.assertEqual(window.selected_provider, "Local Cluster")
        self.assertIsNotNone(window._cluster_strategy_combo)
        self.assertIsNotNone(window._cluster_health_btn)
        self.assertIsNone(window._unload_vram_btn)

        # 4. Cambiar de regreso a LM Studio: se regeneran controles de LM Studio
        lm_idx = providers.index("LM Studio")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = lm_idx
        window._on_provider_changed(item_model_mock, None)
        self.assertEqual(window.selected_provider, "LM Studio")
        self.assertIsNotNone(window._unload_vram_btn)
        self.assertIsNone(window._cluster_health_btn)

        window.destroy()

    def test_initial_cluster_strategy_reads_from_local_cluster_config(self):
        """Verifica que selected_cluster_strategy lea la configuración de Local Cluster incluso si otro proveedor está seleccionado."""
        self.settings_manager.update_provider_config("Local Cluster", cluster_strategy="lowest_latency")
        window = SettingsWindow(settings_manager=self.settings_manager)
        self.assertEqual(window.selected_provider, "LM Studio")
        self.assertEqual(window.selected_cluster_strategy, "lowest_latency")
        window.destroy()

    async def test_lm_studio_run_async_unload_vram_none_manager_fallback(self):
        """Verifica que si get_lm_studio_vram_manager retorna None, se recurre a LMStudioVRAMManager sin AttributeError."""
        window = SettingsWindow(settings_manager=self.settings_manager)

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=None):
            with patch("logic.lm_studio_vram.LMStudioVRAMManager.unload_all_models", new_callable=AsyncMock) as mock_unload:
                mock_unload.return_value = {"success": True, "unloaded_instances": ["fallback-model"], "errors": []}
                res = await window._run_async_unload_vram()
                self.assertTrue(res["success"])
                self.assertEqual(res["unloaded_instances"], ["fallback-model"])
                self.assertIn("1 modelo(s) descargado(s)", window._vram_status_label.text)

        window.destroy()

    async def test_local_cluster_run_async_health_check_none_manager_fallback(self):
        """Verifica que si get_cluster_manager retorna None, se recurre a ClusterManager sin AttributeError."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        with patch.object(self.settings_manager, "get_cluster_manager", return_value=None):
            with patch("logic.cluster_manager.ClusterManager.check_health_all", new_callable=AsyncMock) as mock_health:
                mock_health.return_value = {"Fallback Node": True}
                res = await window._run_async_cluster_health_check()
                self.assertEqual(res, {"Fallback Node": True})
                self.assertIn("1/1", window._cluster_health_status_label.text)

        window.destroy()

    def test_unload_vram_double_click_guard(self):
        """Verifica que clics concurrentes repetidos no lancen tareas duplicadas."""
        window = SettingsWindow(settings_manager=self.settings_manager)

        # Simular tarea activa
        mock_task = MagicMock()
        mock_task.done.return_value = False
        window._vram_task = mock_task

        window._on_unload_vram_clicked()
        # La tarea activa no debe ser reemplazada
        self.assertIs(window._vram_task, mock_task)

        window.destroy()

    def test_cluster_health_check_double_click_guard(self):
        """Verifica que clics concurrentes repetidos en salud del cluster no lancen tareas duplicadas."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        # Simular tarea activa
        mock_task = MagicMock()
        mock_task.done.return_value = False
        window._cluster_health_task = mock_task

        window._on_cluster_health_check_clicked()
        # La tarea activa no debe ser reemplazada
        self.assertIs(window._cluster_health_task, mock_task)

        window.destroy()

    def test_cluster_nodes_view_handles_none_or_malformed_latency(self):
        """Verifica que nodos con latencia None o valores no numéricos se rendericen sin lanzar TypeError."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        mock_cluster = MagicMock()
        node_none_lat = MagicMock()
        node_none_lat.name = "Node None"
        node_none_lat.url = "http://localhost:1111"
        node_none_lat.is_healthy = True
        node_none_lat.last_latency_ms = None

        node_str_lat = MagicMock()
        node_str_lat.name = "Node Str"
        node_str_lat.url = "http://localhost:2222"
        node_str_lat.is_healthy = False
        node_str_lat.last_latency_ms = "invalid"

        mock_cluster.get_nodes.return_value = [node_none_lat, node_str_lat]

        # No debe lanzar TypeError al reconstruir la vista
        window._rebuild_cluster_nodes_view(mock_cluster)
        self.assertIsNotNone(window._cluster_nodes_frame)

        window.destroy()

    async def test_destroyed_window_safe_in_async_tasks(self):
        """Verifica que las tareas asíncronas no fallen ni muten si la ventana fue destruida."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        mock_vram_mgr = MagicMock()

        async def _destroy_and_return():
            window.destroy()
            return {"success": True, "unloaded_instances": ["model"], "errors": []}

        mock_vram_mgr.unload_all_models = _destroy_and_return

        with patch.object(self.settings_manager, "get_lm_studio_vram_manager", return_value=mock_vram_mgr):
            res = await window._run_async_unload_vram()
            self.assertTrue(res["success"])
            self.assertIsNone(window._window)

    async def test_provider_switch_during_async_task_does_not_mutate_stale_widgets(self):
        """Verifica que si el usuario cambia de proveedor mientras se ejecuta un sondeo, no se actualicen widgets obsoletos."""
        window = SettingsWindow(settings_manager=self.settings_manager)
        providers = self.settings_manager.get_all_providers()

        # Seleccionar Local Cluster
        cluster_idx = providers.index("Local Cluster")
        item_model_mock = MagicMock()
        item_model_mock.get_item_value_model.return_value.as_int = cluster_idx
        window._on_provider_changed(item_model_mock, None)

        # Cambiar a OpenAI API antes de que termine la tarea
        openai_idx = providers.index("OpenAI API")
        item_model_mock.get_item_value_model.return_value.as_int = openai_idx
        window._on_provider_changed(item_model_mock, None)

        mock_cluster = MagicMock()
        mock_cluster.check_health_all = AsyncMock(return_value={"Node": True})

        with patch.object(self.settings_manager, "get_cluster_manager", return_value=mock_cluster):
            res = await window._run_async_cluster_health_check()
            self.assertEqual(res, {"Node": True})
            # Como el proveedor actual es OpenAI API, los controles de cluster están en None
            self.assertIsNone(window._cluster_health_status_label)

        window.destroy()


if __name__ == "__main__":
    unittest.main()


