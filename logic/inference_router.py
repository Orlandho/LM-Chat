# -*- coding: utf-8 -*-

"""
Inference Router Module for Multi-Provider LLM Integration.

This module implements the InferenceRouter class, which acts as an asynchronous,
decoupled gateway for directing chat completion requests across multiple LLM providers:
LM Studio, Ollama, vLLM (Enterprise/Nemotron), and Cloud APIs (OpenAI, Anthropic, Gemini).
"""

import asyncio
import json
from typing import AsyncGenerator, Dict, List, Optional, Any
import aiohttp


class InferenceRouter:
    """
    Asynchronous Multi-Provider Router for LLM Inference.

    Supports LM Studio, Ollama, vLLM, and OpenAPI-compatible Cloud endpoints.
    Ensures non-blocking streaming requests for Omniverse (60 FPS rendering thread).
    """

    DEFAULT_ENDPOINTS: Dict[str, str] = {
        "lm_studio": "http://localhost:1234/v1",
        "ollama": "http://localhost:11434/v1",
        "vllm": "http://localhost:8000/v1",
        "cloud": "https://api.openai.com/v1",
    }

    DEFAULT_MODELS: Dict[str, str] = {
        "lm_studio": "local-model",
        "ollama": "llama3",
        "vllm": "nvidia/nemotron-4-70b-instruct",
        "cloud": "gpt-4o",
    }

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
            provider (str): Provider identifier ('lm_studio', 'ollama', 'vllm', 'cloud').
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
            provider (str): Provider key ('lm_studio', 'ollama', 'vllm', 'cloud').
            base_url (Optional[str]): Custom base URL or default for provider.
            model (Optional[str]): Model identifier.
            api_key (Optional[str]): API Key for cloud services.
        """
        provider_clean = provider.lower().strip()
        self._provider = provider_clean

        # Resolve and validate base URL
        if base_url:
            cleaned_url = base_url.strip().replace("\r", "").replace("\n", "").rstrip("/")
            if not (cleaned_url.startswith("http://") or cleaned_url.startswith("https://")):
                raise ValueError(f"Invalid base_url scheme: '{base_url}'. Must start with http:// or https://")
            self._base_url = cleaned_url
        else:
            self._base_url = self.DEFAULT_ENDPOINTS.get(
                provider_clean, "http://localhost:1234/v1"
            )

        # Resolve default model
        if model:
            self._model = model
        else:
            self._model = self.DEFAULT_MODELS.get(provider_clean, "local-model")

        # Sanitize API key to prevent CRLF HTTP header injection
        if api_key:
            self._api_key = api_key.strip().replace("\r", "").replace("\n", "")
        else:
            self._api_key = None

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

    def get_endpoint_url(self, path: str = "/chat/completions") -> str:
        """
        Constructs full URL for an API endpoint path.

        Args:
            path (str): Endpoint path relative to base_url.

        Returns:
            str: Full URL.
        """
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{self._base_url}{clean_path}"

    def get_headers(self) -> Dict[str, str]:
        """
        Constructs HTTP request headers including Authorization if API key is provided.

        Returns:
            Dict[str, str]: HTTP headers.
        """
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
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
        url = self.get_endpoint_url("/chat/completions")
        headers = self.get_headers()
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            **kwargs,
        }

        client_timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        body_text = await response.text(encoding="utf-8")
                        data = json.loads(body_text)
                        return {"success": True, "data": data}
                    else:
                        error_text = await response.text(encoding="utf-8")
                        return {
                            "success": False,
                            "error_type": "HTTPError",
                            "status": response.status,
                            "message": f"Error del servidor ({response.status}): {error_text}",
                        }

        except aiohttp.ClientConnectorError as e:
            return {
                "success": False,
                "error_type": "ConnectionError",
                "message": f"Conexión rehusada al servidor ({self._provider} en {self._base_url}): {str(e)}",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error_type": "TimeoutError",
                "message": f"Tiempo de espera agotado ({self._timeout}s) contactando {self._provider}.",
            }
        except Exception as e:
            return {
                "success": False,
                "error_type": "Exception",
                "message": f"Excepción en petición a {self._provider}: {str(e)}",
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
            Dict[str, Any]: Structured dicts containing chunk data or error status.
        """
        url = self.get_endpoint_url("/chat/completions")
        headers = self.get_headers()
        headers["Accept"] = "text/event-stream"
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }

        client_timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text(encoding="utf-8")
                        yield {
                            "success": False,
                            "error_type": "HTTPError",
                            "status": response.status,
                            "message": f"Error de servidor HTTP {response.status}: {error_text}",
                        }
                        return

                    # Read SSE stream line by line
                    async for raw_line in response.content:
                        line = raw_line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                yield {"success": True, "data": data_json}
                            except json.JSONDecodeError:
                                continue

        except aiohttp.ClientConnectorError as e:
            yield {
                "success": False,
                "error_type": "ConnectionError",
                "message": f"Conexión rehusada al servidor ({self._provider} en {self._base_url}): {str(e)}",
            }
        except asyncio.TimeoutError:
            yield {
                "success": False,
                "error_type": "TimeoutError",
                "message": f"Tiempo de espera agotado ({self._timeout}s) en streaming con {self._provider}.",
            }
        except Exception as e:
            yield {
                "success": False,
                "error_type": "Exception",
                "message": f"Excepción durante el streaming con {self._provider}: {str(e)}",
            }
