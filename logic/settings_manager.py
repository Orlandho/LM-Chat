# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Gestión de Configuración Persistente (SettingsManager) para LM-Chat™.

Implementa ISettingsManager para centralizar y persistir las preferencias del usuario:
proveedor predeterminado, modelo predeterminado, URLs de servidores, credenciales y
parámetros de inferencia (temperatura, timeout, max_tokens) con presets de 1 clic.

Integra modelos contemporáneos y emergentes (OpenAI GPT-4o / o3-mini / GPT-4.5,
Claude 3.7 Sonnet / 3.5 Haiku, NVIDIA NIM Nemotron-70B, Ollama / LM Studio
con DeepSeek-R1 y Qwen 2.5 Coder, Gemini 2.0 Flash) y diagnósticos avanzados de conectividad.
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
import aiohttp

from core.interfaces import ISettingsManager, ProviderSettings
from logic.logger import get_logger
from logic.diagnostics import diagnose_inference_failure, ErrorDiagnostic


logger = get_logger("SettingsManager")


class SettingsManager(ISettingsManager):
    """Gestor de configuración persistente con soporte para múltiples proveedores de LLM."""

    DEFAULT_CONFIG_DIR = os.path.expanduser(os.path.join("~", ".omni_lm_chat"))
    DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "settings.json")

    # Mapeo y presets recomendados de proveedores contemporáneos y de próxima generación
    DEFAULT_PROVIDERS_CONFIG: Dict[str, Dict[str, Any]] = {
        "LM Studio": {
            "name": "LM Studio",
            "provider_key": "lm_studio",
            "base_url": "http://localhost:1234/v1",
            "default_model": "deepseek-v4",
            "available_models": [
                "deepseek-v4",
                "deepseek-r1-distill-qwen-14b",
                "deepseek-r1-distill-qwen-32b",
                "qwen-3.6",
                "qwen2.5-coder-7b",
                "llama-4-scout",
                "llama-3.3-70b-instruct",
                "local-model",
            ],
            "api_key": "",
            "env_key": None,
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "Local (:1234)", "url": "http://localhost:1234/v1"},
                {"label": "Host LAN (:1234)", "url": "http://192.168.1.100:1234/v1"},
            ],
        },
        "Ollama": {
            "name": "Ollama",
            "provider_key": "ollama",
            "base_url": "http://localhost:11434/v1",
            "default_model": "deepseek-v4",
            "available_models": [
                "deepseek-v4",
                "deepseek-r1:8b",
                "deepseek-r1:14b",
                "deepseek-r1:32b",
                "qwen-3.6",
                "qwen2.5-coder:7b",
                "llama-4-scout",
                "llama-4-maverick",
                "llama3.3:latest",
                "codellama:7b",
                "mistral:latest",
            ],
            "api_key": "",
            "env_key": None,
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "Local (:11434)", "url": "http://localhost:11434/v1"},
                {"label": "Docker (:11434)", "url": "http://host.docker.internal:11434/v1"},
            ],
        },
        "OpenAI API": {
            "name": "OpenAI API",
            "provider_key": "openai",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-6-astra",
            "available_models": [
                "gpt-6-astra",
                "gpt-6.1-sol",
                "gpt-6-luna",
                "gpt-5",
                "o3-mini",
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.5-preview",
            ],
            "api_key": "",
            "env_key": "OPENAI_API_KEY",
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "Oficial OpenAI", "url": "https://api.openai.com/v1"},
            ],
        },
        "Claude API": {
            "name": "Claude API",
            "provider_key": "claude",
            "base_url": "https://api.anthropic.com/v1",
            "default_model": "claude-opus-5-5-latest",
            "available_models": [
                "claude-opus-5-5-latest",
                "claude-fable-5-1",
                "claude-sonnet-5-5",
                "claude-haiku-4-5",
                "claude-3-7-sonnet-latest",
                "claude-3-5-sonnet-latest",
                "claude-3-opus-latest",
            ],
            "api_key": "",
            "env_key": "ANTHROPIC_API_KEY",
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "Oficial Anthropic", "url": "https://api.anthropic.com/v1"},
            ],
        },
        "NVIDIA Spark": {
            "name": "NVIDIA Spark",
            "provider_key": "nvidia_spark",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "nvidia/nemotron-3.5-lightning",
            "available_models": [
                "nvidia/nemotron-3.5-lightning",
                "nvidia/cosmos-3",
                "nvidia/nemotron-3-ultra-550b",
                "nvidia/llama-3.1-nemotron-70b-instruct",
                "deepseek-ai/deepseek-r1",
                "meta/llama-3.1-405b-instruct",
            ],
            "api_key": "",
            "env_key": "NVIDIA_API_KEY",
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "NVIDIA Build Cloud (NIM)", "url": "https://integrate.api.nvidia.com/v1"},
                {"label": "DGX Spark Local NIM (:8000)", "url": "http://localhost:8000/v1"},
            ],
        },
        "Google Gemini API": {
            "name": "Google Gemini API",
            "provider_key": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "default_model": "gemini-3.8-flash",
            "available_models": [
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.1-pro",
                "gemini-3.5-flash-lite",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
            ],
            "api_key": "",
            "env_key": "GEMINI_API_KEY",
            "temperature": 0.7,
            "timeout": 600.0,
            "max_tokens": 4096,
            "presets": [
                {"label": "Google Gemini OpenAI-Compat", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
            ],
        },
    }



    # Alias y compatibilidad con configuraciones previas
    PROVIDER_ALIASES: Dict[str, str] = {
        "lmstudio": "LM Studio",
        "lm_studio": "LM Studio",
        "ollama": "Ollama",
        "openai": "OpenAI API",
        "open_ai": "OpenAI API",
        "openai api": "OpenAI API",
        "claude": "Claude API",
        "anthropic": "Claude API",
        "claude api": "Claude API",
        "nvidia": "NVIDIA Spark",
        "spark": "NVIDIA Spark",
        "nvidia_spark": "NVIDIA Spark",
        "nvidia spark": "NVIDIA Spark",
        "nemotron": "NVIDIA Spark",
        "gemini": "Google Gemini API",
        "google": "Google Gemini API",
        "google gemini": "Google Gemini API",
        "google_gemini": "Google Gemini API",
        "google gemini api": "Google Gemini API",
        "muse": "LM Studio",
        "vllm": "LM Studio",
        "cloud": "OpenAI API",
        "cloud apis": "OpenAI API",
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Inicializa el SettingsManager con una ruta opcional de archivo de configuración.

        Args:
            config_path (Optional[str]): Ruta personalizada del archivo settings.json.
        """
        self._config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._settings_data: Dict[str, Any] = {}
        self.load()

    @property
    def config_path(self) -> str:
        """Ruta física del archivo de persistencia."""
        return self._config_path

    def _canonicalize_provider_name(self, provider_name: str) -> str:
        """Normaliza el nombre del proveedor a su clave canónica en DEFAULT_PROVIDERS_CONFIG."""
        if not provider_name:
            return "LM Studio"
        if provider_name in self.DEFAULT_PROVIDERS_CONFIG:
            return provider_name
        clean = provider_name.strip().lower().replace("_", " ")
        if clean in self.PROVIDER_ALIASES:
            return self.PROVIDER_ALIASES[clean]
        clean_no_space = clean.replace(" ", "")
        if clean_no_space in self.PROVIDER_ALIASES:
            return self.PROVIDER_ALIASES[clean_no_space]
        return "LM Studio"

    def get_all_providers(self) -> List[str]:
        """Retorna la lista ordenada de nombres canónicos de proveedores."""
        return list(self.DEFAULT_PROVIDERS_CONFIG.keys())

    def get_default_provider(self) -> str:
        """Obtiene el nombre legible del proveedor predeterminado."""
        p = self._settings_data.get("default_provider", "LM Studio")
        return self._canonicalize_provider_name(p)

    def set_default_provider(self, provider_name: str) -> None:
        """Establece el proveedor predeterminado y actualiza el modelo si corresponde."""
        can_name = self._canonicalize_provider_name(provider_name)
        self._settings_data["default_provider"] = can_name
        # Sincronizar modelo por defecto
        self._settings_data["default_model"] = self.get_default_model(can_name)
        logger.info(f"Proveedor predeterminado establecido: {can_name} con modelo: {self._settings_data['default_model']}")
        self.save()

    def get_default_model(self, provider_name: str) -> str:
        """Obtiene el modelo predeterminado para el proveedor indicado."""
        can_name = self._canonicalize_provider_name(provider_name)
        p_cfg = self.get_provider_config(can_name)
        return p_cfg.get("default_model", self.DEFAULT_PROVIDERS_CONFIG[can_name]["default_model"])

    def set_default_model(self, provider_name: str, model_name: str) -> None:
        """Establece el modelo predeterminado para el proveedor indicado."""
        can_name = self._canonicalize_provider_name(provider_name)
        if "providers" not in self._settings_data:
            self._settings_data["providers"] = {}
        if can_name not in self._settings_data["providers"]:
            self._settings_data["providers"][can_name] = json.loads(
                json.dumps(self.DEFAULT_PROVIDERS_CONFIG[can_name])
            )
        self._settings_data["providers"][can_name]["default_model"] = model_name
        if self.get_default_provider() == can_name:
            self._settings_data["default_model"] = model_name
        logger.info(f"Modelo predeterminado actualizado para {can_name}: {model_name}")
        self.save()

    def get_available_models(self, provider_name: str) -> List[str]:
        """Retorna la lista de modelos disponibles para un proveedor."""
        can_name = self._canonicalize_provider_name(provider_name)
        p_cfg = self.get_provider_config(can_name)
        models = p_cfg.get("available_models")
        if models and isinstance(models, list):
            return list(models)
        return list(self.DEFAULT_PROVIDERS_CONFIG[can_name]["available_models"])

    def add_custom_model(self, provider_name: str, model_name: str) -> None:
        """Agrega un modelo personalizado a la lista de modelos disponibles de un proveedor."""
        can_name = self._canonicalize_provider_name(provider_name)
        cleaned = model_name.strip()
        if not cleaned:
            return
        p_cfg = self.get_provider_config(can_name)
        models = p_cfg.get("available_models", [])
        if cleaned not in models:
            models.append(cleaned)
            logger.info(f"Modelo personalizado agregado a {can_name}: {cleaned}")
            self.update_provider_config(can_name, available_models=models)

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Obtiene la configuración activa de un proveedor con valores por defecto."""
        can_name = self._canonicalize_provider_name(provider_name)
        default_cfg = self.DEFAULT_PROVIDERS_CONFIG[can_name]
        stored_providers = self._settings_data.get("providers", {})
        stored_cfg = stored_providers.get(can_name, {})

        merged = json.loads(json.dumps(default_cfg))
        merged.update(stored_cfg)
        return merged

    def update_provider_config(self, provider_name: str, **kwargs: Any) -> bool:
        """Actualiza parámetros de configuración para un proveedor."""
        can_name = self._canonicalize_provider_name(provider_name)
        if "providers" not in self._settings_data:
            self._settings_data["providers"] = {}
        if can_name not in self._settings_data["providers"]:
            self._settings_data["providers"][can_name] = json.loads(
                json.dumps(self.DEFAULT_PROVIDERS_CONFIG[can_name])
            )

        for k, v in kwargs.items():
            if v is not None:
                self._settings_data["providers"][can_name][k] = v

        logger.debug(f"Configuración de {can_name} actualizada: {list(kwargs.keys())}")
        return self.save()

    def get_effective_api_key(self, provider_name: str) -> Optional[str]:
        """Obtiene la API key configurada o resuelta desde variables de entorno."""
        can_name = self._canonicalize_provider_name(provider_name)
        cfg = self.get_provider_config(can_name)
        explicit_key = cfg.get("api_key", "").strip()
        if explicit_key:
            return explicit_key

        env_key_var = cfg.get("env_key")
        if env_key_var:
            return os.getenv(env_key_var, "").strip() or None
        return None

    def get_presets(self, provider_name: str) -> List[Dict[str, str]]:
        """Retorna la lista de accesos rápidos de URL para el proveedor."""
        can_name = self._canonicalize_provider_name(provider_name)
        cfg = self.get_provider_config(can_name)
        return cfg.get("presets", [])

    def load(self) -> Dict[str, Any]:
        """Carga la configuración desde el disco o inicializa la estructura por defecto."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._settings_data = json.load(f)
                logger.debug(f"Configuración cargada exitosamente desde {self._config_path}")
            except Exception as e:
                logger.warning(
                    f"Error leyendo configuración ({e}). Usando valores por defecto.",
                    exc_info=e,
                )
                self.reset_to_defaults()
        else:
            self.reset_to_defaults()
        return self._settings_data

    def save(self) -> bool:
        """Persiste la configuración atómicamente a disco."""
        try:
            config_dir = os.path.dirname(self._config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            temp_path = f"{self._config_path}.tmp"
            data_to_save = dict(self._settings_data)
            if "mcp_servers" in data_to_save:
                data_to_save["mcp_servers"] = [
                    s.to_dict() if hasattr(s, "to_dict") else s for s in data_to_save["mcp_servers"]
                ]
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            if os.path.exists(self._config_path):
                os.replace(temp_path, self._config_path)
            else:
                os.rename(temp_path, self._config_path)
            logger.debug(f"Configuración persistida atómicamente en {self._config_path}")
            return True
        except Exception as e:
            logger.error(f"Error guardando archivo de configuración en {self._config_path}: {e}", exc_info=e)
            return False

    def reset_to_defaults(self) -> None:
        """Restablece toda la configuración a los valores de fábrica."""
        self._settings_data = {
            "default_provider": "LM Studio",
            "default_model": "local-model",
            "execution_mode": "immediate",
            "turbo_mode": False,
            "mcp_servers": [],
            "providers": json.loads(json.dumps(self.DEFAULT_PROVIDERS_CONFIG)),
        }
        logger.info("Configuración restablecida a valores por defecto")
        self.save()

    async def test_connection(
        self,
        provider_name: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 6.0,
    ) -> Dict[str, Any]:
        """Verifica la conectividad de forma asíncrona con el proveedor configurado.

        Args:
            provider_name (str): Nombre del proveedor a probar.
            base_url (Optional[str]): URL base a probar (si es None, usa la configurada).
            api_key (Optional[str]): API key a probar (si es None, usa la efectiva).
            timeout (float): Tiempo máximo de espera en segundos.

        Returns:
            Dict[str, Any]: Diccionario con estado ('success': bool, 'message': str, 'latency_ms': float, 'diagnostic': ErrorDiagnostic).
        """
        can_name = self._canonicalize_provider_name(provider_name)
        cfg = self.get_provider_config(can_name)
        target_url = (base_url or cfg.get("base_url", "")).strip().rstrip("/")
        target_key = api_key if api_key is not None else (self.get_effective_api_key(can_name) or "")
        target_model = self.get_default_model(can_name)

        logger.info(f"Iniciando verificación de conexión para proveedor='{can_name}' en URL='{target_url}' (timeout={timeout}s)")

        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            diag = diagnose_inference_failure(
                provider=can_name,
                model=target_model,
                base_url=target_url,
                error_type="ConfigurationError",
                error_message="Invalid URL scheme",
                raw_error=f"La URL debe comenzar con http:// o https:// ({target_url})",
            )
            logger.warning(f"URL inválida para proveedor='{can_name}': {target_url}")
            return {
                "success": False,
                "message": f"URL inválida: Debe comenzar con http:// o https:// ({target_url})",
                "latency_ms": 0.0,
                "diagnostic": diag,
            }

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        # Probar endpoint según naturaleza del proveedor
        if can_name == "Claude API" or "api.anthropic.com" in target_url:
            test_endpoint = f"{target_url}/models"
            if target_key:
                headers["x-api-key"] = target_key
                headers["anthropic-version"] = "2023-06-01"
        else:
            test_endpoint = f"{target_url}/models"
            if target_key:
                headers["Authorization"] = f"Bearer {target_key}"

        start_time = time.monotonic()
        client_timeout = aiohttp.ClientTimeout(total=timeout)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(test_endpoint, headers=headers) as response:
                    latency = round((time.monotonic() - start_time) * 1000, 1)
                    if response.status == 200:
                        logger.info(f"Conexión exitosa con {can_name} en {latency} ms (HTTP 200 OK)")
                        return {
                            "success": True,
                            "message": f"Conexión exitosa ({response.status} OK - {latency} ms)",
                            "latency_ms": latency,
                            "status": response.status,
                        }
                    elif response.status in (401, 403):
                        try:
                            text_raw = await response.text()
                            text = text_raw if isinstance(text_raw, str) else ""
                        except Exception:
                            text = ""
                        logger.warning(f"Fallo de autenticación con {can_name} (HTTP {response.status})")
                        diag = diagnose_inference_failure(
                            provider=can_name,
                            model=target_model,
                            base_url=target_url,
                            status_code=response.status,
                            raw_error=text,
                        )
                        return {
                            "success": False,
                            "message": f"Error de autenticación ({response.status}): Clave de API inválida o faltante.",
                            "latency_ms": latency,
                            "status": response.status,
                            "diagnostic": diag,
                        }
                    elif response.status == 404:
                        # Si /models da 404, en servidores locales indica que el puerto responde
                        is_local = any(k in can_name.lower() for k in ("lm studio", "ollama", "localhost", "127.0.0.1"))
                        if is_local:
                            logger.info(f"Servidor alcanzable con código 404 en /models ({can_name} en {latency} ms)")
                            return {
                                "success": True,
                                "message": f"Servidor alcanzable ({response.status} - {latency} ms)",
                                "latency_ms": latency,
                                "status": response.status,
                            }
                        else:
                            try:
                                text_raw = await response.text()
                                text = text_raw if isinstance(text_raw, str) else ""
                            except Exception:
                                text = ""
                            logger.warning(f"Endpoint no encontrado para {can_name} (HTTP 404 en {test_endpoint})")
                            diag = diagnose_inference_failure(
                                provider=can_name,
                                model=target_model,
                                base_url=target_url,
                                status_code=404,
                                raw_error=f"Endpoint no encontrado (404) en {test_endpoint}: {text}",
                            )
                            return {
                                "success": False,
                                "message": f"Endpoint no encontrado (HTTP 404). Verifica la URL configurada.",
                                "latency_ms": latency,
                                "status": 404,
                                "diagnostic": diag,
                            }
                    else:
                        try:
                            text_raw = await response.text()
                            text = text_raw if isinstance(text_raw, str) else ""
                        except Exception:
                            text = ""
                        short_err = text[:120].strip() if text else f"HTTP {response.status}"
                        logger.warning(f"Respuesta inesperada de {can_name} (HTTP {response.status}): {short_err}")
                        diag = diagnose_inference_failure(
                            provider=can_name,
                            model=target_model,
                            base_url=target_url,
                            status_code=response.status,
                            raw_error=text,
                        )
                        return {
                            "success": False,
                            "message": f"Respuesta inesperada ({response.status}): {short_err}",
                            "latency_ms": latency,
                            "status": response.status,
                            "diagnostic": diag,
                        }

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Conexión rehusada al contactar {can_name} en {target_url}: {e}")
            diag = diagnose_inference_failure(
                provider=can_name,
                model=target_model,
                base_url=target_url,
                error_type="ConnectionError",
                raw_error=str(e),
            )
            return {
                "success": False,
                "message": f"Conexión rehusada al servidor ({target_url}). ¿Está el servicio en ejecución?",
                "latency_ms": 0.0,
                "error_type": "ClientConnectorError",
                "diagnostic": diag,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Tiempo de espera agotado ({timeout}s) contactando {can_name} en {target_url}")
            diag = diagnose_inference_failure(
                provider=can_name,
                model=target_model,
                base_url=target_url,
                error_type="TimeoutError",
                timeout=timeout,
            )
            return {
                "success": False,
                "message": f"Tiempo de espera agotado ({timeout}s) contactando {target_url}.",
                "latency_ms": 0.0,
                "error_type": "TimeoutError",
                "diagnostic": diag,
            }
        except Exception as e:
            logger.error(f"Excepción verificando conexión con {can_name}: {e}", exc_info=e)
            diag = diagnose_inference_failure(
                provider=can_name,
                model=target_model,
                base_url=target_url,
                error_type=type(e).__name__,
                raw_error=str(e),
            )
            return {
                "success": False,
                "message": f"Error al verificar conexión: {str(e)}",
                "latency_ms": 0.0,
                "error_type": type(e).__name__,
                "diagnostic": diag,
            }

    async def fetch_remote_models(self, provider_name: str) -> List[str]:
        """Consulta en tiempo real el endpoint del proveedor (/v1/models o /api/tags) y retorna los modelos vivos disponibles."""
        canonical_name = self._canonicalize_provider_name(provider_name)
        cfg = self.get_provider_config(canonical_name)
        base_url = cfg.get("base_url", "").rstrip("/")
        api_key = self.get_effective_api_key(canonical_name)
        provider_key = cfg.get("provider_key", canonical_name.lower())

        discovered_models: List[str] = []
        timeout = aiohttp.ClientTimeout(total=8.0)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Content-Type": "application/json"}
                if api_key:
                    clean_key = api_key.strip().replace("\r", "").replace("\n", "")
                    if provider_key == "claude" or "anthropic" in base_url:
                        headers["x-api-key"] = clean_key
                        headers["anthropic-version"] = "2023-06-01"
                    else:
                        headers["Authorization"] = f"Bearer {clean_key}"

                # Try endpoint according to provider
                if provider_key == "ollama" or "11434" in base_url:
                    try:
                        clean_root = base_url[:-3] if base_url.endswith("/v1") else base_url
                        async with session.get(f"{clean_root}/api/tags") as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                for m in data.get("models", []):
                                    name = m.get("name") or m.get("model")
                                    if name and name not in discovered_models:
                                        discovered_models.append(name)
                    except Exception:
                        pass

                # Standard /models endpoint (OpenAI, LM Studio, NVIDIA, vLLM, Gemini, or Ollama /v1/models)
                if not discovered_models:
                    url = f"{base_url}/models"
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = data.get("data", []) if isinstance(data, dict) else []
                            if not items and isinstance(data, list):
                                items = data
                            for item in items:
                                if isinstance(item, dict):
                                    mid = item.get("id") or item.get("name")
                                    if mid and mid not in discovered_models:
                                        discovered_models.append(mid)

        except Exception as e:
            logger.warning(f"Error descubriendo modelos en vivo para {provider_name}: {e}")

        if discovered_models:
            # Merge with existing models preserving new ones at top
            existing = cfg.get("available_models", [])
            merged = discovered_models.copy()
            for m in existing:
                if m not in merged:
                    merged.append(m)
            cfg["available_models"] = merged
            if "providers" in self._settings_data and canonical_name in self._settings_data["providers"]:
                self._settings_data["providers"][canonical_name]["available_models"] = merged
            self.save()
            logger.info(f"Descubiertos {len(discovered_models)} modelos en vivo para {provider_name}")
            return merged


        return cfg.get("available_models", [])

    def get_execution_mode(self) -> str:
        """Obtiene el modo de ejecución activo ('immediate' o 'plan_and_confirm')."""
        return self._settings_data.get("execution_mode", "immediate")

    def set_execution_mode(self, mode: str) -> None:
        """Establece el modo de ejecución activo y lo persiste en disco."""
        clean_mode = "plan_and_confirm" if "plan" in mode.lower() else "immediate"
        self._settings_data["execution_mode"] = clean_mode
        logger.info(f"Modo de ejecución guardado en settings: {clean_mode}")
        self.save()

    def is_turbo_mode(self) -> bool:
        """Indica si el modo turbo con micro-batching está activado."""
        return bool(self._settings_data.get("turbo_mode", False))

    def get_turbo_mode(self) -> bool:
        """Alias para is_turbo_mode()."""
        return self.is_turbo_mode()

    def set_turbo_mode(self, enabled: bool) -> None:
        """Activa o desactiva el modo turbo en la configuración."""
        self._settings_data["turbo_mode"] = bool(enabled)
        logger.info(f"Modo turbo guardado en settings: {enabled}")
        self.save()

    def get_mcp_servers(self) -> List[Any]:
        """Retorna la lista de servidores MCP configurados como MCPServerConfig."""
        from core.interfaces import MCPServerConfig
        raw_list = self._settings_data.get("mcp_servers", [])
        result = []
        for item in raw_list:
            if isinstance(item, MCPServerConfig):
                result.append(item)
            elif isinstance(item, dict):
                result.append(MCPServerConfig(
                    name=item.get("name", ""),
                    command=item.get("command", ""),
                    args=item.get("args", []),
                    env=item.get("env"),
                    enabled=item.get("enabled", True),
                ))
        return result

    def add_mcp_server(
        self,
        name_or_config: Any,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        enabled: bool = True
    ) -> bool:
        """Registra una configuración persistente de servidor MCP. Rechaza nombres duplicados."""
        if hasattr(name_or_config, "name"):
            clean_name = name_or_config.name.strip()
            cmd = name_or_config.command
            arguments = name_or_config.args
            environ = getattr(name_or_config, "env", None) or {}
            is_enabled = getattr(name_or_config, "enabled", True)
        else:
            clean_name = str(name_or_config).strip()
            cmd = command or ""
            arguments = args or []
            environ = env or {}
            is_enabled = enabled

        if not clean_name:
            return False

        if "mcp_servers" not in self._settings_data:
            self._settings_data["mcp_servers"] = []

        servers = self._settings_data["mcp_servers"]
        for s in servers:
            s_name = s.name if hasattr(s, "name") else s.get("name")
            if s_name == clean_name:
                logger.warning(f"Servidor MCP '{clean_name}' ya existe en settings.")
                return False

        servers.append({
            "name": clean_name,
            "command": cmd,
            "args": arguments,
            "env": environ,
            "enabled": is_enabled,
        })
        logger.info(f"Servidor MCP '{clean_name}' agregado a settings.")
        return self.save()

    def remove_mcp_server(self, name: str) -> bool:
        """Elimina la configuración persistente de un servidor MCP."""
        if "mcp_servers" not in self._settings_data:
            return False
        servers = self._settings_data["mcp_servers"]
        initial_len = len(servers)
        self._settings_data["mcp_servers"] = [
            s for s in servers
            if (s.name if hasattr(s, "name") else s.get("name")) != name
        ]
        if len(self._settings_data["mcp_servers"]) < initial_len:
            logger.info(f"Servidor MCP '{name}' eliminado de settings.")
            return self.save()
        return False

    def set_mcp_server_enabled(self, name: str, enabled: bool) -> bool:
        """Habilita o deshabilita un servidor MCP en settings."""
        if "mcp_servers" not in self._settings_data:
            return False
        found = False
        for s in self._settings_data["mcp_servers"]:
            s_name = s.name if hasattr(s, "name") else s.get("name")
            if s_name == name:
                if hasattr(s, "enabled"):
                    s.enabled = enabled
                else:
                    s["enabled"] = enabled
                found = True
        if found:
            return self.save()
        return False


