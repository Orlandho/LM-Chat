# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Modelo de datos para la interfaz gráfica omni.ui (Paradigma MDV).
Maneja el estado de la conversación, sesiones locales persistentes,
proveedores de inferencia y badges de estado.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable
from core.interfaces import ChatMessage, ChatSession, IChatHistoryManager
from logic.chat_history import LocalChatHistoryManager


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

    def __init__(self, history_manager: Optional[IChatHistoryManager] = None) -> None:
        """Inicializa el modelo con la lista de mensajes, gestor de historial y estados por defecto.

        Args:
            history_manager (Optional[IChatHistoryManager]): Gestor de historial de chat inyectado.
        """
        self._history_manager: IChatHistoryManager = (
            history_manager if history_manager is not None else LocalChatHistoryManager()
        )
        self._current_session: Optional[ChatSession] = None
        self._messages: List[ChatMessage] = []
        self._providers: List[str] = list(self.DEFAULT_PROVIDERS)
        self._selected_provider: str = self._providers[0]
        self._selected_model: str = self.DEFAULT_MODELS_MAP[self._selected_provider][0]
        self._status: str = "Listo"
        self._is_loading: bool = False
        self._listeners: List[Callable[[], None]] = []

    @property
    def history_manager(self) -> IChatHistoryManager:
        """Obtiene el gestor de historial de chat."""
        return self._history_manager

    @property
    def current_session(self) -> Optional[ChatSession]:
        """Obtiene la sesión de chat activa actual."""
        return self._current_session

    @property
    def current_session_id(self) -> Optional[str]:
        """Obtiene el identificador de la sesión activa."""
        return self._current_session.session_id if self._current_session else None

    @property
    def current_session_title(self) -> str:
        """Obtiene el título legible de la sesión activa."""
        return self._current_session.title if self._current_session else LocalChatHistoryManager.DEFAULT_TITLE

    @property
    def sessions(self) -> List[Dict[str, Any]]:
        """Obtiene la lista resumida de todas las sesiones locales."""
        return self._history_manager.list_sessions()

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
    def selected_provider(self) -> str:
        """Alias para current_provider."""
        return self._selected_provider

    @property
    def current_model(self) -> str:
        """Obtiene el modelo actualmente seleccionado."""
        return self._selected_model

    @property
    def selected_model(self) -> str:
        """Alias para current_model."""
        return self._selected_model

    @property
    def available_models(self) -> List[str]:
        """Obtiene la lista de modelos para el proveedor actual."""
        return list(self.DEFAULT_MODELS_MAP.get(self._selected_provider, ["default"]))

    def _find_matching_provider(self, provider_query: Optional[str]) -> Optional[str]:
        """Busca el nombre canónico del proveedor de forma tolerante a mayúsculas y formatos."""
        if not provider_query:
            return None
        norm_query = provider_query.lower().replace(" ", "").replace("_", "").replace("-", "")
        for p in self._providers:
            norm_p = p.lower().replace(" ", "").replace("_", "").replace("-", "")
            if norm_query == norm_p:
                return p
        if norm_query in ("cloud", "cloudapi", "cloudapis"):
            for p in self._providers:
                if "cloud" in p.lower():
                    return p
        if norm_query in ("lmstudio", "lm_studio"):
            for p in self._providers:
                if "lm" in p.lower() and "studio" in p.lower():
                    return p
        return None

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
        """Agrega un nuevo mensaje al historial y lo persiste automáticamente.

        Args:
            role (str): Rol del emisor ('user', 'assistant', 'system').
            content (str): Texto del mensaje.
            metadata (Optional[Dict[str, Any]]): Metadatos adicionales.

        Returns:
            ChatMessage: Objeto mensaje creado.
        """
        msg = ChatMessage(role=role, content=content, metadata=metadata)
        self._messages.append(msg)

        # Inicializar sesión si no existe aún
        if self._current_session is None:
            self._current_session = self._history_manager.create_session(
                metadata={"provider": self._selected_provider, "model": self._selected_model}
            )

        # Auto-titular de forma inteligente la sesión en el primer prompt de usuario
        default_titles = (LocalChatHistoryManager.DEFAULT_TITLE, "Nueva Conversación", "Nueva conversación")
        if role == "user" and self._current_session.title in default_titles:
            self._current_session.title = LocalChatHistoryManager.generate_title_from_prompt(content)

        # Actualizar mensajes y marca de tiempo en la sesión persistida
        self._current_session.messages = list(self._messages)
        self._current_session.updated_at = datetime.now(timezone.utc).isoformat()
        self._history_manager.save_session(self._current_session)

        self._notify()
        return msg

    def clear_messages(self) -> None:
        """Limpia todo el historial de conversación actual."""
        self._messages.clear()
        if self._current_session:
            self._current_session.messages.clear()
            self._current_session.updated_at = datetime.now(timezone.utc).isoformat()
            self._history_manager.save_session(self._current_session)
        self._notify()

    def new_session(self, title: Optional[str] = None) -> ChatSession:
        """Inicia una nueva sesión de chat limpia y persistente.

        Args:
            title (Optional[str]): Título opcional de la nueva sesión.

        Returns:
            ChatSession: Nueva sesión creada y activa.
        """
        session = self._history_manager.create_session(
            title=title,
            metadata={"provider": self._selected_provider, "model": self._selected_model},
        )
        self._current_session = session
        self._messages.clear()
        self._notify()
        return session

    def load_session(self, session_id: str) -> bool:
        """Carga una sesión guardada desde el almacenamiento local.

        Args:
            session_id (str): Identificador de la sesión.

        Returns:
            bool: True si la sesión se cargó con éxito, False si no existe.
        """
        session = self._history_manager.get_session(session_id)
        if not session:
            return False

        self._current_session = session
        self._messages = list(session.messages)

        # Sincronizar proveedor y modelo si estaban almacenados en la sesión
        if session.metadata:
            prov = session.metadata.get("provider")
            mod = session.metadata.get("model")
            matched_prov = self._find_matching_provider(prov) if prov else None
            if matched_prov:
                self._selected_provider = matched_prov
            if mod:
                self._selected_model = mod

        self._notify()
        return True

    def delete_session(self, session_id: str) -> bool:
        """Elimina una sesión del historial local.

        Args:
            session_id (str): Identificador de la sesión a eliminar.

        Returns:
            bool: True si se eliminó, False en caso contrario.
        """
        success = self._history_manager.delete_session(session_id)
        if success:
            if self._current_session and self._current_session.session_id == session_id:
                self._current_session = None
                self._messages.clear()
            self._notify()
        return success

    def rename_session(self, session_id: str, new_title: str) -> bool:
        """Renombra una sesión guardada en el historial local.

        Args:
            session_id (str): Identificador de la sesión.
            new_title (str): Nuevo título para la conversación.

        Returns:
            bool: True si se actualizó con éxito.
        """
        session = self._history_manager.get_session(session_id)
        if not session:
            return False

        session.title = new_title.strip() if new_title else LocalChatHistoryManager.DEFAULT_TITLE
        session.updated_at = datetime.now(timezone.utc).isoformat()
        saved = self._history_manager.save_session(session)
        if saved:
            if self._current_session and self._current_session.session_id == session_id:
                self._current_session.title = session.title
            self._notify()
        return saved

    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        """Busca sesiones que contengan la consulta en su título o mensajes.

        Args:
            query (str): Texto a buscar.

        Returns:
            List[Dict[str, Any]]: Resultados de la búsqueda.
        """
        return self._history_manager.search_sessions(query)

    def export_current_session(self) -> Optional[str]:
        """Exporta la sesión actual a una cadena en formato JSON.

        Returns:
            Optional[str]: JSON serializado o None.
        """
        if not self._current_session:
            return None
        return self._history_manager.export_session_json(self._current_session.session_id)

    def import_session(self, json_content: str, switch_to: bool = True) -> Optional[ChatSession]:
        """Importa una sesión desde una cadena JSON.

        Args:
            json_content (str): Texto JSON.
            switch_to (bool): Si es True, activa de inmediato la sesión importada.

        Returns:
            Optional[ChatSession]: La sesión importada o None.
        """
        session = self._history_manager.import_session_json(json_content)
        if session and switch_to:
            self._current_session = session
            self._messages = list(session.messages)
            self._notify()
        return session

    def set_provider(self, provider: str) -> None:
        """Actualiza el proveedor seleccionado y ajusta el modelo por defecto.

        Args:
            provider (str): Nombre del proveedor.
        """
        matched = self._find_matching_provider(provider)
        if matched:
            self._selected_provider = matched
            models = self.available_models
            if models:
                self._selected_model = models[0]
            if self._current_session:
                if not self._current_session.metadata:
                    self._current_session.metadata = {}
                self._current_session.metadata["provider"] = self._selected_provider
                self._current_session.metadata["model"] = self._selected_model
                self._history_manager.save_session(self._current_session)
            self._notify()

    def set_model(self, model: str) -> None:
        """Actualiza el modelo seleccionado.

        Args:
            model (str): Nombre del modelo.
        """
        self._selected_model = model
        if self._current_session:
            if not self._current_session.metadata:
                self._current_session.metadata = {}
            self._current_session.metadata["model"] = self._selected_model
            self._history_manager.save_session(self._current_session)
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
