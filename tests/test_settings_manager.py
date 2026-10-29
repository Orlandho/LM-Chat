# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for SettingsManager and multi-provider configuration persistence.
"""

import os
import json
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import aiohttp

from logic.settings_manager import SettingsManager


class TestSettingsManager(unittest.IsolatedAsyncioTestCase):
    """Pruebas unitarias para SettingsManager."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.temp_dir.name, "settings.json")
        self.manager = SettingsManager(config_path=self.config_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_initialization(self):
        """Verifica los valores de inicialización por defecto."""
        self.assertEqual(self.manager.get_default_provider(), "LM Studio")
        self.assertEqual(self.manager.get_default_model("LM Studio"), "deepseek-v4")
        providers = self.manager.get_all_providers()
        self.assertIn("LM Studio", providers)
        self.assertIn("Ollama", providers)
        self.assertIn("OpenAI API", providers)
        self.assertIn("Claude API", providers)
        self.assertIn("NVIDIA Spark", providers)

    def test_canonicalize_provider_name_and_aliases(self):
        """Verifica la normalización tolerante de nombres y alias de proveedores."""
        self.assertEqual(self.manager._canonicalize_provider_name("openai"), "OpenAI API")
        self.assertEqual(self.manager._canonicalize_provider_name("open_ai"), "OpenAI API")
        self.assertEqual(self.manager._canonicalize_provider_name("claude"), "Claude API")
        self.assertEqual(self.manager._canonicalize_provider_name("anthropic"), "Claude API")
        self.assertEqual(self.manager._canonicalize_provider_name("nvidia_spark"), "NVIDIA Spark")
        self.assertEqual(self.manager._canonicalize_provider_name("nemotron"), "NVIDIA Spark")
        self.assertEqual(self.manager._canonicalize_provider_name("spark"), "NVIDIA Spark")
        self.assertEqual(self.manager._canonicalize_provider_name("ollama"), "Ollama")
        self.assertEqual(self.manager._canonicalize_provider_name("lm_studio"), "LM Studio")

    def test_set_default_provider_and_persistence(self):
        """Verifica que cambiar el proveedor predeterminado persista en disco."""
        self.manager.set_default_provider("Claude API")
        self.assertEqual(self.manager.get_default_provider(), "Claude API")
        self.assertEqual(self.manager.get_default_model("Claude API"), "claude-opus-5-5-latest")


        # Recargar desde el archivo físico
        reloaded = SettingsManager(config_path=self.config_file)
        self.assertEqual(reloaded.get_default_provider(), "Claude API")

    def test_update_provider_config(self):
        """Verifica la actualización de URL, modelo y credenciales para un proveedor."""
        self.manager.update_provider_config(
            "NVIDIA Spark",
            base_url="http://localhost:8000/v1",
            api_key="nvapi-test-key",
            default_model="meta/llama-3.1-70b-instruct",
            temperature=0.2,
            timeout=120.0,
        )

        cfg = self.manager.get_provider_config("NVIDIA Spark")
        self.assertEqual(cfg["base_url"], "http://localhost:8000/v1")
        self.assertEqual(cfg["api_key"], "nvapi-test-key")
        self.assertEqual(cfg["default_model"], "meta/llama-3.1-70b-instruct")
        self.assertEqual(cfg["temperature"], 0.2)
        self.assertEqual(cfg["timeout"], 120.0)

    def test_add_custom_model(self):
        """Verifica agregar un modelo personalizado a la lista de un proveedor."""
        self.manager.add_custom_model("OpenAI API", "gpt-4o-custom-ft")
        models = self.manager.get_available_models("OpenAI API")
        self.assertIn("gpt-4o-custom-ft", models)

        # No duplicar si ya existe
        self.manager.add_custom_model("OpenAI API", "gpt-4o-custom-ft")
        self.assertEqual(models.count("gpt-4o-custom-ft"), 1)

    def test_effective_api_key_resolution(self):
        """Verifica la resolución de API keys explícitas vs variables de entorno."""
        # 1. Sin key explícita ni variable de entorno
        with patch.dict(os.environ, {}, clear=True):
            key = self.manager.get_effective_api_key("OpenAI API")
            self.assertIsNone(key)

        # 2. Resuelta desde variable de entorno
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-test-key"}):
            key = self.manager.get_effective_api_key("OpenAI API")
            self.assertEqual(key, "sk-env-test-key")

        # 3. Key explícita configurada tiene precedencia
        self.manager.update_provider_config("OpenAI API", api_key="sk-explicit-override")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-test-key"}):
            key = self.manager.get_effective_api_key("OpenAI API")
            self.assertEqual(key, "sk-explicit-override")

    def test_presets_availability(self):
        """Verifica que todos los servicios principales tengan presets de 1 clic."""
        for prov in ["LM Studio", "Ollama", "OpenAI API", "Claude API", "NVIDIA Spark", "Google Gemini API"]:
            presets = self.manager.get_presets(prov)
            self.assertIsInstance(presets, list)
            self.assertGreater(len(presets), 0)
            self.assertTrue(all("label" in p and "url" in p for p in presets))

    def test_reset_to_defaults(self):
        """Verifica restaurar los valores de fábrica."""
        self.manager.set_default_provider("OpenAI API")
        self.manager.update_provider_config("OpenAI API", base_url="https://custom.proxy.com/v1")
        self.assertEqual(self.manager.get_default_provider(), "OpenAI API")

        self.manager.reset_to_defaults()
        self.assertEqual(self.manager.get_default_provider(), "LM Studio")
        cfg = self.manager.get_provider_config("OpenAI API")
        self.assertEqual(cfg["base_url"], "https://api.openai.com/v1")

    @patch("aiohttp.ClientSession.get")
    async def test_test_connection_success(self, mock_get):
        """Verifica resultado exitoso de la prueba de conexión (HTTP 200)."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_get.return_value.__aenter__.return_value = mock_response

        res = await self.manager.test_connection("OpenAI API", api_key="sk-test")
        self.assertTrue(res["success"])
        self.assertIn("200 OK", res["message"])
        self.assertGreaterEqual(res["latency_ms"], 0.0)

    @patch("aiohttp.ClientSession.get")
    async def test_test_connection_auth_error(self, mock_get):
        """Verifica manejo de error de autenticación (HTTP 401)."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_get.return_value.__aenter__.return_value = mock_response

        res = await self.manager.test_connection("Claude API", api_key="bad-key")
        self.assertFalse(res["success"])
        self.assertIn("401", res["message"])
        self.assertIn("autenticación", res["message"].lower())

    @patch("aiohttp.ClientSession.get")
    async def test_test_connection_refused(self, mock_get):
        """Verifica manejo de conexión rehusada cuando el servidor local está apagado."""
        mock_get.side_effect = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError(111, "Connection refused")
        )

        res = await self.manager.test_connection("LM Studio")
        self.assertFalse(res["success"])
        self.assertIn("rehusada", res["message"].lower())

    async def test_test_connection_invalid_url(self):
        """Verifica rechazo de URLs con esquemas no HTTP/HTTPS."""
        res = await self.manager.test_connection("LM Studio", base_url="ftp://invalid-server")
        self.assertFalse(res["success"])
        self.assertIn("inválida", res["message"].lower())

    @patch("aiohttp.ClientSession.get")
    async def test_fetch_remote_models_openai_compat(self, mock_get):
        """Verifica descubrimiento dinámico en endpoint compatible con OpenAI /models."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "data": [
                {"id": "gpt-6-astra"},
                {"id": "gpt-6.1-sol"},
                {"id": "gpt-6-luna"},
            ]
        })
        mock_get.return_value.__aenter__.return_value = mock_response

        models = await self.manager.fetch_remote_models("OpenAI API")
        self.assertIn("gpt-6-astra", models)
        self.assertIn("gpt-6.1-sol", models)
        self.assertIn("gpt-6-luna", models)

    @patch("aiohttp.ClientSession.get")
    async def test_fetch_remote_models_ollama_tags(self, mock_get):
        """Verifica descubrimiento dinámico en endpoint Ollama /api/tags."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "models": [
                {"name": "deepseek-r1:8b"},
                {"name": "deepseek-r1:14b"},
            ]
        })
        mock_get.return_value.__aenter__.return_value = mock_response

        models = await self.manager.fetch_remote_models("Ollama")
        self.assertIn("deepseek-r1:8b", models)
        self.assertIn("deepseek-r1:14b", models)

    @patch("aiohttp.ClientSession.get")
    async def test_fetch_remote_models_error_fallback(self, mock_get):
        """Verifica que si la red falla, retorna los modelos existentes sin propagar excepción."""
        mock_get.side_effect = Exception("Conexión rechazada")

        models = await self.manager.fetch_remote_models("LM Studio")
        self.assertIsInstance(models, list)
        self.assertTrue(len(models) > 0)

    def test_save_file_permissions(self):
        """Verifica que el archivo de configuración se guarde con permisos 0o600."""
        self.manager.save()
        self.assertTrue(os.path.exists(self.config_file))
        if os.name != "nt":
            mode = os.stat(self.config_file).st_mode & 0o777
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()

