# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Contratos e interfaces fundamentales de la suite LM-Chat™.
Diseñados para permitir el desarrollo concurrente y desacoplado por el Enjambre de Jules.
"""

import uuid
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncIterator, Callable
from dataclasses import dataclass

@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant"
    content: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ChatSession:
    """Representa una sesión de chat persistente con sus mensajes y metadatos."""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializa la sesión a un diccionario nativo JSON-compatible."""
        serialized_messages: List[Dict[str, Any]] = []
        for m in self.messages:
            if isinstance(m, ChatMessage):
                serialized_messages.append({
                    "role": m.role,
                    "content": m.content,
                    "metadata": m.metadata or {},
                })
            elif isinstance(m, dict):
                serialized_messages.append({
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                    "metadata": m.get("metadata") or {},
                })
            else:
                serialized_messages.append({
                    "role": getattr(m, "role", "user"),
                    "content": str(getattr(m, "content", m)),
                    "metadata": getattr(m, "metadata", {}) or {},
                })

        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": serialized_messages,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSession":
        """Instancia un ChatSession a partir de un diccionario."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not isinstance(data, dict):
            return cls(
                session_id=uuid.uuid4().hex,
                title="Nueva Conversación",
                created_at=now_iso,
                updated_at=now_iso,
                messages=[],
                metadata={},
            )

        raw_msgs = data.get("messages")
        if not isinstance(raw_msgs, list):
            raw_msgs = []

        msgs: List[ChatMessage] = []
        for m in raw_msgs:
            if isinstance(m, ChatMessage):
                msgs.append(m)
            elif isinstance(m, dict):
                msgs.append(
                    ChatMessage(
                        role=m.get("role", "user"),
                        content=m.get("content", ""),
                        metadata=m.get("metadata"),
                    )
                )
            elif isinstance(m, str):
                msgs.append(ChatMessage(role="user", content=m))

        sid = data.get("session_id") or uuid.uuid4().hex
        created = data.get("created_at") or now_iso
        updated = data.get("updated_at") or created
        title = data.get("title") or "Nueva Conversación"
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            session_id=sid,
            title=title,
            created_at=created,
            updated_at=updated,
            messages=msgs,
            metadata=metadata,
        )

@dataclass
class InferenceConfig:
    provider: str  # "lm_studio", "ollama", "vllm", "cloud"
    base_url: str
    model: str
    api_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 600.0

class IInferenceRouter(ABC):
    """Contrato para el Router Multi-Proveedor de Inferencia (Jules Issue #35)."""
    @abstractmethod
    async def chat_completion(self, messages: List[ChatMessage], config: InferenceConfig) -> str:
        """Genera una respuesta completa."""
        pass

    @abstractmethod
    async def chat_stream(self, messages: List[ChatMessage], config: InferenceConfig) -> AsyncIterator[str]:
        """Genera una respuesta en streaming asíncrono para mantener 60 FPS."""
        pass

class IStageContextSerializer(ABC):
    """Contrato para el serializador del escenario espacial OpenUSD (Jules Issue #36)."""
    @abstractmethod
    def get_stage_context_as_json(self, max_depth: int = 4) -> str:
        """Extrae la jerarquía de prims, transforms y luces en formato estructurado JSON."""
        pass

    @abstractmethod
    def get_prim_summary(self, prim_path: str) -> Dict[str, Any]:
        """Extrae atributos específicos de un prim para alimentar el razonamiento del LLM."""
        pass

class IMCPClientRegistry(ABC):
    """Contrato para el cliente y registro de herramientas MCP (Jules Issue #37)."""
    @abstractmethod
    async def register_server(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None) -> bool:
        """Registra e inicia un servidor MCP local."""
        pass

    @abstractmethod
    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """Lista todas las herramientas disponibles en formato compatible con LLM function calling."""
        pass

    @abstractmethod
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoca una herramienta MCP y retorna el resultado estructurado."""
        pass

class IExecutionEngine(ABC):
    """Contrato para el motor de ejecución y autorreflexión ReAct (Jules Issue #38)."""
    @abstractmethod
    def execute_script(self, python_code: str, dry_run: bool = False) -> Dict[str, Any]:
        """Ejecuta código Python usando omni.kit.commands para Undo/Redo y captura excepciones."""
        pass

    @abstractmethod
    def format_reflection_prompt(self, failed_code: str, traceback_str: str) -> str:
        """Construye el prompt de autorreflexión para que el LLM corrija el código."""
        pass

class IChatView(ABC):
    """Contrato para la interfaz gráfica omni.ui (Jules Issue #39)."""
    @abstractmethod
    def set_submit_callback(self, callback: Callable[[str], Any]) -> None:
        """Establece la función a invocar al enviar un mensaje."""
        pass

    @abstractmethod
    def append_message(self, role: str, message: str) -> None:
        """Agrega un mensaje a la conversación en el hilo de UI."""
        pass

    @abstractmethod
    def update_status(self, status: str, is_loading: bool = False) -> None:
        """Actualiza el badge de estado en la UI."""
        pass


class IChatHistoryManager(ABC):
    """Contrato para el gestor de persistencia e historial de chats locales."""

    @abstractmethod
    def create_session(
        self, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> ChatSession:
        """Crea e inicializa una nueva sesión de chat persistente."""
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Recupera una sesión existente por su identificador único."""
        pass

    @abstractmethod
    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lista los metadatos resumidos de todas las sesiones ordenadas por fecha de actualización."""
        pass

    @abstractmethod
    def save_session(self, session: ChatSession) -> bool:
        """Persiste una sesión en el almacenamiento local de forma atómica."""
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Elimina una sesión del almacenamiento local."""
        pass

    @abstractmethod
    def clear_all_sessions(self) -> bool:
        """Elimina todas las sesiones almacenadas localmente."""
        pass

    @abstractmethod
    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        """Busca sesiones que coincidan en título o contenido de mensajes."""
        pass

    @abstractmethod
    def export_session_json(self, session_id: str) -> Optional[str]:
        """Exporta una sesión a formato JSON como string."""
        pass

    @abstractmethod
    def import_session_json(self, json_content: str) -> Optional[ChatSession]:
        """Importa una sesión desde una cadena JSON y la persiste localmente."""
        pass

