# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Registro Unificado (Structured Logger) para LM-Chat™.

Proporciona un sistema de logging estructurado, robusto y de alto rendimiento
con soporte dual para el subsistema nativo de NVIDIA Omniverse (`carb.logging`)
y la biblioteca estándar de Python `logging`.

Incluye un búfer en memoria circular para inspección en caliente desde la UI/CLI,
registro persistente opcional en disco (~/.omni_lm_chat/lm_chat.log) y formateo
consistente de eventos y excepciones.
"""

import os
import sys
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


class LogEntry:
    """Representa una entrada estructurada de log."""

    __slots__ = ("timestamp", "level", "component", "message", "details")

    def __init__(
        self,
        level: str,
        component: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.level = level.upper()
        self.component = component
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serializa la entrada a un diccionario nativo."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "component": self.component,
            "message": self.message,
            "details": self.details,
        }

    def format_line(self) -> str:
        """Formatea la entrada en una línea legible para consola o archivo."""
        details_str = f" | {self.details}" if self.details else ""
        return f"[{self.timestamp}][{self.level}][{self.component}] {self.message}{details_str}"


class LMChatLogger:
    """Gestor unificado de logs para LM-Chat con buffer circular y soporte para Omniverse carb."""

    _instance: Optional["LMChatLogger"] = None
    _carb_module: Optional[Any] = None
    _carb_checked: bool = False

    DEFAULT_LOG_DIR = os.path.expanduser(os.path.join("~", ".omni_lm_chat"))
    DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "lm_chat.log")

    def __init__(self, buffer_size: int = 1000, log_to_file: bool = True) -> None:
        """Inicializa el logger.

        Args:
            buffer_size (int): Tamaño máximo del buffer circular en memoria.
            log_to_file (bool): Si es True, escribe logs en el archivo persistente.
        """
        self._buffer: deque = deque(maxlen=buffer_size)
        self._python_logger = logging.getLogger("orlandodorival.lm_chat")
        self._log_to_file = log_to_file
        self._file_handler: Optional[logging.Handler] = None

        self._configure_python_logger()

    @classmethod
    def get_instance(cls) -> "LMChatLogger":
        """Obtiene la instancia singleton del logger."""
        if cls._instance is None:
            cls._instance = LMChatLogger()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reinicia la instancia singleton (útil en tests)."""
        cls._instance = None
        cls._carb_checked = False
        cls._carb_module = None

    def _get_carb(self) -> Optional[Any]:
        """Detecta de forma segura si NVIDIA Omniverse carb está disponible."""
        if not self._carb_checked:
            self._carb_checked = True
            try:
                import carb
                # Verificar si tiene las funciones de logging esperadas
                if hasattr(carb, "log_info"):
                    self._carb_module = carb
            except Exception:
                self._carb_module = None
        return self._carb_module

    def _configure_python_logger(self) -> None:
        """Configura el logger de Python si no tiene handlers configurados."""
        if not self._python_logger.handlers:
            self._python_logger.setLevel(logging.DEBUG)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "[LM-Chat][%(levelname)s][%(name)s] %(message)s"
            )
            console_handler.setFormatter(formatter)
            self._python_logger.addHandler(console_handler)

        if self._log_to_file and not self._file_handler:
            try:
                os.makedirs(self.DEFAULT_LOG_DIR, exist_ok=True)
                file_handler = logging.FileHandler(
                    self.DEFAULT_LOG_FILE, encoding="utf-8"
                )
                file_handler.setLevel(logging.DEBUG)
                file_formatter = logging.Formatter(
                    "[%(asctime)s][%(levelname)s][%(name)s] %(message)s"
                )
                file_handler.setFormatter(file_formatter)
                self._python_logger.addHandler(file_handler)
                self._file_handler = file_handler
            except Exception:
                # Si no se tiene permiso de escritura, continúa en memoria
                self._file_handler = None

    def log(
        self,
        level: str,
        component: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        exc_info: Optional[Exception] = None,
    ) -> LogEntry:
        """Registra un evento estructurado en todos los destinos disponibles.

        Args:
            level (str): Nivel ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
            component (str): Nombre del componente o módulo de origen.
            message (str): Mensaje descriptivo.
            details (Optional[Dict[str, Any]]): Metadatos adicionales o contexto.
            exc_info (Optional[Exception]): Excepción asociada si aplica.

        Returns:
            LogEntry: La entrada registrada.
        """
        lvl_upper = level.upper()
        entry = LogEntry(
            level=lvl_upper,
            component=component,
            message=message,
            details=details,
        )
        self._buffer.append(entry)

        # 1. Enviar a Omniverse carb si está disponible en Kit SDK
        carb = self._get_carb()
        if carb:
            formatted_msg = f"[{component}] {message}"
            if details:
                formatted_msg += f" | {details}"
            try:
                if lvl_upper == "DEBUG" and hasattr(carb, "log_verbose"):
                    carb.log_verbose(formatted_msg)
                elif lvl_upper == "INFO" and hasattr(carb, "log_info"):
                    carb.log_info(formatted_msg)
                elif lvl_upper == "WARNING" and hasattr(carb, "log_warn"):
                    carb.log_warn(formatted_msg)
                elif lvl_upper in ("ERROR", "CRITICAL") and hasattr(carb, "log_error"):
                    carb.log_error(formatted_msg)
            except Exception:
                pass

        # 2. Enviar a Python logging
        log_method = getattr(self._python_logger, lvl_upper.lower(), self._python_logger.info)
        extra_info = f"[{component}] {message}"
        if details:
            extra_info += f" | {details}"
        log_method(extra_info, exc_info=exc_info)

        return entry

    def debug(self, component: str, message: str, **kwargs: Any) -> LogEntry:
        """Registra un mensaje de nivel DEBUG."""
        return self.log("DEBUG", component, message, kwargs if kwargs else None)

    def info(self, component: str, message: str, **kwargs: Any) -> LogEntry:
        """Registra un mensaje de nivel INFO."""
        return self.log("INFO", component, message, kwargs if kwargs else None)

    def warning(self, component: str, message: str, **kwargs: Any) -> LogEntry:
        """Registra un mensaje de nivel WARNING."""
        return self.log("WARNING", component, message, kwargs if kwargs else None)

    def error(
        self, component: str, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> LogEntry:
        """Registra un mensaje de nivel ERROR."""
        return self.log("ERROR", component, message, kwargs if kwargs else None, exc_info=exc_info)

    def critical(
        self, component: str, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> LogEntry:
        """Registra un mensaje de nivel CRITICAL."""
        return self.log("CRITICAL", component, message, kwargs if kwargs else None, exc_info=exc_info)

    def get_recent_entries(
        self,
        count: int = 100,
        min_level: Optional[str] = None,
        level: Optional[str] = None,
        exact_level: Optional[str] = None,
    ) -> List[LogEntry]:
        """Retorna las entradas más recientes del buffer circular en memoria.

        Args:
            count (int): Cantidad máxima de entradas a devolver.
            min_level (Optional[str]): Nivel mínimo de severidad para filtrar ('DEBUG', 'INFO', etc.).
            level (Optional[str]): Nivel exacto para filtrar ('INFO', 'WARNING', etc.).
            exact_level (Optional[str]): Alias explícito para filtrar por nivel exacto.

        Returns:
            List[LogEntry]: Lista de entradas ordenadas cronológicamente.
        """
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_rank = level_order.get(min_level.upper(), 0) if min_level else 0
        exact_target = (exact_level or level).upper() if (exact_level or level) else None

        results = []
        for entry in self._buffer:
            if exact_target and entry.level != exact_target:
                continue
            if min_level and level_order.get(entry.level, 0) < min_rank:
                continue
            results.append(entry)

        return results[-count:]

    get_recent_logs = get_recent_entries

    def export_as_text(self, count: int = 200) -> str:
        """Exporta los logs recientes formateados como cadena de texto."""
        entries = self.get_recent_entries(count=count)
        return "\n".join(e.format_line() for e in entries)

    def clear_buffer(self) -> None:
        """Vacía el buffer de memoria circular."""
        self._buffer.clear()


def get_logger(component: Optional[str] = None) -> "ComponentLogger":
    """Obtiene una interfaz conveniente de logging ligada a un componente específico.

    Args:
        component (Optional[str]): Nombre del componente ('InferenceRouter', 'ChatWindow', etc.).

    Returns:
        ComponentLogger: Logger contextual para el componente.
    """
    comp_name = component or "Core"
    return ComponentLogger(comp_name, LMChatLogger.get_instance())


class ComponentLogger:
    """Adaptador de conveniencia que inyecta automáticamente el nombre del componente."""

    def __init__(self, component: str, manager: LMChatLogger) -> None:
        self._component = component
        self._manager = manager

    @property
    def component(self) -> str:
        return self._component

    def debug(self, message: str, **kwargs: Any) -> LogEntry:
        return self._manager.debug(self._component, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> LogEntry:
        return self._manager.info(self._component, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> LogEntry:
        return self._manager.warning(self._component, message, **kwargs)

    def error(self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any) -> LogEntry:
        return self._manager.error(self._component, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any) -> LogEntry:
        return self._manager.critical(self._component, message, exc_info=exc_info, **kwargs)
