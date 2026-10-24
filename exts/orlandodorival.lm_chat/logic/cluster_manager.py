# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo de Gestión de Clusters de Inferencia Multi-Nodo (ClusterManager).

Permite orquestar múltiples instancias de inferencia (LM Studio, Ollama, vLLM, NIM)
distribuidas en una red local (LAN) o clúster de cómputo (DGX, servidores secundarios).
Proporciona balanceo por prioridad (conmutación por error instantánea), round-robin y
menor latencia con sondeo de salud asíncrono y transparente.
"""

from __future__ import annotations

import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import aiohttp

from core.interfaces import IClusterManager, ClusterNode, ClusterFailoverStrategy
from logic.logger import get_logger

logger = get_logger("ClusterManager")


class ClusterManager(IClusterManager):
    """Gestor de nodos de inferencia distribuidos con tolerancia a fallos."""

    def __init__(
        self,
        nodes: Optional[List[ClusterNode]] = None,
        strategy: ClusterFailoverStrategy = ClusterFailoverStrategy.PRIORITY,
        health_check_timeout: float = 3.0,
    ) -> None:
        """
        Inicializa el ClusterManager.

        Args:
            nodes (Optional[List[ClusterNode]]): Lista inicial de nodos de cómputo.
            strategy (ClusterFailoverStrategy): Estrategia de enrutamiento y balanceo.
            health_check_timeout (float): Tiempo máximo de espera para sondear salud de un nodo.
        """
        self._nodes: List[ClusterNode] = list(nodes) if nodes else []
        self._strategy: ClusterFailoverStrategy = strategy
        self._health_check_timeout = health_check_timeout
        self._rr_index: int = 0
        self._failure_timestamps: Dict[str, float] = {}
        self._failure_cooldown_seconds: float = 30.0

    @property
    def strategy(self) -> ClusterFailoverStrategy:
        """Estrategia de selección activa."""
        return self._strategy

    def set_strategy(self, strategy: ClusterFailoverStrategy) -> None:
        """Establece la estrategia de enrutamiento."""
        self._strategy = strategy
        logger.info(f"Estrategia de clúster actualizada a: {strategy.value}")

    def get_nodes(self) -> List[ClusterNode]:
        """Retorna la lista de todos los nodos configurados."""
        return list(self._nodes)

    def get_node(self, name: str) -> Optional[ClusterNode]:
        """Obtiene un nodo por su nombre."""
        for n in self._nodes:
            if n.name == name:
                return n
        return None

    def add_node(self, node: ClusterNode) -> None:
        """Registra o actualiza un nodo en el cluster."""
        for i, existing in enumerate(self._nodes):
            if existing.name == node.name:
                self._nodes[i] = node
                logger.info(f"Nodo de clúster '{node.name}' actualizado: {node.url}")
                return
        self._nodes.append(node)
        logger.info(f"Nodo de clúster '{node.name}' agregado: {node.url}")

    def remove_node(self, name: str) -> bool:
        """Elimina un nodo del cluster."""
        for i, node in enumerate(self._nodes):
            if node.name == name:
                self._nodes.pop(i)
                self._failure_timestamps.pop(name, None)
                logger.info(f"Nodo de clúster '{name}' eliminado")
                return True
        return False

    def mark_node_failure(self, name: str) -> None:
        """Registra un fallo en un nodo y activa su periodo de enfriamiento."""
        node = self.get_node(name)
        if node:
            node.is_healthy = False
            self._failure_timestamps[name] = time.time()
            logger.warning(
                f"Nodo de clúster '{name}' marcado como NO SALUDABLE (cooldown {self._failure_cooldown_seconds}s)"
            )

    def _is_node_eligible(self, node: ClusterNode) -> bool:
        """Evalúa si un nodo está activo y apto para recibir peticiones."""
        if not node.is_active:
            return False
        if not node.is_healthy:
            # Comprobar si el periodo de enfriamiento ya expiró para permitir reintento
            fail_time = self._failure_timestamps.get(node.name, 0.0)
            if time.time() - fail_time > self._failure_cooldown_seconds:
                node.is_healthy = True
                self._failure_timestamps.pop(node.name, None)
                logger.info(f"Nodo '{node.name}' reincorporado tras expirar periodo de enfriamiento")
                return True
            return False
        return True

    def select_node(self) -> Optional[ClusterNode]:
        """
        Selecciona el nodo óptimo según la estrategia configurada.

        Returns:
            Optional[ClusterNode]: Nodo seleccionado o None si no hay nodos aptos.
        """
        eligible_nodes = [n for n in self._nodes if self._is_node_eligible(n)]
        if not eligible_nodes:
            logger.warning("No hay nodos elegibles ni saludables disponibles en el clúster")
            return None

        if self._strategy == ClusterFailoverStrategy.PRIORITY:
            # Seleccionar el primer nodo elegible en orden de prioridad
            return eligible_nodes[0]

        elif self._strategy == ClusterFailoverStrategy.LOWEST_LATENCY:
            # Seleccionar el nodo con menor latencia registrada
            sorted_nodes = sorted(eligible_nodes, key=lambda n: n.last_latency_ms if n.last_latency_ms > 0 else 999999.0)
            return sorted_nodes[0]

        elif self._strategy == ClusterFailoverStrategy.ROUND_ROBIN:
            # Seleccionar el siguiente nodo en orden rotativo
            node = eligible_nodes[self._rr_index % len(eligible_nodes)]
            self._rr_index = (self._rr_index + 1) % len(eligible_nodes)
            return node

        return eligible_nodes[0]

    async def check_health_node(self, node: ClusterNode) -> bool:
        """
        Sondea asíncronamente el estado de salud y latencia de un nodo.

        Args:
            node (ClusterNode): Nodo a sondear.

        Returns:
            bool: True si el nodo responde correctamente.
        """
        raw_url = (node.url or "").strip().replace("\r", "").replace("\n", "")
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            node.is_healthy = False
            self._failure_timestamps[node.name] = time.time()
            node.last_checked_at = datetime.now(timezone.utc).isoformat()
            logger.warning(
                f"Nodo de clúster '{node.name}' rechazado: Esquema de URL no permitido en '{node.url}'. "
                "Solo se permiten esquemas http:// y https://."
            )
            return False

        clean_url = raw_url.rstrip("/")
        # Detectar endpoint adecuado para sondeo (/models o /health)
        ping_url = f"{clean_url}/models" if not clean_url.endswith("/models") else clean_url

        headers = {}
        if node.api_key:
            headers["Authorization"] = f"Bearer {node.api_key}"

        start_time = time.perf_counter()
        try:
            timeout_cfg = aiohttp.ClientTimeout(total=self._health_check_timeout)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.get(ping_url, headers=headers) as resp:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    node.last_latency_ms = round(elapsed_ms, 2)
                    node.last_checked_at = datetime.now(timezone.utc).isoformat()

                    if resp.status in (200, 204):
                        node.is_healthy = True
                        self._failure_timestamps.pop(node.name, None)
                        logger.debug(f"Nodo '{node.name}' saludable: {node.last_latency_ms}ms")
                        return True
                    else:
                        node.is_healthy = False
                        self._failure_timestamps[node.name] = time.time()
                        logger.warning(f"Nodo '{node.name}' respondió status={resp.status}")
                        return False
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            node.last_latency_ms = round(elapsed_ms, 2)
            node.last_checked_at = datetime.now(timezone.utc).isoformat()
            node.is_healthy = False
            self._failure_timestamps[node.name] = time.time()
            logger.warning(f"Fallo al contactar nodo '{node.name}' ({ping_url}): {e}")
            return False

    async def check_health_all(self) -> Dict[str, bool]:
        """
        Verifica la salud de todos los nodos concurrentemente.

        Returns:
            Dict[str, bool]: Mapa de nombre de nodo a estado de salud.
        """
        tasks = [self.check_health_node(node) for node in self._nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_map: Dict[str, bool] = {}
        for node, res in zip(self._nodes, results):
            health_map[node.name] = bool(res) if isinstance(res, bool) else False

        logger.info(f"Sondeo de clúster completado: {health_map}")
        return health_map

    def to_dict(self) -> Dict[str, Any]:
        """Serializa la configuración del clúster."""
        return {
            "strategy": self._strategy.value,
            "nodes": [n.to_dict() for n in self._nodes],
            "health_check_timeout": self._health_check_timeout,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClusterManager":
        """Reconstruye un ClusterManager a partir de un diccionario."""
        raw_nodes = data.get("nodes", [])
        nodes = [ClusterNode.from_dict(d) for d in raw_nodes if isinstance(d, dict)]
        raw_strat = data.get("strategy", ClusterFailoverStrategy.PRIORITY.value)
        try:
            strat = ClusterFailoverStrategy(raw_strat)
        except ValueError:
            strat = ClusterFailoverStrategy.PRIORITY

        timeout = float(data.get("health_check_timeout", 3.0))
        return cls(nodes=nodes, strategy=strat, health_check_timeout=timeout)
