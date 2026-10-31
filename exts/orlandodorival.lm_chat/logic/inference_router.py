# -*- coding: utf-8 -*-

"""
Inference Router Module for Multi-Provider LLM Integration.

This module implements the InferenceRouter class, which acts as an asynchronous,
decoupled gateway for directing chat completion requests across multiple LLM providers:
LM Studio, Ollama, vLLM (Enterprise/Nemotron), Cloud APIs (OpenAI, Anthropic, Gemini, NVIDIA Spark).

Integrates contemporary LLM models (OpenAI GPT-4o / o3-mini / GPT-4.5, Claude 3.7 Sonnet,
Gemini 2.0 Flash, NVIDIA NIM Nemotron-70B, Ollama/LM Studio) and provides deep diagnostic classification
on any communication failure.
"""

from __future__ import annotations

import os
import re
import asyncio
import json
import time
import functools
from typing import AsyncGenerator, Dict, List, Optional, Any, Tuple
import aiohttp

from logic.logger import get_logger
from logic.diagnostics import diagnose_inference_failure, ErrorDiagnostic


logger = get_logger("InferenceRouter")

REASONING_MODEL_PATTERNS: List[str] = [
    r"^o1(-mini|-preview)?",
    r"^o3(-mini)?",
    r"deepseek-r1",
    r"deepseek-reasoner",
    r"reasoner",
    r"qwq",
    r".*thinking.*",
    r".*-r1.*",
    r"claude-3-7",
    r"deepseek-v4",
    r"gemini-3(\.[0-9]+)?",
]


# Pre-compiled consolidated regular expression for fast reasoning model detection
_REASONING_MODEL_REGEX = re.compile("|".join(REASONING_MODEL_PATTERNS), re.IGNORECASE)


@functools.lru_cache(maxsize=256)
def is_reasoning_model(model_name: str) -> bool:
    """Evalúa si un modelo cuenta con capacidades de razonamiento extendido (Plan 01).

    Optimized with pre-compiled regex consolidation and LRU caching for O(1) repeated lookups (~40x speedup).
    """
    if not model_name:
        return False
    clean_name = model_name.lower().strip()
    return bool(_REASONING_MODEL_REGEX.search(clean_name))


class StreamingReasoningParser:
    """
    Parser incremental para flujos SSE que separa bloques de pensamiento (<think>...</think>)
    del contenido final, incluso cuando las etiquetas están fragmentadas entre chunks.
    """

    def __init__(self) -> None:
        self._in_think: bool = False
        self._buffer: str = ""

    @property
    def in_thinking_phase(self) -> bool:
        """Retorna True si el parser está actualmente dentro de un bloque de pensamiento."""
        return self._in_think

    def process_chunk(self, text: str) -> List[Dict[str, str]]:
        """
        Procesa un fragmento de texto y retorna lista de fragmentos categorizados:
        [{"type": "reasoning" | "content", "text": str}, ...]
        """
        if not text:
            return []

        self._buffer += text
        results: List[Dict[str, str]] = []

        while self._buffer:
            if not self._in_think:
                tag_idx = self._buffer.find("<think>")
                if tag_idx != -1:
                    if tag_idx > 0:
                        content_part = self._buffer[:tag_idx]
                        results.append({"type": "content", "text": content_part})
                    self._buffer = self._buffer[tag_idx + len("<think>"):]
                    self._in_think = True
                else:
                    # Comprobar si el final del buffer tiene un prefijo parcial de <think>
                    held = 0
                    for i in range(1, len("<think>")):
                        if self._buffer.endswith("<think>"[:i]):
                            held = i
                            break
                    if held > 0:
                        emit_part = self._buffer[:-held]
                        if emit_part:
                            results.append({"type": "content", "text": emit_part})
                        self._buffer = self._buffer[-held:]
                        break
                    else:
                        results.append({"type": "content", "text": self._buffer})
                        self._buffer = ""
                        break
            else:
                tag_idx = self._buffer.find("</think>")
                if tag_idx != -1:
                    if tag_idx > 0:
                        reasoning_part = self._buffer[:tag_idx]
                        results.append({"type": "reasoning", "text": reasoning_part})
                    self._buffer = self._buffer[tag_idx + len("</think>"):]
                    self._in_think = False
                else:
                    held = 0
                    for i in range(1, len("</think>")):
                        if self._buffer.endswith("</think>"[:i]):
                            held = i
                            break
                    if held > 0:
                        emit_part = self._buffer[:-held]
                        if emit_part:
                            results.append({"type": "reasoning", "text": emit_part})
                        self._buffer = self._buffer[-held:]
                        break
                    else:
                        results.append({"type": "reasoning", "text": self._buffer})
                        self._buffer = ""
                        break

        return results

    def flush(self) -> List[Dict[str, str]]:
        """Descarga el contenido residual del buffer al finalizar el stream."""
        results: List[Dict[str, str]] = []
        if self._buffer:
            res_type = "reasoning" if self._in_think else "content"
            results.append({"type": res_type, "text": self._buffer})
            self._buffer = ""
        self._in_think = False
        return results

    def feed_chunk(self, text: str = "", reasoning_chunk: str = "") -> Tuple[str, str]:
        """
        Método de conveniencia que procesa texto o razonamiento nativo, retornando (thoughts, content).
        """
        thoughts = []
        contents = []
        if reasoning_chunk:
            thoughts.append(reasoning_chunk)
        if text:
            items = self.process_chunk(text)
            for item in items:
                if item["type"] == "reasoning":
                    thoughts.append(item["text"])
                else:
                    contents.append(item["text"])
        return "".join(thoughts), "".join(contents)


class InferenceRouter:
    """
    Asynchronous Multi-Provider Router for LLM Inference.

    Supports LM Studio, Ollama, vLLM, OpenAI, Anthropic Claude, Google Gemini, and NVIDIA Spark.
    Ensures non-blocking streaming requests for Omniverse (60 FPS rendering thread).
    """

    DEFAULT_ENDPOINTS: Dict[str, str] = {
        "lm_studio": "http://localhost:1234/v1",
        "lm studio": "http://localhost:1234/v1",
        "lmstudio": "http://localhost:1234/v1",
        "ollama": "http://localhost:11434/v1",
        "vllm": "http://localhost:8000/v1",
        "cloud": "https://api.openai.com/v1",
        "cloud apis": "https://api.openai.com/v1",
        "openai": "https://api.openai.com/v1",
        "openai api": "https://api.openai.com/v1",
        "claude": "https://api.anthropic.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "claude api": "https://api.anthropic.com/v1",
        "nvidia_spark": "https://integrate.api.nvidia.com/v1",
        "nvidia spark": "https://integrate.api.nvidia.com/v1",
        "nemotron": "https://integrate.api.nvidia.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        "google": "https://generativelanguage.googleapis.com/v1beta/openai",
        "google gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        "google gemini api": "https://generativelanguage.googleapis.com/v1beta/openai",
        "cluster": "http://localhost:1234/v1",
    }

    DEFAULT_MODELS: Dict[str, str] = {
        "lm_studio": "local-model",
        "lm studio": "local-model",
        "lmstudio": "local-model",
        "ollama": "llama3",
        "vllm": "nvidia/nemotron-4-70b-instruct",
        "cloud": "gpt-4o",
        "cloud apis": "gpt-4o",
        "openai": "gpt-4o",
        "openai api": "gpt-4o",
        "claude": "claude-3-7-sonnet-latest",
        "anthropic": "claude-3-7-sonnet-latest",
        "claude api": "claude-3-7-sonnet-latest",
        "nvidia_spark": "nvidia/llama-3.1-nemotron-70b-instruct",
        "nvidia spark": "nvidia/llama-3.1-nemotron-70b-instruct",
        "nemotron": "nvidia/nemotron-4-340b-instruct",
        "gemini": "gemini-3.8-flash",
        "google": "gemini-3.8-flash",
        "google gemini": "gemini-3.8-flash",
        "google gemini api": "gemini-3.8-flash",
        "cluster": "deepseek-v4",
    }

    CANONICAL_PROVIDERS: Dict[str, str] = {
        "lm_studio": "lm_studio",
        "lmstudio": "lm_studio",
        "lm studio": "lm_studio",
        "ollama": "ollama",
        "vllm": "vllm",
        "cloud": "cloud",
        "cloud apis": "cloud",
        "openai": "openai",
        "open_ai": "openai",
        "openai api": "openai",
        "claude": "claude",
        "anthropic": "claude",
        "claude api": "claude",
        "nvidia": "nvidia_spark",
        "spark": "nvidia_spark",
        "nvidia_spark": "nvidia_spark",
        "nvidia spark": "nvidia_spark",
        "nemotron": "nvidia_spark",
        "gemini": "gemini",
        "google": "gemini",
        "google gemini": "gemini",
        "google_gemini": "gemini",
        "google gemini api": "gemini",
        "gemini api": "gemini",
        "cluster": "cluster",
        "clusters": "cluster",
        "local_cluster": "cluster",
        "local cluster": "cluster",
    }

    @classmethod
    @functools.lru_cache(maxsize=128)
    def canonicalize_provider(cls, provider: str) -> str:
        """Normaliza el identificador del proveedor a su clave interna estándar."""
        if not provider:
            return "lm_studio"
        clean = provider.strip().lower()
        if clean in cls.CANONICAL_PROVIDERS:
            return cls.CANONICAL_PROVIDERS[clean]
        clean_underscore = clean.replace(" ", "_")
        if clean_underscore in cls.CANONICAL_PROVIDERS:
            return cls.CANONICAL_PROVIDERS[clean_underscore]
        return clean

    def __init__(
        self,
        provider: str = "lm_studio",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 600.0,
        cluster_manager: Optional[Any] = None,
    ) -> None:
        """
        Initializes the InferenceRouter with specified provider configuration.

        Args:
            provider (str): Provider identifier ('lm_studio', 'ollama', 'vllm', 'cloud', 'openai', 'claude', 'gemini', 'cluster').
            base_url (Optional[str]): Custom base URL override.
            api_key (Optional[str]): API key for authentication (optional for local).
            model (Optional[str]): Model name override.
            timeout (float): Request timeout in seconds (default: 600s).
            cluster_manager (Optional[Any]): Gestor de cluster multi-nodo con conmutación por error.
        """
        self._timeout = timeout
        self._cluster_manager = cluster_manager
        self.set_provider(provider=provider, base_url=base_url, model=model, api_key=api_key)

    @property
    def cluster_manager(self) -> Optional[Any]:
        """Gestor de cluster multi-nodo activo."""
        return self._cluster_manager

    def set_cluster_manager(self, cluster_manager: Optional[Any]) -> None:
        """Configura el gestor de cluster multi-nodo."""
        self._cluster_manager = cluster_manager

    def set_provider(
        self,
        provider: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Updates the active provider and associated parameters.

        Args:
            provider (str): Provider key ('lm_studio', 'ollama', 'vllm', 'cloud', 'openai', 'claude', 'gemini').
            base_url (Optional[str]): Custom base URL or default for provider.
            model (Optional[str]): Model identifier.
            api_key (Optional[str]): API Key for cloud services.
        """
        can_prov = self.canonicalize_provider(provider)
        self._provider = can_prov

        # Resolve and validate base URL
        if base_url:
            cleaned_url = base_url.strip().replace("\r", "").replace("\n", "").rstrip("/")
            if not (cleaned_url.startswith("http://") or cleaned_url.startswith("https://")):
                raise ValueError(f"Invalid base_url scheme: '{base_url}'. Must start with http:// or https://")
            self._base_url = cleaned_url
        else:
            self._base_url = self.DEFAULT_ENDPOINTS.get(
                can_prov, self.DEFAULT_ENDPOINTS.get(provider.lower().strip(), "http://localhost:1234/v1")
            )

        # Resolve default model
        if model:
            self._model = model
        else:
            self._model = self.DEFAULT_MODELS.get(
                can_prov, self.DEFAULT_MODELS.get(provider.lower().strip(), "local-model")
            )

        # Sanitize API key to prevent CRLF HTTP header injection
        if api_key:
            self._api_key = api_key.strip().replace("\r", "").replace("\n", "")
        else:
            self._api_key = None

        logger.info(
            f"Configurado proveedor='{self._provider}' | modelo='{self._model}' | base_url='{self._base_url}'"
        )

    @property
    def provider(self) -> str:
        """Returns the current provider name."""
        return self._provider

    @property
    def base_url(self) -> str:
        """Returns the current base URL."""
        return self._base_url

    @property
    def model(self) -> str:
        """Returns the current model name."""
        return self._model

    @property
    def api_key(self) -> Optional[str]:
        """Returns the current API key if set."""
        return self._api_key

    @property
    def timeout(self) -> float:
        """Returns the configured request timeout."""
        return self._timeout

    def _is_anthropic_direct(self) -> bool:
        """Determines if Anthropic messages API protocol is active."""
        can_p = self.canonicalize_provider(self._provider)
        return (can_p == "claude") or ("api.anthropic.com" in self._base_url)

    def _prepare_payload(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Formats the payload according to whether Anthropic direct or standard OpenAI format is used."""
        target_model = model or self._model
        if self._is_anthropic_direct():
            system_text = ""
            raw_msgs = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    system_text = f"{system_text}\n{content}".strip() if system_text else content
                elif role in ("user", "assistant"):
                    raw_msgs.append({"role": role, "content": content})

            # Anthropic requires strictly alternating user/assistant messages with non-empty content
            merged_msgs: List[Dict[str, str]] = []
            for m in raw_msgs:
                c = m.get("content", "").strip()
                if not c:
                    continue
                r = m.get("role", "user")
                if merged_msgs and merged_msgs[-1]["role"] == r:
                    merged_msgs[-1]["content"] = f"{merged_msgs[-1]['content']}\n\n{c}"
                else:
                    merged_msgs.append({"role": r, "content": c})

            if not merged_msgs:
                merged_msgs.append({"role": "user", "content": "Hola"})
            elif merged_msgs[0]["role"] != "user":
                merged_msgs.insert(0, {"role": "user", "content": "Inicio de conversación"})

            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": merged_msgs,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "temperature": temperature,
                "stream": stream,
            }
            if system_text:
                payload["system"] = system_text
            for k, v in kwargs.items():
                if k not in payload:
                    payload[k] = v
            return payload

        # Standard OpenAI-compatible format (OpenAI, Ollama, LM Studio, NVIDIA Spark, vLLM, Google Gemini)
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": stream,
        }

        # Check for reasoning models which reject 'temperature' and require 'max_completion_tokens'
        is_reasoning = is_reasoning_model(target_model)

        if not is_reasoning:
            payload["temperature"] = temperature

        # Handle max_tokens vs max_completion_tokens for reasoning models
        for k, v in kwargs.items():
            if is_reasoning and k == "max_tokens":
                payload["max_completion_tokens"] = v
            elif k not in payload and k not in ("turbo_mode", "turbo"):
                payload[k] = v

        if is_reasoning and "max_completion_tokens" not in payload:
            payload["max_completion_tokens"] = kwargs.get("max_tokens", 4096)

        return payload

    def _build_payload(
        self,
        messages: Any,
        config: Optional[InferenceConfig] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Construye el payload adaptativo para la API a partir de mensajes y configuración."""
        raw_msgs = []
        for m in messages:
            if hasattr(m, "role") and hasattr(m, "content"):
                raw_msgs.append({"role": m.role, "content": m.content})
            elif isinstance(m, dict):
                raw_msgs.append(m)
            else:
                raw_msgs.append({"role": "user", "content": str(m)})

        temp = config.temperature if (config and config.temperature is not None) else kwargs.get("temperature", 0.7)
        max_tok = config.max_tokens if (config and config.max_tokens is not None) else kwargs.get("max_tokens", 4096)
        mod = (config.model if config and config.model else None) or kwargs.get("model") or self._model
        return self._prepare_payload(raw_msgs, model=mod, temperature=temp, stream=stream, max_tokens=max_tok, **kwargs)

    def get_endpoint_url(self, path: str = "/chat/completions") -> str:
        """
        Constructs full URL for an API endpoint path.

        Args:
            path (str): Endpoint path relative to base_url.

        Returns:
            str: Full URL.
        """
        clean_path = path if path.startswith("/") else f"/{path}"
        if self._is_anthropic_direct() and clean_path in ("/chat/completions", "chat/completions"):
            clean_path = "/messages"
        return f"{self._base_url}{clean_path}"

    def get_headers(self) -> Dict[str, str]:
        """
        Constructs HTTP request headers including Authorization or x-api-key if API key is provided.

        Returns:
            Dict[str, str]: HTTP headers.
        """
        headers = {"Content-Type": "application/json; charset=utf-8"}
        effective_key = self._api_key
        can_p = self.canonicalize_provider(self._provider)

        if not effective_key:
            if can_p == "openai":
                effective_key = os.getenv("OPENAI_API_KEY")
            elif can_p == "claude":
                effective_key = os.getenv("ANTHROPIC_API_KEY")
            elif can_p == "nvidia_spark":
                effective_key = os.getenv("NVIDIA_API_KEY")
            elif can_p == "gemini":
                effective_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            elif can_p == "cloud":
                effective_key = os.getenv("OPENAI_API_KEY")

        if effective_key:
            clean_key = effective_key.strip().replace("\r", "").replace("\n", "")
            if self._is_anthropic_direct():
                headers["x-api-key"] = clean_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {clean_key}"
        return headers

    async def _execute_chat_request(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        target_model: str,
        provider_name: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Ejecuta una petición HTTP individual no-streaming con diagnóstico completo de errores."""
        client_timeout = aiohttp.ClientTimeout(total=self._timeout)
        start_time = time.monotonic()
        logger.info(f"Petición no-streaming iniciada -> {provider_name} ({target_model}) en {url}")
        max_retries = kwargs.get(
            "max_retries",
            2 if self.canonicalize_provider(self._provider) in ("gemini", "cloud", "openai", "claude") else 0
        )

        try:
            for attempt in range(max_retries + 1):
                async with aiohttp.ClientSession(timeout=client_timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        latency = round((time.monotonic() - start_time) * 1000, 1)
                        if response.status == 200:
                            body_text = await response.text(encoding="utf-8")
                            data = json.loads(body_text)
                            # Normalize Anthropic response format to OpenAI-standard choices structure
                            if self._is_anthropic_direct() and "content" in data and isinstance(data["content"], list):
                                text_parts = [b.get("text", "") for b in data["content"] if b.get("type") == "text"]
                                full_text = "".join(text_parts)
                                normalized_data = {
                                    "id": data.get("id", ""),
                                    "choices": [
                                        {
                                            "index": 0,
                                            "message": {
                                                "role": "assistant",
                                                "content": full_text,
                                            },
                                            "finish_reason": data.get("stop_reason", "stop"),
                                        }
                                    ],
                                    "usage": data.get("usage", {}),
                                }
                                logger.info(f"Petición exitosa Claude (HTTP 200 - {latency} ms)")
                                return {"success": True, "data": normalized_data}
                            logger.info(f"Petición exitosa {provider_name} (HTTP 200 - {latency} ms)")
                            return {"success": True, "data": data}
                        elif response.status in (429, 502, 503, 504) and attempt < max_retries:
                            wait_sec = 1.0 * (attempt + 1)
                            logger.info(
                                f"Fallo temporal HTTP {response.status} en {provider_name}. "
                                f"Reintentando en {wait_sec}s (intento {attempt + 1}/{max_retries})..."
                            )
                            await asyncio.sleep(wait_sec)
                            continue
                        else:
                            try:
                                error_raw = await response.text(encoding="utf-8")
                                error_text = error_raw if isinstance(error_raw, str) else ""
                            except Exception:
                                error_text = ""
                            logger.warning(
                                f"Fallo HTTP {response.status} en {provider_name}: {error_text[:200]}"
                            )
                            diag = diagnose_inference_failure(
                                provider=self._provider,
                                model=target_model,
                                base_url=self._base_url,
                                status_code=response.status,
                                error_type="HTTPError",
                                raw_error=error_text,
                                timeout=self._timeout,
                            )
                            return {
                                "success": False,
                                "error_type": "HTTPError",
                                "status": response.status,
                                "message": f"Error del servidor ({response.status}): {error_text}",
                                "diagnostic": diag,
                                "diagnostic_md": diag.to_markdown(),
                            }

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Conexión rehusada con {provider_name} en {url}: {e}")
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type="ConnectionError",
                raw_error=str(e),
                timeout=self._timeout,
            )
            return {
                "success": False,
                "error_type": "ConnectionError",
                "message": f"Conexión rehusada al servidor ({provider_name} en {url}): {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({self._timeout}s) agotado contactando {provider_name}")
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type="TimeoutError",
                timeout=self._timeout,
            )
            return {
                "success": False,
                "error_type": "TimeoutError",
                "message": f"Tiempo de espera agotado ({self._timeout}s) contactando {provider_name}.",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except Exception as e:
            logger.error(f"Excepción en petición a {provider_name}: {e}", exc_info=e)
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type=type(e).__name__,
                raw_error=str(e),
                timeout=self._timeout,
            )
            return {
                "success": False,
                "error_type": "Exception",
                "message": f"Excepción en petición a {provider_name}: {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }

    async def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes a non-streaming asynchronous chat completion request.
        Supports multi-node cluster failover if configured.
        """
        target_model = model or self._model

        # Modo Cluster Multi-Nodo con Conmutación por Error
        if self._provider == "cluster" and self._cluster_manager:
            eligible_nodes = [n for n in self._cluster_manager.get_nodes() if n.is_active]
            max_attempts = max(1, len(eligible_nodes))
            last_err = None
            for _ in range(max_attempts):
                node = self._cluster_manager.select_node()
                if not node:
                    break
                node_url = node.url.rstrip("/")
                endpoint = f"{node_url}/chat/completions"
                node_headers = self.get_headers()
                if node.api_key:
                    node_headers["Authorization"] = f"Bearer {node.api_key}"
                node_model = node.model or target_model
                node_payload = self._prepare_payload(
                    messages=messages,
                    model=node_model,
                    temperature=temperature,
                    stream=False,
                    **kwargs,
                )
                res = await self._execute_chat_request(
                    url=endpoint,
                    payload=node_payload,
                    headers=node_headers,
                    target_model=node_model,
                    provider_name=f"Cluster Node: {node.name}",
                )
                if res.get("success"):
                    return res
                else:
                    self._cluster_manager.mark_node_failure(node.name)
                    last_err = res
                    logger.warning(f"Nodo de cluster '{node.name}' falló. Conmutando al siguiente nodo...")
            if last_err:
                return last_err

        url = self.get_endpoint_url("/chat/completions")
        headers = self.get_headers()
        payload = self._prepare_payload(
            messages=messages,
            model=target_model,
            temperature=temperature,
            stream=False,
            **kwargs,
        )
        return await self._execute_chat_request(
            url=url,
            payload=payload,
            headers=headers,
            target_model=target_model,
            provider_name=self._provider,
            **kwargs,
        )

    async def _execute_stream_request(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        target_model: str,
        provider_name: str,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecuta una petición SSE streaming individual y procesa fragmentos y tokens de razonamiento."""
        client_timeout = aiohttp.ClientTimeout(total=self._timeout)
        start_time = time.monotonic()
        logger.info(f"Iniciando SSE stream -> {provider_name} ({target_model}) en {url}")
        max_stream_retries = kwargs.get(
            "max_retries",
            2 if self.canonicalize_provider(self._provider) in ("gemini", "cloud", "openai", "claude") else 0
        )

        try:
            for attempt in range(max_stream_retries + 1):
                async with aiohttp.ClientSession(timeout=client_timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        if response.status != 200:
                            if response.status in (429, 502, 503, 504) and attempt < max_stream_retries:
                                wait_sec = 1.0 * (attempt + 1)
                                logger.info(
                                    f"Streaming temporalmente no disponible (HTTP {response.status}). "
                                    f"Reintentando en {wait_sec}s ({attempt + 1}/{max_stream_retries})..."
                                )
                                await asyncio.sleep(wait_sec)
                                continue

                            try:
                                error_raw = await response.text(encoding="utf-8")
                                error_text = error_raw if isinstance(error_raw, str) else ""
                            except Exception:
                                error_text = ""
                            logger.warning(
                                f"Fallo HTTP {response.status} en streaming con {provider_name}: {error_text[:200]}"
                            )
                            diag = diagnose_inference_failure(
                                provider=self._provider,
                                model=target_model,
                                base_url=self._base_url,
                                status_code=response.status,
                                error_type="HTTPError",
                                raw_error=error_text,
                                timeout=self._timeout,
                            )
                            yield {
                                "success": False,
                                "error_type": "HTTPError",
                                "status": response.status,
                                "message": f"Error de servidor HTTP {response.status}: {error_text}",
                                "diagnostic": diag,
                                "diagnostic_md": diag.to_markdown(),
                            }
                            return

                        # Read SSE stream line by line
                        token_count = 0
                        reasoning_parser = StreamingReasoningParser()
                        turbo_mode = kwargs.get("turbo_mode", False) or kwargs.get("turbo", False)
                        turbo_buffer = ""
                        last_turbo_yield = time.monotonic()

                        try:
                            async for raw_line in response.content:
                                line = raw_line.decode("utf-8", errors="replace").strip()
                                if not line or line.startswith(":"):
                                    # Skip keep-alive comments and empty lines
                                    continue

                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        data_json = json.loads(data_str)
                                        # Check for Anthropic SSE format
                                        event_type = data_json.get("type")
                                        if event_type == "content_block_delta":
                                            delta_obj = data_json.get("delta", {})
                                            delta_type = delta_obj.get("type")
                                            if delta_type == "text_delta":
                                                chunk_text = delta_obj.get("text", "")
                                                parts = reasoning_parser.process_chunk(chunk_text)
                                                for part in parts:
                                                    if part["type"] == "reasoning":
                                                        token_count += 1
                                                        yield {
                                                            "success": True,
                                                            "data": {
                                                                "choices": [
                                                                    {"delta": {"content": "", "reasoning_content": part["text"]}}
                                                                ]
                                                            },
                                                        }
                                                    else:
                                                        if turbo_mode:
                                                            turbo_buffer += part["text"]
                                                            now = time.monotonic()
                                                            if len(turbo_buffer) >= 16 or (now - last_turbo_yield) >= 0.02:
                                                                token_count += 1
                                                                yield {
                                                                    "success": True,
                                                                    "data": {
                                                                        "choices": [
                                                                            {"delta": {"content": turbo_buffer}}
                                                                        ]
                                                                    },
                                                                }
                                                                turbo_buffer = ""
                                                                last_turbo_yield = now
                                                        else:
                                                            token_count += 1
                                                            yield {
                                                                "success": True,
                                                                "data": {
                                                                    "choices": [
                                                                        {"delta": {"content": part["text"]}}
                                                                    ]
                                                                },
                                                            }
                                            elif delta_type == "thinking_delta":
                                                chunk_text = delta_obj.get("thinking", "")
                                                token_count += 1
                                                yield {
                                                    "success": True,
                                                    "data": {
                                                        "choices": [
                                                            {"delta": {"content": "", "reasoning_content": chunk_text}}
                                                        ]
                                                    },
                                                }
                                        elif event_type == "message_stop":
                                            break
                                        elif event_type == "error":
                                            err_payload = str(data_json.get("error", "Error en stream"))
                                            diag = diagnose_inference_failure(
                                                provider=self._provider,
                                                model=target_model,
                                                base_url=self._base_url,
                                                error_type="ClaudeError",
                                                raw_error=err_payload,
                                            )
                                            yield {
                                                "success": False,
                                                "error_type": "ClaudeError",
                                                "message": err_payload,
                                                "diagnostic": diag,
                                                "diagnostic_md": diag.to_markdown(),
                                            }
                                            break
                                        else:
                                            if "choices" in data_json:
                                                choices = data_json.get("choices", [])
                                                if choices and isinstance(choices[0], dict):
                                                    delta = choices[0].get("delta", {})
                                                    if isinstance(delta, dict):
                                                        exp_reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thought")
                                                        raw_content = delta.get("content")

                                                        if exp_reasoning:
                                                            token_count += 1
                                                            yield {
                                                                "success": True,
                                                                "data": {
                                                                    "choices": [
                                                                        {"delta": {"content": "", "reasoning_content": exp_reasoning}}
                                                                    ]
                                                                },
                                                            }

                                                        if raw_content:
                                                            parts = reasoning_parser.process_chunk(raw_content)
                                                            for part in parts:
                                                                if part["type"] == "reasoning":
                                                                    token_count += 1
                                                                    yield {
                                                                        "success": True,
                                                                        "data": {
                                                                            "choices": [
                                                                                {"delta": {"content": "", "reasoning_content": part["text"]}}
                                                                            ]
                                                                        },
                                                                    }
                                                                else:
                                                                    if turbo_mode:
                                                                        turbo_buffer += part["text"]
                                                                        now = time.monotonic()
                                                                        if len(turbo_buffer) >= 16 or (now - last_turbo_yield) >= 0.02:
                                                                            token_count += 1
                                                                            yield {
                                                                                "success": True,
                                                                                "data": {
                                                                                    "choices": [
                                                                                        {"delta": {"content": turbo_buffer}}
                                                                                    ]
                                                                                },
                                                                            }
                                                                            turbo_buffer = ""
                                                                            last_turbo_yield = now
                                                                    else:
                                                                        token_count += 1
                                                                        yield {
                                                                            "success": True,
                                                                            "data": {
                                                                                "choices": [
                                                                                    {"delta": {"content": part["text"]}}
                                                                                ]
                                                                            },
                                                                        }
                                                        elif not exp_reasoning:
                                                            token_count += 1
                                                            yield {"success": True, "data": data_json}
                                    except json.JSONDecodeError:
                                        continue
                        except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, asyncio.IncompleteReadError) as stream_err:
                            if token_count > 0:
                                logger.info(
                                    f"Conexión SSE cerrada por el servidor remoto tras emitir {token_count} chunks ({stream_err}). Finalizando recepción limpiamente."
                                )
                            elif attempt < max_stream_retries:
                                wait_sec = 1.0 * (attempt + 1)
                                logger.info(
                                    f"Conexión perdida antes de recibir datos ({stream_err}). Reintentando en {wait_sec}s ({attempt + 1}/{max_stream_retries})..."
                                )
                                await asyncio.sleep(wait_sec)
                                continue
                            else:
                                raise

                        # Flush remaining buffers
                        for part in reasoning_parser.flush():
                            if part["type"] == "reasoning":
                                token_count += 1
                                yield {
                                    "success": True,
                                    "data": {
                                        "choices": [
                                            {"delta": {"content": "", "reasoning_content": part["text"]}}
                                        ]
                                    },
                                }
                            else:
                                turbo_buffer += part["text"]

                        if turbo_buffer:
                            token_count += 1
                            yield {
                                "success": True,
                                "data": {
                                    "choices": [
                                        {"delta": {"content": turbo_buffer}}
                                    ]
                                },
                            }
                            turbo_buffer = ""

                        elapsed = round(time.monotonic() - start_time, 2)
                        logger.debug(f"SSE stream finalizado con {self._provider} ({token_count} chunks en {elapsed}s)")
                        return

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Conexión rehusada durante streaming con {self._provider} en {self._base_url}: {e}")
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type="ConnectionError",
                raw_error=str(e),
                timeout=self._timeout,
            )
            yield {
                "success": False,
                "error_type": "ConnectionError",
                "message": f"Conexión rehusada al servidor ({self._provider} en {self._base_url}): {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({self._timeout}s) durante streaming con {self._provider}")
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type="TimeoutError",
                timeout=self._timeout,
            )
            yield {
                "success": False,
                "error_type": "TimeoutError",
                "message": f"Tiempo de espera agotado ({self._timeout}s) en streaming con {self._provider}.",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except Exception as e:
            logger.error(f"Excepción en streaming con {self._provider}: {e}", exc_info=e)
            diag = diagnose_inference_failure(
                provider=self._provider,
                model=target_model,
                base_url=self._base_url,
                error_type=type(e).__name__,
                raw_error=str(e),
                timeout=self._timeout,
            )
            yield {
                "success": False,
                "error_type": "Exception",
                "message": f"Excepción durante el streaming con {provider_name}: {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }

    async def stream_chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously streams chat completion responses chunk-by-chunk using Server-Sent Events (SSE).
        Supports reasoning/thinking token separation (Plan 01), Turbo Mode micro-batching, and cluster failover.

        Args:
            messages (List[Dict[str, str]]): Conversation history messages.
            model (Optional[str]): Override model name for this request.
            temperature (float): Sampling temperature.
            **kwargs: Additional payload arguments.

        Yields:
            Dict[str, Any]: Structured dicts containing chunk data or error status with diagnostics.
        """
        target_model = model or self._model

        # Modo Cluster Multi-Nodo con Conmutación por Error
        if self._provider == "cluster" and self._cluster_manager:
            eligible_nodes = [n for n in self._cluster_manager.get_nodes() if n.is_active]
            max_attempts = max(1, len(eligible_nodes))
            last_err_chunk = None
            for _ in range(max_attempts):
                node = self._cluster_manager.select_node()
                if not node:
                    break
                node_url = node.url.rstrip("/")
                endpoint = f"{node_url}/chat/completions"
                node_headers = self.get_headers()
                node_headers["Accept"] = "text/event-stream"
                if node.api_key:
                    node_headers["Authorization"] = f"Bearer {node.api_key}"
                node_model = node.model or target_model
                node_payload = self._prepare_payload(
                    messages=messages,
                    model=node_model,
                    temperature=temperature,
                    stream=True,
                    **kwargs,
                )
                yielded_any = False
                failed_early = False
                async for chunk_obj in self._execute_stream_request(
                    url=endpoint,
                    payload=node_payload,
                    headers=node_headers,
                    target_model=node_model,
                    provider_name=f"Cluster Node: {node.name}",
                    **kwargs,
                ):
                    if not chunk_obj.get("success") and not yielded_any:
                        failed_early = True
                        last_err_chunk = chunk_obj
                        self._cluster_manager.mark_node_failure(node.name)
                        logger.warning(
                            f"Nodo de cluster '{node.name}' falló antes de emitir tokens. Conmutando al siguiente nodo..."
                        )
                        break
                    yielded_any = True
                    yield chunk_obj

                if yielded_any and not failed_early:
                    return

            if last_err_chunk:
                yield last_err_chunk
                return

        # Modo Proveedor Individual Estándar
        url = self.get_endpoint_url("/chat/completions")
        headers = self.get_headers()
        headers["Accept"] = "text/event-stream"
        payload = self._prepare_payload(
            messages=messages,
            model=target_model,
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        async for chunk_obj in self._execute_stream_request(
            url=url,
            payload=payload,
            headers=headers,
            target_model=target_model,
            provider_name=self._provider,
            **kwargs,
        ):
            yield chunk_obj

