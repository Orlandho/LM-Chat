# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Unit tests for Structured Unified Logger (logic/logger.py) in LM-Chat™.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from logic.logger import LMChatLogger, LogEntry, get_logger


class TestLogger(unittest.TestCase):
    """Pruebas unitarias para el sistema de logging estructurado de LM-Chat."""

    def setUp(self):
        LMChatLogger.reset_instance()

    def tearDown(self):
        LMChatLogger.reset_instance()

    def test_log_entry_to_dict_and_format(self):
        """Verifica la serialización y formateo de LogEntry."""
        entry = LogEntry(
            level="info",
            component="TestComp",
            message="Mensaje de prueba",
            details={"key": "val"},
            timestamp="2026-09-30T12:00:00Z",
        )
        d = entry.to_dict()
        self.assertEqual(d["level"], "INFO")
        self.assertEqual(d["component"], "TestComp")
        self.assertEqual(d["message"], "Mensaje de prueba")
        self.assertEqual(d["details"], {"key": "val"})

        line = entry.format_line()
        self.assertIn("[INFO]", line)
        self.assertIn("[TestComp]", line)
        self.assertIn("Mensaje de prueba", line)

    def test_logger_singleton(self):
        """Verifica que LMChatLogger funcione como singleton."""
        logger1 = LMChatLogger.get_instance()
        logger2 = LMChatLogger.get_instance()
        self.assertIs(logger1, logger2)

    def test_circular_buffer_recording(self):
        """Verifica que las llamadas a info/warning/error se guarden en el buffer circular."""
        logger = LMChatLogger(buffer_size=10, log_to_file=False)

        with patch.object(LMChatLogger, "get_instance", return_value=logger):
            adapter = get_logger("SubComponent")
            adapter.info("Evento informativo 1")
            adapter.warning("Advertencia 2", details={"status": 404})
            adapter.error("Fallo crítico 3")

            recent_info = logger.get_recent_logs(level="info")
            self.assertEqual(len(recent_info), 1)
            self.assertEqual(recent_info[0].message, "Evento informativo 1")

            recent_min_warn = logger.get_recent_logs(min_level="warning")
            self.assertEqual(len(recent_min_warn), 2)

            all_recent = logger.get_recent_logs()
            self.assertEqual(len(all_recent), 3)

    def test_carb_detection_fallback(self):
        """Verifica que no falle cuando carb no está disponible en entornos de testing headless."""
        logger = LMChatLogger(buffer_size=10, log_to_file=False)
        carb = logger._get_carb()
        self.assertIsNone(carb)

        # Registrar un mensaje cuando carb es None no debe lanzar excepción
        logger.log("INFO", "Component", "Mensaje seguro")


if __name__ == "__main__":
    unittest.main()
