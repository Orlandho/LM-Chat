# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Gestión de VRAM y Ciclo de Vida de Modelos para LM Studio 0.4.x+.

Permite la carga (JIT load) y descarga (unload) programática de modelos locales
a través de la API REST nativa v1 de LM Studio (/api/v1/models/load y /api/v1/models/unload).
Diseñado específicamente para NVIDIA Omniverse con el fin de liberar memoria GPU (VRAM)
para el renderizador RTX Path Tracing durante la manipulación de escenas complejas.
"""

from __future__ import annotations

import os
import re
import json
import asyncio
from typing import Dict, Any, List, Optional
import aiohttp

from core.interfaces import ILMStudioVRAMManager
from logic.logger import get_logger

logger = get_logger("LMStudioVRAMManager")


class LMStudioVRAMManager(ILMStudioVRAMManager):
    """Gestor de VRAM y ciclo de vida de modelos para LM Studio."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        """
        Inicializa el gestor de VRAM para LM Studio.

        Args:
            base_url (str): URL base del servidor LM Studio (ej. 'http://localhost:1234' o 'http://localhost:1234/v1').
            api_key (Optional[str]): Token de desarrollador de LM Studio si la autenticación está activa.
            timeout (float): Tiempo máximo de espera para operaciones de carga/descarga de modelos.
        """
        clean_url = (base_url or "http://localhost:1234").strip().rstrip("/")
        # Normalizar para remover sufijo /v1 si está presente al construir rutas /api/v1
        if clean_url.endswith("/v1"):
            clean_url = clean_url[:-3]
        self._server_root = clean_url
        self._api_key = api_key
        self._timeout = timeout

    @property
    def server_root(self) -> str:
        """URL raíz del servidor LM Studio."""
        return self._server_root

    def _get_headers(self) -> Dict[str, str]:
        """Construye los encabezados HTTP para la API de LM Studio."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def list_loaded_models(self) -> List[Dict[str, Any]]:
        """
        Consulta los modelos disponibles y cargados en LM Studio.

        Returns:
            List[Dict[str, Any]]: Lista de descriptores de modelos con estado y metadatos.
        """
        url_v1 = f"{self._server_root}/api/v1/models"
        headers = self._get_headers()

        try:
            timeout_cfg = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.get(url_v1, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models") or data.get("data") or []
                        logger.info(f"LM Studio: recuperados {len(models)} modelos de {url_v1}")
                        return list(models)
                    elif resp.status == 404:
                        # Fallback a endpoint estándar OpenAI /v1/models
                        compat_url = f"{self._server_root}/v1/models"
                        async with session.get(compat_url, headers=headers) as resp_compat:
                            if resp_compat.status == 200:
                                data_compat = await resp_compat.json()
                                models = data_compat.get("data", [])
                                logger.info(f"LM Studio: recuperados {len(models)} modelos de fallback {compat_url}")
                                return list(models)
                    
                    text = await resp.text()
                    logger.warning(f"LM Studio list_loaded_models status={resp.status}: {text[:150]}")
                    return []
        except Exception as e:
            logger.error(f"Fallo al listar modelos de LM Studio ({self._server_root}): {e}")
            return []

    async def load_model(
        self,
        model_name: str,
        context_length: Optional[int] = None,
        flash_attention: bool = True,
        offload_kv_cache_to_gpu: bool = True,
        eval_batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Carga programáticamente un modelo en memoria y VRAM vía POST /api/v1/models/load.

        Args:
            model_name (str): Identificador único o ruta del modelo a cargar.
            context_length (Optional[int]): Longitud de contexto máxima en tokens.
            flash_attention (bool): Habilitar aceleración de Flash Attention.
            offload_kv_cache_to_gpu (bool): Descargar caché KV a la memoria de la GPU.
            eval_batch_size (Optional[int]): Tamaño de lote de evaluación.

        Returns:
            Dict[str, Any]: Resultado con 'success', 'model', 'instance_id' y metadatos de carga.
        """
        url = f"{self._server_root}/api/v1/models/load"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": model_name,
            "flash_attention": flash_attention,
            "offload_kv_cache_to_gpu": offload_kv_cache_to_gpu,
            "echo_load_config": True,
        }
        if context_length is not None and context_length > 0:
            payload["context_length"] = context_length
        if eval_batch_size is not None and eval_batch_size > 0:
            payload["eval_batch_size"] = eval_batch_size

        logger.info(f"LM Studio: Cargando modelo '{model_name}' en VRAM...")

        try:
            timeout_cfg = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    resp_json = {}
                    try:
                        resp_json = await resp.json()
                    except Exception:
                        text = await resp.text()
                        resp_json = {"raw_text": text}

                    if resp.status in (200, 201):
                        instance_id = resp_json.get("instance_id") or resp_json.get("id") or model_name
                        logger.info(f"LM Studio: Modelo '{model_name}' cargado con éxito en VRAM (instance_id={instance_id})")
                        return {
                            "success": True,
                            "model": model_name,
                            "instance_id": instance_id,
                            "data": resp_json,
                        }
                    else:
                        err_msg = resp_json.get("error", {}).get("message") if isinstance(resp_json.get("error"), dict) else str(resp_json.get("error") or resp_json)
                        logger.warning(f"LM Studio: Error {resp.status} al cargar modelo '{model_name}': {err_msg}")
                        return {
                            "success": False,
                            "error": f"HTTP {resp.status}: {err_msg}",
                            "status_code": resp.status,
                        }
        except Exception as e:
            logger.error(f"Excepción de conexión al cargar modelo en LM Studio: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def unload_model(self, instance_id: str) -> Dict[str, Any]:
        """
        Descarga un modelo de la memoria y libera VRAM para Omniverse RTX vía POST /api/v1/models/unload.

        Args:
            instance_id (str): Identificador de la instancia o nombre del modelo cargado.

        Returns:
            Dict[str, Any]: Resultado con 'success' y confirmación de liberación de VRAM.
        """
        url = f"{self._server_root}/api/v1/models/unload"
        headers = self._get_headers()

        payload = {"instance_id": instance_id}
        logger.info(f"LM Studio: Descargando modelo/instancia '{instance_id}' para liberar VRAM...")

        try:
            timeout_cfg = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    resp_json = {}
                    try:
                        resp_json = await resp.json()
                    except Exception:
                        text = await resp.text()
                        resp_json = {"raw_text": text}

                    if resp.status in (200, 204):
                        logger.info(f"LM Studio: Modelo '{instance_id}' descargado con éxito. VRAM liberada para RTX Viewport.")
                        return {
                            "success": True,
                            "instance_id": instance_id,
                            "data": resp_json,
                        }
                    else:
                        err_msg = resp_json.get("error", {}).get("message") if isinstance(resp_json.get("error"), dict) else str(resp_json.get("error") or resp_json)
                        logger.warning(f"LM Studio: Error {resp.status} al descargar modelo '{instance_id}': {err_msg}")
                        return {
                            "success": False,
                            "error": f"HTTP {resp.status}: {err_msg}",
                            "status_code": resp.status,
                        }
        except Exception as e:
            logger.error(f"Excepción al descargar modelo de LM Studio: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def unload_all_models(self) -> Dict[str, Any]:
        """
        Descarga todas las instancias activas de modelos en LM Studio para liberar la máxima VRAM posible.

        Returns:
            Dict[str, Any]: Resumen de instancias descargadas y estado de la operación.
        """
        models = await self.list_loaded_models()
        unloaded = []
        errors = []

        for m in models:
            inst_id = m.get("instance_id") or m.get("id") or m.get("name")
            if inst_id:
                res = await self.unload_model(inst_id)
                if res.get("success"):
                    unloaded.append(inst_id)
                else:
                    errors.append({inst_id: res.get("error")})

        logger.info(f"LM Studio: Liberación total de VRAM completada. Descargados: {unloaded}, Fallos: {errors}")
        return {
            "success": len(errors) == 0,
            "unloaded_instances": unloaded,
            "errors": errors,
        }
