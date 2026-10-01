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

import os
import asyncio
import json
import time
from typing import AsyncGenerator, Dict, List, Optional, Any
import aiohttp

from logic.logger import get_logger
from logic.diagnostics import diagnose_inference_failure, ErrorDiagnostic


logger = get_logger("InferenceRouter")


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
        "gemini": "gemini-2.0-flash",
        "google": "gemini-2.0-flash",
        "google gemini": "gemini-2.0-flash",
        "google gemini api": "gemini-2.0-flash",
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
    }

    @classmethod
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
    ) -> None:
        """
        Initializes the InferenceRouter with specified provider configuration.

        Args:
            provider (str): Provider identifier ('lm_studio', 'ollama', 'vllm', 'cloud', 'openai', 'claude', 'gemini').
            base_url (Optional[str]): Custom base URL override.
            api_key (Optional[str]): API key for authentication (optional for local).
            model (Optional[str]): Model name override.
            timeout (float): Request timeout in seconds (default: 600s).
        """
        self._timeout = timeout
        self.set_provider(provider=provider, base_url=base_url, model=model, api_key=api_key)

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

        # Check for OpenAI reasoning models (o1, o3-mini, etc.) which reject 'temperature'
        is_openai_reasoning = any(
            target_model.lower().startswith(prefix) for prefix in ("o1", "o3", "o1-mini", "o3-mini", "o1-preview")
        )
        if not is_openai_reasoning:
            payload["temperature"] = temperature

        # Handle max_tokens vs max_completion_tokens for reasoning models
        for k, v in kwargs.items():
            if is_openai_reasoning and k == "max_tokens":
                payload["max_completion_tokens"] = v
            elif k not in payload:
                payload[k] = v

        return payload

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
                effective_key = os.getenv("GEMINI_API_KEY")
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

    async def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes a non-streaming asynchronous chat completion request.

        Args:
            messages (List[Dict[str, str]]): Conversation history messages.
            model (Optional[str]): Override model name for this request.
            temperature (float): Sampling temperature.
            **kwargs: Additional parameters passed to LLM payload.

        Returns:
            Dict[str, Any]: Structured dictionary with success status and data/error details.
        """
        target_model = model or self._model
        url = self.get_endpoint_url("/chat/completions")
        headers = self.get_headers()
        payload = self._prepare_payload(
            messages=messages,
            model=target_model,
            temperature=temperature,
            stream=False,
            **kwargs,
        )

        client_timeout = aiohttp.ClientTimeout(total=self._timeout)
        start_time = time.monotonic()
        logger.info(f"Petición no-streaming iniciada -> {self._provider} ({target_model}) en {url}")

        try:
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
                        logger.info(f"Petición exitosa {self._provider} (HTTP 200 - {latency} ms)")
                        return {"success": True, "data": data}
                    else:
                        try:
                            error_raw = await response.text(encoding="utf-8")
                            error_text = error_raw if isinstance(error_raw, str) else ""
                        except Exception:
                            error_text = ""
                        logger.warning(
                            f"Fallo HTTP {response.status} en {self._provider}: {error_text[:200]}"
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
            logger.error(f"Conexión rehusada con {self._provider} en {self._base_url}: {e}")
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
                "message": f"Conexión rehusada al servidor ({self._provider} en {self._base_url}): {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({self._timeout}s) agotado contactando {self._provider}")
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
                "message": f"Tiempo de espera agotado ({self._timeout}s) contactando {self._provider}.",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
        except Exception as e:
            logger.error(f"Excepción en petición a {self._provider}: {e}", exc_info=e)
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
                "message": f"Excepción en petición a {self._provider}: {str(e)}",
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

        Args:
            messages (List[Dict[str, str]]): Conversation history messages.
            model (Optional[str]): Override model name for this request.
            temperature (float): Sampling temperature.
            **kwargs: Additional payload arguments.

        Yields:
            Dict[str, Any]: Structured dicts containing chunk data or error status with diagnostics.
        """
        target_model = model or self._model
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

        client_timeout = aiohttp.ClientTimeout(total=self._timeout)
        start_time = time.monotonic()
        logger.info(f"Iniciando SSE stream -> {self._provider} ({target_model}) en {url}")

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        try:
                            error_raw = await response.text(encoding="utf-8")
                            error_text = error_raw if isinstance(error_raw, str) else ""
                        except Exception:
                            error_text = ""
                        logger.warning(
                            f"Fallo HTTP {response.status} en streaming con {self._provider}: {error_text[:200]}"
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
                                        token_count += 1
                                        yield {
                                            "success": True,
                                            "data": {
                                                "choices": [
                                                    {"delta": {"content": chunk_text}}
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
                                            if isinstance(delta, dict) and delta.get("content") is None:
                                                delta["content"] = ""
                                        token_count += 1
                                        yield {"success": True, "data": data_json}
                            except json.JSONDecodeError:
                                continue

                    elapsed = round(time.monotonic() - start_time, 2)
                    logger.debug(f"SSE stream finalizado con {self._provider} ({token_count} chunks en {elapsed}s)")

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
                "message": f"Excepción durante el streaming con {self._provider}: {str(e)}",
                "diagnostic": diag,
                "diagnostic_md": diag.to_markdown(),
            }
