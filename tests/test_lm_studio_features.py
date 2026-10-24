# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Suite de Pruebas Unitarias para Funcionalidades Avanzadas de LM Studio, MCP Tool Calling y Clusters.

Verifica:
1. Gestión dinámica de VRAM en LM Studio 0.4.x+ (carga, descarga y liberación total de VRAM).
2. Orquestación de Clusters Multi-Nodo con tolerancia a fallos (Priority, Round-Robin, Lowest-Latency).
3. Conmutación por error transparente en InferenceRouter tanto en modo streaming como no-streaming.
4. Ciclo ReAct con MCP Tool Calling e Integrations de LM Studio en AgentManager.
5. Integración y persistencia de configuración en SettingsManager.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.interfaces import ClusterNode, ClusterFailoverStrategy, IMCPClientRegistry
from logic.lm_studio_vram import LMStudioVRAMManager
from logic.cluster_manager import ClusterManager
from logic.inference_router import InferenceRouter
from logic.agent_manager import AgentManager
from logic.settings_manager import SettingsManager


# ---------------------------------------------------------------------------
# 1. PRUEBAS: LMStudioVRAMManager
# ---------------------------------------------------------------------------

class TestLMStudioVRAMManager:
    """Pruebas para gestión dinámica de VRAM y ciclo de vida de modelos."""

    @pytest.mark.asyncio
    async def test_list_loaded_models_api_v1(self):
        """Verifica la consulta de modelos usando el endpoint nativo /api/v1/models."""
        manager = LMStudioVRAMManager(base_url="http://localhost:1234/v1")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"models": [{"id": "deepseek-v4", "loaded": True}]})

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_resp
            models = await manager.list_loaded_models()
            assert len(models) == 1
            assert models[0]["id"] == "deepseek-v4"

    @pytest.mark.asyncio
    async def test_load_model_success(self):
        """Verifica la carga programática de un modelo en memoria y VRAM."""
        manager = LMStudioVRAMManager(base_url="http://localhost:1234")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"instance_id": "inst_deepseek_123", "status": "loaded"})

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            res = await manager.load_model(
                model_name="deepseek-v4",
                context_length=8192,
                flash_attention=True,
                offload_kv_cache_to_gpu=True,
            )
            assert res["success"] is True
            assert res["instance_id"] == "inst_deepseek_123"

    @pytest.mark.asyncio
    async def test_unload_model_and_liberate_vram(self):
        """Verifica la descarga de un modelo para liberar VRAM para el viewport RTX de Omniverse."""
        manager = LMStudioVRAMManager(base_url="http://localhost:1234")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"instance_id": "inst_deepseek_123"})

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            res = await manager.unload_model("inst_deepseek_123")
            assert res["success"] is True
            assert res["instance_id"] == "inst_deepseek_123"

    @pytest.mark.asyncio
    async def test_unload_all_models_batch(self):
        """Verifica la descarga de todos los modelos activos en LM Studio."""
        manager = LMStudioVRAMManager(base_url="http://localhost:1234")
        with patch.object(
            manager,
            "list_loaded_models",
            AsyncMock(return_value=[{"id": "model_1"}, {"id": "model_2"}])
        ), patch.object(
            manager,
            "unload_model",
            AsyncMock(return_value={"success": True})
        ):
            res = await manager.unload_all_models()
            assert res["success"] is True
            assert len(res["unloaded_instances"]) == 2


# ---------------------------------------------------------------------------
# 2. PRUEBAS: ClusterManager
# ---------------------------------------------------------------------------

class TestClusterManager:
    """Pruebas para orquestación de clusters de inferencia multi-nodo."""

    def test_node_lifecycle_and_strategies(self):
        """Verifica agregar, recuperar y seleccionar nodos bajo distintas estrategias."""
        node1 = ClusterNode(name="Primary", url="http://127.0.0.1:1234/v1", last_latency_ms=10.0)
        node2 = ClusterNode(name="Secondary", url="http://192.168.1.100:1234/v1", last_latency_ms=5.0)

        cm = ClusterManager(nodes=[node1, node2], strategy=ClusterFailoverStrategy.PRIORITY)
        assert len(cm.get_nodes()) == 2

        # Priority debe retornar el primero elegible
        selected = cm.select_node()
        assert selected is not None
        assert selected.name == "Primary"

        # Lowest latency debe retornar node2 (5ms < 10ms)
        cm.set_strategy(ClusterFailoverStrategy.LOWEST_LATENCY)
        selected_fast = cm.select_node()
        assert selected_fast is not None
        assert selected_fast.name == "Secondary"

        # Round robin debe alternar
        cm.set_strategy(ClusterFailoverStrategy.ROUND_ROBIN)
        n_a = cm.select_node()
        n_b = cm.select_node()
        assert n_a != n_b

    def test_node_failure_marking_and_failover(self):
        """Verifica que marcar un nodo como no saludable provoca conmutación inmediata."""
        node1 = ClusterNode(name="Node1", url="http://node1:1234/v1")
        node2 = ClusterNode(name="Node2", url="http://node2:1234/v1")
        cm = ClusterManager(nodes=[node1, node2], strategy=ClusterFailoverStrategy.PRIORITY)

        cm.mark_node_failure("Node1")
        # El siguiente nodo seleccionado debe ser Node2 automáticamente
        next_node = cm.select_node()
        assert next_node is not None
        assert next_node.name == "Node2"

    @pytest.mark.asyncio
    async def test_check_health_all(self):
        """Verifica el sondeo concurrente de salud y latencia en todos los nodos."""
        node1 = ClusterNode(name="Node1", url="http://node1:1234/v1")
        cm = ClusterManager(nodes=[node1])

        mock_resp = AsyncMock()
        mock_resp.status = 200

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_resp
            health_map = await cm.check_health_all()
            assert health_map.get("Node1") is True
            assert node1.is_healthy is True
            assert node1.last_latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_cluster_manager_rejects_non_http_node_urls(self):
        """Verifica que nodos con esquemas no HTTP/HTTPS son rechazados en el sondeo de salud."""
        invalid_node = ClusterNode(name="BadNode", url="file:///etc/passwd")
        ftp_node = ClusterNode(name="FTPNode", url="ftp://192.168.1.50/api")
        cm = ClusterManager(nodes=[invalid_node, ftp_node])

        with patch("aiohttp.ClientSession.get") as mock_get:
            health_map = await cm.check_health_all()
            assert health_map.get("BadNode") is False
            assert health_map.get("FTPNode") is False
            assert invalid_node.is_healthy is False
            assert ftp_node.is_healthy is False
            mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 3. PRUEBAS: InferenceRouter con Cluster Failover
# ---------------------------------------------------------------------------

class TestInferenceRouterClusterFailover:
    """Pruebas de conmutación por error en el router de inferencia."""

    @pytest.mark.asyncio
    async def test_cluster_chat_completion_failover(self):
        """Verifica que si el nodo primario falla (ConnectionError), conmuta al secundario."""
        node1 = ClusterNode(name="Node1", url="http://failing-node:1234/v1")
        node2 = ClusterNode(name="Node2", url="http://healthy-node:1234/v1")
        cm = ClusterManager(nodes=[node1, node2], strategy=ClusterFailoverStrategy.PRIORITY)

        router = InferenceRouter(provider="cluster", cluster_manager=cm)

        # Mock de _execute_chat_request: falla para Node1 y triunfa para Node2
        async def mock_execute(url, payload, headers, target_model, provider_name):
            if "failing-node" in url:
                return {"success": False, "error_type": "ConnectionError", "message": "Connection refused"}
            return {
                "success": True,
                "data": {"choices": [{"message": {"role": "assistant", "content": "Respuesta desde Node2"}}]},
            }

        with patch.object(router, "_execute_chat_request", side_effect=mock_execute):
            res = await router.chat_completions([{"role": "user", "content": "Hola cluster"}])
            assert res["success"] is True
            assert res["data"]["choices"][0]["message"]["content"] == "Respuesta desde Node2"
            # Node1 debe haber quedado marcado como no saludable
            assert node1.is_healthy is False

    @pytest.mark.asyncio
    async def test_cluster_stream_chat_completion_failover(self):
        """Verifica conmutación por error en streaming antes de la emisión de tokens."""
        node1 = ClusterNode(name="Node1", url="http://bad-stream-node:1234/v1")
        node2 = ClusterNode(name="Node2", url="http://good-stream-node:1234/v1")
        cm = ClusterManager(nodes=[node1, node2], strategy=ClusterFailoverStrategy.PRIORITY)

        router = InferenceRouter(provider="cluster", cluster_manager=cm)

        async def mock_stream_exec(url, payload, headers, target_model, provider_name, **kwargs):
            if "bad-stream-node" in url:
                yield {"success": False, "error_type": "HTTPError", "message": "HTTP 503"}
            else:
                yield {
                    "success": True,
                    "data": {"choices": [{"delta": {"content": "Stream exitoso de Node2"}}]},
                }

        with patch.object(router, "_execute_stream_request", side_effect=mock_stream_exec):
            chunks = []
            async for chunk in router.stream_chat_completions([{"role": "user", "content": "Stream"}]):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0]["success"] is True
            assert chunks[0]["data"]["choices"][0]["delta"]["content"] == "Stream exitoso de Node2"
            assert node1.is_healthy is False


# ---------------------------------------------------------------------------
# 4. PRUEBAS: AgentManager con MCP Tool Calling y ReAct Loop
# ---------------------------------------------------------------------------

class TestAgentManagerMCPToolCalling:
    """Pruebas del ciclo ReAct con herramientas MCP en AgentManager."""

    @pytest.mark.asyncio
    async def test_agent_manager_executes_mcp_tool_call(self):
        """Verifica que AgentManager procesa tool_calls de la IA, invoca MCP y sintetiza respuesta."""
        router = InferenceRouter(provider="lm_studio")
        mock_registry = AsyncMock(spec=IMCPClientRegistry)
        mock_registry.list_available_tools.return_value = [
            {
                "server": "omni_usd",
                "name": "usd_list_prims",
                "description": "Lista prims en la escena",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
        mock_registry.call_tool.return_value = {
            "status": "success",
            "result": {"prims": ["/World/Light", "/World/Cube"]},
        }

        manager = AgentManager(router=router, mcp_registry=mock_registry)

        # Simular 2 turnos del stream:
        # Turno 1: el LLM emite un tool_call para usd_list_prims
        # Turno 2: el LLM recibe el resultado y genera la respuesta final
        turn_call = [
            {
                "success": True,
                "data": {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_usd_001",
                                        "type": "function",
                                        "function": {
                                            "name": "usd_list_prims",
                                            "arguments": "{}",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
            }
        ]

        turn_final = [
            {
                "success": True,
                "data": {
                    "choices": [
                        {
                            "delta": {
                                "content": "He encontrado los objetos /World/Light y /World/Cube en la escena."
                            }
                        }
                    ]
                },
            }
        ]

        stream_turns = [turn_call, turn_final]
        call_count = 0

        async def mock_stream(messages, **kwargs):
            nonlocal call_count
            current_turn = stream_turns[call_count]
            call_count += 1
            for item in current_turn:
                yield item

        with patch.object(router, "stream_chat_completions", side_effect=mock_stream):
            append_chunks = []
            final_res = await manager.process_prompt(
                "¿Qué prims hay en la escena?",
                append_callback=lambda c: append_chunks.append(c),
            )

            # Verificar que mock_registry.call_tool fue invocado con los argumentos del LLM
            mock_registry.call_tool.assert_called_once_with("omni_usd", "usd_list_prims", {})
            assert "He encontrado los objetos" in final_res
            # Verificar que el historial conservó el mensaje assistant con tool_calls y el mensaje tool
            roles = [m["role"] for m in manager._messages]
            assert "assistant" in roles
            assert "tool" in roles


# ---------------------------------------------------------------------------
# 5. PRUEBAS: SettingsManager con Clusters y LM Studio VRAM
# ---------------------------------------------------------------------------

class TestSettingsManagerClusterAndVRAM:
    """Pruebas de configuración de clústeres y gestores en SettingsManager."""

    def test_settings_manager_cluster_and_vram_instantiation(self, tmp_path):
        """Verifica la persistencia y carga de gestores de cluster y VRAM."""
        cfg_file = str(tmp_path / "test_settings.json")
        sm = SettingsManager(config_path=cfg_file)

        # Verificar alias canónico
        assert sm._canonicalize_provider_name("cluster") == "Local Cluster"
        assert sm._canonicalize_provider_name("local cluster") == "Local Cluster"

        # Verificar obtención de ClusterManager
        cm = sm.get_cluster_manager()
        assert isinstance(cm, ClusterManager)
        assert len(cm.get_nodes()) >= 1

        # Verificar obtención de LMStudioVRAMManager
        vm = sm.get_lm_studio_vram_manager()
        assert isinstance(vm, LMStudioVRAMManager)
        assert "1234" in vm.server_root
