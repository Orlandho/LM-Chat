# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Gestión de Configuración Persistente (SettingsManager) para LM-Chat™.

Implementa ISettingsManager para centralizar y persistir las preferencias del usuario:
proveedor predeterminado, modelo predeterminado, URLs de servidores, credenciales y
parámetros de inferencia (temperatura, timeout, max_tokens) con presets de 1 clic.
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
import aiohttp

from core.interfaces import ISettingsManager, ProviderSettings


class SettingsManager(ISettingsManager):
    """Gestor de configuración persistente con soporte para múltiples proveedores de LLM."""

    DEFAULT_CONFIG_DIR = os.path.expanduser(os.path.join("~", ".omni_lm_chat"))
    DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "settings.json")

    # Mapeo y presets recomendados de proveedores
    DEFAULT_PROVIDERS_CONFIG: Dict[str, Dict[str, Any]] = {
        "LM Studio": {
            "name": "LM Studio",
            "provider_key": "lm_studio",
            "base_url": "http://localhost:1234/v1",
            "default_model": "local-model",
            "available_models": [
                "local-model",
                "qwen2.5-coder-7b",
                "deepseek-r1-distill-qwen-14b",
                "llama-3.2-3b-instruct",
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
            "default_model": "llama3:latest",
            "available_models": [
                "llama3:latest",
                "llama3.3:latest",
                "llama3.1:8b",
                "codellama:7b",
                "mistral:latest",
                "qwen2.5-coder:7b",
                "deepseek-r1:8b",
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
            "default_model": "gpt-4o",
            "available_models": [
                "gpt-4o",
                "gpt-4o-mini",
                "o3-mini",
                "o1",
                "gpt-4-turbo",
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
            "default_model": "claude-3-7-sonnet-latest",
            "available_models": [
                "claude-3-7-sonnet-latest",
                "claude-3-5-sonnet-latest",
                "claude-3-5-haiku-latest",
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
            "default_model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "available_models": [
                "nvidia/llama-3.1-nemotron-70b-instruct",
                "meta/llama-3.1-70b-instruct",
                "meta/llama-3.1-405b-instruct",
                "nvidia/nemotron-4-340b-instruct",
                "mistralai/mixtral-8x22b-instruct-v0.1",
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
            except Exception as e:
                print(f"[SettingsManager] Advertencia: Error leyendo configuración ({e}). Usando valores por defecto.")
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
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._settings_data, f, indent=2, ensure_ascii=False)

            if os.path.exists(self._config_path):
                os.replace(temp_path, self._config_path)
            else:
                os.rename(temp_path, self._config_path)
            return True
        except Exception as e:
            print(f"[SettingsManager] Error guardando archivo de configuración: {e}")
            return False

    def reset_to_defaults(self) -> None:
        """Restablece toda la configuración a los valores de fábrica."""
        self._settings_data = {
            "default_provider": "LM Studio",
            "default_model": "local-model",
            "providers": json.loads(json.dumps(self.DEFAULT_PROVIDERS_CONFIG)),
        }
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
            Dict[str, Any]: Diccionario con estado ('success': bool, 'message': str, 'latency_ms': float).
        """
        can_name = self._canonicalize_provider_name(provider_name)
        cfg = self.get_provider_config(can_name)
        target_url = (base_url or cfg.get("base_url", "")).strip().rstrip("/")
        target_key = api_key if api_key is not None else (self.get_effective_api_key(can_name) or "")

        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            return {
                "success": False,
                "message": f"URL inválida: Debe comenzar con http:// o https:// ({target_url})",
                "latency_ms": 0.0,
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
                        return {
                            "success": True,
                            "message": f"Conexión exitosa ({response.status} OK - {latency} ms)",
                            "latency_ms": latency,
                            "status": response.status,
                        }
                    elif response.status in (401, 403):
                        return {
                            "success": False,
                            "message": f"Error de autenticación ({response.status}): Clave de API inválida o faltante.",
                            "latency_ms": latency,
                            "status": response.status,
                        }
                    elif response.status == 404:
                        # Si /models da 404 (algunos servidores locales solo exponen /chat/completions)
                        # Hacemos fallback rápido probando un ping OPTIONS o un POST vacío
                        return {
                            "success": True,
                            "message": f"Servidor alcanzable ({response.status} - {latency} ms)",
                            "latency_ms": latency,
                            "status": response.status,
                        }
                    else:
                        text = await response.text()
                        short_err = text[:120].strip() if text else f"HTTP {response.status}"
                        return {
                            "success": False,
                            "message": f"Respuesta inesperada ({response.status}): {short_err}",
                            "latency_ms": latency,
                            "status": response.status,
                        }

        except aiohttp.ClientConnectorError as e:
            return {
                "success": False,
                "message": f"Conexión rehusada al servidor ({target_url}). ¿Está el servicio en ejecución?",
                "latency_ms": 0.0,
                "error_type": "ClientConnectorError",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": f"Tiempo de espera agotado ({timeout}s) contactando {target_url}.",
                "latency_ms": 0.0,
                "error_type": "TimeoutError",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error al verificar conexión: {str(e)}",
                "latency_ms": 0.0,
                "error_type": type(e).__name__,
            }
