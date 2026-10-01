# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for the Intelligent Diagnostics Engine (logic/diagnostics.py) in LM-Chat™.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from logic.diagnostics import (
    DiagnosticCategory,
    ErrorDiagnostic,
    diagnose_inference_failure,
    _safe_str,
)


class TestDiagnosticsEngine(unittest.TestCase):
    """Pruebas unitarias para el motor de diagnóstico de errores de LM-Chat."""

    def test_safe_str_various_types(self):
        """Verifica que _safe_str maneje de forma segura distintos tipos de datos."""
        self.assertEqual(_safe_str(None), "")
        self.assertEqual(_safe_str("hello"), "hello")
        self.assertEqual(_safe_str(b"bytes string"), "bytes string")
        self.assertEqual(_safe_str(ValueError("un valor")), "un valor")

        # Objetos Mock o corrutinas no deben reventar ni generar Mocks
        mock_obj = AsyncMock()
        self.assertEqual(_safe_str(mock_obj), "")
        magic_mock = MagicMock()
        self.assertEqual(_safe_str(magic_mock), "")

    def test_diagnostic_connection_refused_ollama(self):
        """Verifica diagnóstico cuando Ollama está apagado."""
        diag = diagnose_inference_failure(
            provider="Ollama",
            model="llama3.3",
            base_url="http://localhost:11434/v1",
            error_type="ConnectionError",
            raw_error="Cannot connect to host localhost:11434 [Connect call failed ('127.0.0.1', 11434)]",
        )
        self.assertEqual(diag.category, DiagnosticCategory.CONNECTION_REFUSED)
        self.assertIn("Ollama no detectado", diag.title)
        self.assertTrue(any("ollama serve" in step for step in diag.troubleshooting_steps))
        self.assertTrue(any("ollama pull" in step for step in diag.troubleshooting_steps))

        # Markdown representation
        md = diag.to_markdown()
        self.assertIn("### ⚠️ Diagnóstico LM-Chat:", md)
        self.assertIn("ollama serve", md)
        self.assertIn("http://localhost:11434/v1", md)

        # Plain text representation
        plain = diag.to_plain_text()
        self.assertIn("[DIAGNÓSTICO LM-Chat]", plain)
        self.assertIn("Ollama", plain)

    def test_diagnostic_connection_refused_lm_studio(self):
        """Verifica diagnóstico cuando LM Studio está apagado."""
        diag = diagnose_inference_failure(
            provider="LM Studio",
            model="local-model",
            base_url="http://localhost:1234/v1",
            error_message="WinError 10061: No se puede establecer una conexión ya que el equipo de destino denegó expresamente dicha conexión",
        )
        self.assertEqual(diag.category, DiagnosticCategory.CONNECTION_REFUSED)
        self.assertIn("LM Studio", diag.title)
        self.assertTrue(any("Start Server" in step for step in diag.troubleshooting_steps))
        self.assertTrue(any("1234" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_auth_error_openai(self):
        """Verifica diagnóstico de clave de API incorrecta en OpenAI."""
        diag = diagnose_inference_failure(
            provider="OpenAI API",
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            status_code=401,
            raw_error='{"error": {"message": "Incorrect API key provided: sk-bad***"}}',
        )
        self.assertEqual(diag.category, DiagnosticCategory.AUTHENTICATION_ERROR)
        self.assertIn("Autenticación fallida", diag.title)
        self.assertEqual(diag.technical_details["expected_env"], "OPENAI_API_KEY")
        self.assertTrue(any("OPENAI_API_KEY" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_auth_error_claude(self):
        """Verifica diagnóstico de clave de API incorrecta en Claude."""
        diag = diagnose_inference_failure(
            provider="Claude API",
            model="claude-3-7-sonnet-latest",
            base_url="https://api.anthropic.com/v1",
            status_code=401,
            raw_error='{"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}',
        )
        self.assertEqual(diag.category, DiagnosticCategory.AUTHENTICATION_ERROR)
        self.assertEqual(diag.technical_details["expected_env"], "ANTHROPIC_API_KEY")
        self.assertTrue(any("ANTHROPIC_API_KEY" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_model_not_found_404(self):
        """Verifica diagnóstico cuando el modelo solicitado no existe o no está cargado."""
        diag = diagnose_inference_failure(
            provider="Ollama",
            model="mistral-unknown",
            base_url="http://localhost:11434/v1",
            status_code=404,
            raw_error='{"error": "model \'mistral-unknown\' not found, try pulling it first"}',
        )
        self.assertEqual(diag.category, DiagnosticCategory.MODEL_NOT_FOUND)
        self.assertIn("mistral-unknown", diag.title)
        self.assertTrue(any("ollama pull mistral-unknown" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_rate_limit_429(self):
        """Verifica diagnóstico para HTTP 429 Cuota excedida."""
        diag = diagnose_inference_failure(
            provider="OpenAI API",
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            status_code=429,
            raw_error="Rate limit reached for requests",
        )
        self.assertEqual(diag.category, DiagnosticCategory.RATE_LIMIT_EXCEEDED)
        self.assertIn("429", diag.title)
        self.assertTrue(any("facturación" in step or "saldo" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_timeout(self):
        """Verifica diagnóstico de tiempo de espera agotado."""
        diag = diagnose_inference_failure(
            provider="LM Studio",
            model="deepseek-r1-distill-qwen-14b",
            base_url="http://localhost:1234/v1",
            error_type="TimeoutError",
            timeout=120.0,
        )
        self.assertEqual(diag.category, DiagnosticCategory.TIMEOUT)
        self.assertIn("120s", diag.title)
        self.assertTrue(any("VRAM" in step or "GPU" in step for step in diag.troubleshooting_steps))

    def test_diagnostic_server_error_oom(self):
        """Verifica diagnóstico cuando ocurre fallo de memoria GPU / CUDA OOM."""
        diag = diagnose_inference_failure(
            provider="LM Studio",
            model="qwen2.5-coder-32b",
            base_url="http://localhost:1234/v1",
            status_code=500,
            raw_error="RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB",
        )
        self.assertEqual(diag.category, DiagnosticCategory.SERVER_ERROR)
        self.assertTrue(diag.technical_details.get("is_oom"))
        self.assertIn("VRAM", diag.title)

    def test_diagnostic_invalid_url(self):
        """Verifica diagnóstico ante URL inválida o sin protocolo http/https."""
        diag = diagnose_inference_failure(
            provider="Custom",
            model="custom-model",
            base_url="ftp://localhost:1234",
            error_message="invalid base_url scheme",
        )
        self.assertEqual(diag.category, DiagnosticCategory.CONFIGURATION_ERROR)
        self.assertIn("URL", diag.title)

    def test_diagnostic_serialization_to_dict(self):
        """Verifica que to_dict serialice los campos adecuadamente."""
        diag = diagnose_inference_failure(
            provider="OpenAI API",
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            status_code=401,
        )
        data = diag.to_dict()
        self.assertEqual(data["category"], "authentication_error")
        self.assertEqual(data["provider"], "OpenAI API")
        self.assertEqual(data["model"], "gpt-4o")
        self.assertIsInstance(data["troubleshooting_steps"], list)

    def test_diagnostic_none_and_empty_base_url_and_model(self):
        """Verifica que valores None o vacíos en base_url o model no causen excepciones ni falsos CONFIGURATION_ERROR."""
        diag_none = diagnose_inference_failure(
            provider="openai",
            model=None,
            base_url=None,
            error_message="Unexpected error",
        )
        self.assertNotEqual(diag_none.category, DiagnosticCategory.CONFIGURATION_ERROR)
        self.assertEqual(diag_none.category, DiagnosticCategory.UNKNOWN)
        self.assertEqual(diag_none.model, "desconocido")
        self.assertEqual(diag_none.base_url, "")

        diag_empty = diagnose_inference_failure(
            provider="openai",
            model="gpt-4o",
            base_url="",
            error_message="Some generic error",
        )
        self.assertEqual(diag_empty.category, DiagnosticCategory.UNKNOWN)

    def test_diagnostic_auth_error_gemini(self):
        """Verifica diagnóstico de autenticación para Google Gemini API."""
        diag = diagnose_inference_failure(
            provider="Google Gemini API",
            model="gemini-2.0-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            status_code=401,
            raw_error="API_KEY_INVALID",
        )
        self.assertEqual(diag.category, DiagnosticCategory.AUTHENTICATION_ERROR)
        self.assertEqual(diag.technical_details.get("expected_env"), "GEMINI_API_KEY")
        self.assertTrue(any("GEMINI_API_KEY" in step for step in diag.troubleshooting_steps))


if __name__ == "__main__":
    unittest.main()
