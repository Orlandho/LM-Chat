---
title: "Contratos e Interfaces del Sistema (Contract-First)"
tipo: "especificacion"
modulo: "architecture"
version: "1.2.0"
estado: "vigente"
fecha_revision: "2026-10-28"
commit_referencia: "c0c41db"
autor: "Orlando Dorival"
aliases:
  - "Contratos e Interfaces"
  - "Interfaces LM-Chat"
  - "Core Interfaces"
tags:
  - "interfaces"
  - "contratos"
  - "typing"
  - "python"
  - "dataclasses"
---

# Contratos e Interfaces del Sistema (Contract-First)

## 1. Filosofía Contract-First y Tipado Estricto

En el desarrollo de **LM-Chat™**, la arquitectura se rige por el principio de **Desarrollo Basado en Contratos (Contract-First Design)**. Este paradigma, consolidado en `core/interfaces.py` y `core/policies.py`, persigue dos objetivos esenciales:
1. **Desacoplamiento Absoluto:** Cada subsistema expone interfaces puras (`abc.ABC`), permitiendo que implementaciones concretas (por ejemplo, `InferenceRouter`, `LocalChatHistoryManager` o `USDController`) sean sustituidas, ampliadas o probadas con dobles de prueba (mocks) sin alterar el resto de la aplicación.
2. **Concurrencia Multi-Agente (Jules & Swarms):** Habilita el trabajo paralelo de agentes autónomos de codificación en ramas separadas, eliminando conflictos de integración al compartir contratos tipados inmutables.

---

## 2. Catálogo de Modelos de Datos y Enumeraciones

### A. Modelos Conversacionales y de Sesión

```python
@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ChatSession:
    session_id: str
    title: str
    created_at: str  # ISO 8601 UTC
    updated_at: str  # ISO 8601 UTC
    messages: List[ChatMessage]
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSession": ...
```

### B. Modos de Ejecución Espacial

```python
class ExecutionMode(str, Enum):
    IMMEDIATE = "immediate"            # ⚡ Fast Act / Ejecución autónoma instantánea
    PLAN_AND_CONFIRM = "plan_and_confirm"  # 📝 Planificación previa, requiere confirmación interactiva
```

### C. Configuración de Inferencia y Servidores MCP

```python
@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    enabled: bool = True
    def to_dict(self) -> Dict[str, Any]: ...

@dataclass
class InferenceConfig:
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 600.0
    turbo_mode: bool = False
    is_reasoning: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    integrations: Optional[List[Dict[str, Any]]] = None
```

### D. Nodos de Inferencia y Topología de Cluster

```python
class ClusterFailoverStrategy(str, Enum):
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    LOWEST_LATENCY = "lowest_latency"

@dataclass
class ClusterNode:
    name: str
    url: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    weight: int = 1
    is_active: bool = True
    is_healthy: bool = True
    last_latency_ms: float = 0.0
    last_checked_at: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClusterNode": ...
```

---

## 3. Interfaces Abstractas de la Capa de Lógica

### `IInferenceRouter`
```python
class IInferenceRouter(ABC):
    @abstractmethod
    async def chat_completion(self, messages: List[ChatMessage], config: InferenceConfig) -> str:
        """Genera una respuesta síncrona completa."""

    @abstractmethod
    async def chat_stream(self, messages: List[ChatMessage], config: InferenceConfig) -> AsyncIterator[str]:
        """Genera una respuesta en streaming asíncrono para mantener los 60 FPS del renderizado."""
```

### `IStageContextSerializer`
```python
class IStageContextSerializer(ABC):
    @abstractmethod
    def get_stage_context_as_json(self, max_depth: int = 4) -> str:
        """Extrae la jerarquía de prims, transforms y luces en formato estructurado JSON."""

    @abstractmethod
    def get_prim_summary(self, prim_path: str) -> Dict[str, Any]:
        """Extrae atributos específicos de un prim para alimentar el razonamiento del LLM."""
```

### `IUSDInspector`
```python
class IUSDInspector(ABC):
    @abstractmethod
    def audit_missing_assets(self) -> List[Dict[str, Any]]:
        """Escanea todos los atributos Sdf.AssetPath en el Stage y valida la existencia de archivos."""

    @abstractmethod
    def find_prims_by_query(self, query_criteria: Dict[str, Any]) -> List[str]:
        """Busca prims en el Stage según criterios semánticos (tipo, visibilidad, atributos)."""

    @abstractmethod
    def get_layer_stack_status(self) -> Dict[str, Any]:
        """Informa sobre el estado de la pila de capas (capa raíz, capas sucias, anónimas)."""
```

### `IAgentPolicy`
```python
class IAgentPolicy(ABC):
    @abstractmethod
    def validate_code(self, python_code: str) -> Tuple[bool, Optional[str]]:
        """Valida que el código generado no viole las políticas de seguridad espacial antes de ejecutar."""

    @abstractmethod
    def is_prim_protected(self, prim_path: str) -> bool:
        """Determina si una ruta en el Stage corresponde a un elemento protegido del sistema."""
```

### `IMCPClientRegistry`
```python
class IMCPClientRegistry(ABC):
    @abstractmethod
    async def register_server(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None) -> bool:
        """Registra e inicia un servidor MCP local."""

    @abstractmethod
    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """Lista todas las herramientas disponibles en formato compatible con LLM function calling."""

    @abstractmethod
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoca una herramienta MCP y retorna el resultado estructurado."""
```

### `IChatHistoryManager`
```python
class IChatHistoryManager(ABC):
    @abstractmethod
    def create_session(self, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ChatSession: ...
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[ChatSession]: ...
    @abstractmethod
    def list_sessions(self) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def save_session(self, session: ChatSession) -> bool: ...
    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...
    @abstractmethod
    def clear_all_sessions(self) -> bool: ...
    @abstractmethod
    def search_sessions(self, query: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def export_session_json(self, session_id: str) -> Optional[str]: ...
    @abstractmethod
    def import_session_json(self, json_content: str) -> Optional[ChatSession]: ...
```

### `ISettingsManager`
```python
class ISettingsManager(ABC):
    @abstractmethod
    def get_default_provider(self) -> str: ...
    @abstractmethod
    def set_default_provider(self, provider_name: str) -> None: ...
    @abstractmethod
    def get_default_model(self, provider_name: str) -> str: ...
    @abstractmethod
    def set_default_model(self, provider_name: str, model_name: str) -> None: ...
    @abstractmethod
    def get_provider_config(self, provider_name: str) -> Dict[str, Any]: ...
    @abstractmethod
    def update_provider_config(self, provider_name: str, **kwargs: Any) -> bool: ...
    @abstractmethod
    def get_effective_api_key(self, provider_name: str) -> Optional[str]: ...
    @abstractmethod
    def get_all_providers(self) -> List[str]: ...
    @abstractmethod
    def get_available_models(self, provider_name: str) -> List[str]: ...
    @abstractmethod
    def save(self) -> bool: ...
    @abstractmethod
    def load(self) -> Dict[str, Any]: ...
    @abstractmethod
    def reset_to_defaults(self) -> None: ...
    @abstractmethod
    async def fetch_remote_models(self, provider_name: str) -> List[str]: ...
    # Métodos con implementación por defecto para extensiones avanzadas
    def get_execution_mode(self) -> str: ...
    def set_execution_mode(self, mode: str) -> None: ...
    def is_turbo_mode(self) -> bool: ...
    def set_turbo_mode(self, enabled: bool) -> None: ...
    def get_mcp_servers(self) -> List[Dict[str, Any]]: ...
    def add_mcp_server(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None, enabled: bool = True) -> bool: ...
    def remove_mcp_server(self, name: str) -> bool: ...
    def get_presets(self, provider_name: str) -> List[Dict[str, str]]: ...
    def add_custom_model(self, provider_name: str, model_name: str) -> None: ...
    async def test_connection(self, provider_name: str, base_url: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]: ...
    def get_cluster_manager(self) -> Any: ...
    def get_lm_studio_vram_manager(self) -> Any: ...
```

### `IClusterManager` y `ILMStudioVRAMManager`
```python
class IClusterManager(ABC):
    @abstractmethod
    def get_nodes(self) -> List[ClusterNode]: ...
    @abstractmethod
    def add_node(self, node: ClusterNode) -> None: ...
    @abstractmethod
    def remove_node(self, name: str) -> bool: ...
    @abstractmethod
    async def check_health_all(self) -> Dict[str, bool]: ...
    @abstractmethod
    def select_node(self) -> Optional[ClusterNode]: ...
    @abstractmethod
    def mark_node_failure(self, name: str) -> None: ...

class ILMStudioVRAMManager(ABC):
    @abstractmethod
    async def list_loaded_models(self) -> List[Dict[str, Any]]: ...
    @abstractmethod
    async def load_model(self, model_name: str, context_length: Optional[int] = None, flash_attention: bool = True, offload_kv_cache_to_gpu: bool = True) -> Dict[str, Any]: ...
    @abstractmethod
    async def unload_model(self, instance_id: str) -> Dict[str, Any]: ...
```

---

## 4. Gobernanza y Configuración de Políticas (`core/policies.py`)

```python
@dataclass
class AgentPolicyConfig:
    max_prims_creation_limit: int = 500
    max_code_size: int = 100_000
    max_loop_iterations: int = 10_000
    protected_paths: Tuple[str, ...] = (
        "/OmniverseKit_Root",
        "/Render",
        "/World/System",
        "/Library",
    )
    forbidden_modules: Tuple[str, ...] = (
        "shutil", "subprocess", "socket", "http", "urllib",
        "requests", "ftplib", "telnetlib", "smtplib", "webbrowser",
        "winreg", "ctypes", "posix", "nt",
    )
    forbidden_builtins: Tuple[str, ...] = (
        "eval", "compile", "exec", "__import__", "breakpoint",
    )
    forbidden_os_attributes: Tuple[str, ...] = (
        "system", "popen", "spawn", "remove", "rmdir",
        "unlink", "kill", "rename", "replace", "truncate",
    )
```

Toda implementación de `USDController` o motores derivados debe validar el código contra esta política antes de cualquier interacción con la API de Omniverse.
