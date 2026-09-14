# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Contratos e interfaces fundamentales del OmniAgent Harness.
Diseñados para permitir el desarrollo concurrente y desacoplado por el Enjambre de Jules.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncIterator, Callable
from dataclasses import dataclass

@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant"
    content: str
    metadata: Optional[Dict[str, Any]] = None

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
