# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Modelo de datos para la interfaz gráfica omni.ui (Paradigma MDV).
Maneja el estado de la conversación, proveedores de inferencia y badges de estado.
"""

from typing import List, Dict, Any, Optional, Callable
from core.interfaces import ChatMessage


class ChatModel:
    """Modelo de estado para la vista de chat (Model en la arquitectura MDV)."""

    DEFAULT_PROVIDERS: List[str] = [
        "LM Studio",
        "Ollama",
        "vLLM",
        "Nemotron",
        "Cloud APIs",
    ]

    DEFAULT_MODELS_MAP: Dict[str, List[str]] = {
        "LM Studio": ["local-model", "qwen2.5-coder-7b", "deepseek-r1-distill-qwen-14b"],
        "Ollama": ["llama3:latest", "codellama:7b", "mistral:latest"],
        "vLLM": ["meta-llama/Meta-Llama-3-8B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct"],
        "Nemotron": ["nvidia/nemotron-4-340b-instruct"],
        "Cloud APIs": ["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"],
    }

    def __init__(self) -> None:
        """Inicializa el modelo con la lista de mensajes y estados por defecto."""
        self._messages: List[ChatMessage] = []
        self._providers: List[str] = list(self.DEFAULT_PROVIDERS)
        self._selected_provider: str = self._providers[0]
        self._selected_model: str = self.DEFAULT_MODELS_MAP[self._selected_provider][0]
        self._status: str = "Listo"
        self._is_loading: bool = False
        self._listeners: List[Callable[[], None]] = []

    @property
    def messages(self) -> List[ChatMessage]:
        """Obtiene la lista de mensajes acumulados."""
        return list(self._messages)

    @property
    def providers(self) -> List[str]:
        """Obtiene los proveedores disponibles."""
        return list(self._providers)

    @property
    def current_provider(self) -> str:
        """Obtiene el proveedor actualmente seleccionado."""
        return self._selected_provider

    @property
    def current_model(self) -> str:
        """Obtiene el modelo actualmente seleccionado."""
        return self._selected_model

    @property
    def available_models(self) -> List[str]:
        """Obtiene la lista de modelos para el proveedor actual."""
        return list(self.DEFAULT_MODELS_MAP.get(self._selected_provider, ["default"]))

    @property
    def status(self) -> str:
        """Obtiene el estado actual del agente/badging."""
        return self._status

    @property
    def is_loading(self) -> bool:
        """Obtiene si hay una operación asíncrona en proceso."""
        return self._is_loading

    def add_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        """Agrega un nuevo mensaje al historial.

        Args:
            role (str): Rol del emisor ('user', 'assistant', 'system').
            content (str): Texto del mensaje.
            metadata (Optional[Dict[str, Any]]): Metadatos adicionales.

        Returns:
            ChatMessage: Objeto mensaje creado.
        """
        msg = ChatMessage(role=role, content=content, metadata=metadata)
        self._messages.append(msg)
        self._notify()
        return msg

    def clear_messages(self) -> None:
        """Limpia todo el historial de conversación."""
        self._messages.clear()
        self._notify()

    def set_provider(self, provider: str) -> None:
        """Actualiza el proveedor seleccionado y ajusta el modelo por defecto.

        Args:
            provider (str): Nombre del proveedor.
        """
        if provider in self._providers:
            self._selected_provider = provider
            models = self.available_models
            if models:
                self._selected_model = models[0]
            self._notify()

    def set_model(self, model: str) -> None:
        """Actualiza el modelo seleccionado.

        Args:
            model (str): Nombre del modelo.
        """
        self._selected_model = model
        self._notify()

    def set_status(self, status: str, is_loading: bool = False) -> None:
        """Actualiza el badge de estado e indicador de carga.

        Args:
            status (str): Texto de estado ('Listo', 'Generando...', 'Auto-corrigiendo').
            is_loading (bool): Indica si la UI debe deshabilitar controles.
        """
        self._status = status
        self._is_loading = is_loading
        self._notify()

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Registra un callback de escucha de cambios en el modelo.

        Args:
            listener (Callable[[], None]): Función a invocar cuando cambie el estado.
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[], None]) -> None:
        """Desregistra un callback de escucha.

        Args:
            listener (Callable[[], None]): Función a remover.
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self) -> None:
        """Notifica a todos los escuchas registrados."""
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                print(f"[ChatModel] Error en listener notification: {e}")
