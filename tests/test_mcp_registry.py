# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Pruebas unitarias automatizadas para OmniMCPRegistry (mcp/omni_mcp_registry.py).
Utiliza mocks de asyncio.subprocess para probar el registro de servidores, listado de herramientas e invocación.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.omni_mcp_registry import OmniMCPRegistry, MCPServerConnection
from core.interfaces import IMCPClientRegistry


class MockStreamReader:
    """Mock para asyncio.StreamReader que entrega líneas JSON-RPC preconfiguradas con latencia cero."""

    def __init__(self):
        self._queue = asyncio.Queue()

    def add_line(self, line_dict: dict):
        line_bytes = (json.dumps(line_dict) + "\n").encode("utf-8")
        self._queue.put_nowait(line_bytes)

    async def readline(self):
        return await self._queue.get()


class MockStreamWriter:
    """Mock para asyncio.StreamWriter que captura lo escrito."""

    def __init__(self):
        self.written_data = []

    def write(self, data: bytes):
        self.written_data.append(data)

    async def drain(self):
        pass


def make_mock_process():
    """Crea una instancia de proceso simulado interactivo con sus propios streams independientes."""
    mock_process = AsyncMock()
    mock_process.returncode = None
    mock_process.stdin = MockStreamWriter()
    mock_process.stdout = MockStreamReader()
    mock_process.stderr = AsyncMock()
    mock_process.wait = AsyncMock(return_value=0)
    mock_process.terminate = MagicMock()
    mock_process.kill = MagicMock()
    return mock_process


@pytest.fixture
def mock_subprocess():
    """Fixture que reemplaza asyncio.create_subprocess_exec con un proceso simulado interactivo."""
    mock_process = make_mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        yield mock_exec, mock_process


@pytest.mark.asyncio
async def test_imcp_client_registry_interface():
    """Verifica que OmniMCPRegistry implementa la interfaz IMCPClientRegistry."""
    registry = OmniMCPRegistry()
    assert isinstance(registry, IMCPClientRegistry)


@pytest.mark.asyncio
async def test_register_server_success(mock_subprocess):
    """Prueba el registro exitoso de un servidor MCP."""
    _, mock_proc = mock_subprocess
    registry = OmniMCPRegistry()

    # Simular respuesta a la solicitud 'initialize' (id=1)
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "gdrive-mcp", "version": "1.0.0"}
        }
    })

    success = await registry.register_server(
        name="gdrive",
        command="npx",
        args=["-y", "@us-all/google-drive-mcp"],
        env={"GDRIVE_KEY": "test_key"}
    )

    assert success is True
    assert "gdrive" in registry.servers
    assert registry.servers["gdrive"]._is_initialized is True

    await registry.close()


@pytest.mark.asyncio
async def test_register_server_failure(mock_subprocess):
    """Prueba el fallo de registro cuando el servidor retorna un error JSON-RPC."""
    _, mock_proc = mock_subprocess
    registry = OmniMCPRegistry()

    # Simular error en initialize
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32603, "message": "Internal initialization error"}
    })

    success = await registry.register_server(
        name="failed_server",
        command="python",
        args=["server.py"]
    )

    assert success is False
    assert "failed_server" not in registry.servers

    await registry.close()


@pytest.mark.asyncio
async def test_list_available_tools(mock_subprocess):
    """Prueba la unificación del catálogo de herramientas de múltiples servidores."""
    _, mock_proc = mock_subprocess
    registry = OmniMCPRegistry()

    # 1. Registrar servidor
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2024-11-05"}
    })
    await registry.register_server("gdrive", "npx", ["gdrive-mcp"])

    # 2. Simular respuesta a 'tools/list' (id=2)
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {
                    "name": "read_doc",
                    "description": "Lee un documento de Google Drive",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"file_id": {"type": "string"}},
                        "required": ["file_id"]
                    }
                }
            ]
        }
    })

    tools = await registry.list_available_tools()

    assert len(tools) == 1
    tool = tools[0]
    assert tool["server"] == "gdrive"
    assert tool["name"] == "read_doc"
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "read_doc"
    assert "file_id" in tool["function"]["parameters"]["properties"]

    await registry.close()


@pytest.mark.asyncio
async def test_call_tool_success(mock_subprocess):
    """Prueba la invocación exitosa de una herramienta."""
    _, mock_proc = mock_subprocess
    registry = OmniMCPRegistry()

    # 1. Registrar servidor
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2024-11-05"}
    })
    await registry.register_server("gdrive", "npx", ["gdrive-mcp"])

    # 2. Simular respuesta a 'tools/call' (id=2)
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [
                {"type": "text", "text": "Contenido del documento de Google Drive"}
            ]
        }
    })

    res = await registry.call_tool("gdrive", "read_doc", {"file_id": "doc_123"})

    assert res["status"] == "success"
    assert "result" in res
    assert res["result"]["content"][0]["text"] == "Contenido del documento de Google Drive"

    await registry.close()


@pytest.mark.asyncio
async def test_call_tool_unregistered_server():
    """Prueba llamar a una herramienta de un servidor no registrado."""
    registry = OmniMCPRegistry()
    res = await registry.call_tool("nonexistent", "some_tool", {})
    assert res["status"] == "error"
    assert "no registrado" in res["error"]


@pytest.mark.asyncio
async def test_call_tool_server_error(mock_subprocess):
    """Prueba el manejo de errores cuando el servidor retorna un error al ejecutar la herramienta."""
    _, mock_proc = mock_subprocess
    registry = OmniMCPRegistry()

    # 1. Registrar servidor
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2024-11-05"}
    })
    await registry.register_server("gdrive", "npx", ["gdrive-mcp"])

    # 2. Simular error en 'tools/call' (id=2)
    mock_proc.stdout.add_line({
        "jsonrpc": "2.0",
        "id": 2,
        "error": {
            "code": -32602,
            "message": "ID de documento inválido o sin permisos"
        }
    })

    res = await registry.call_tool("gdrive", "read_doc", {"file_id": "bad_id"})

    assert res["status"] == "error"
    assert res["error"]["code"] == -32602

    await registry.close()


@pytest.mark.asyncio
async def test_stop_server_and_close(mock_subprocess):
    """Prueba la detención individual y masiva de servidores con procesos mock independientes."""
    mock_exec, _ = mock_subprocess
    proc1 = make_mock_process()
    proc2 = make_mock_process()
    mock_exec.side_effect = [proc1, proc2]
    registry = OmniMCPRegistry()

    proc1.stdout.add_line({"jsonrpc": "2.0", "id": 1, "result": {}})
    await registry.register_server("server1", "python", ["s1.py"])

    proc2.stdout.add_line({"jsonrpc": "2.0", "id": 1, "result": {}})
    await registry.register_server("server2", "python", ["s2.py"])

    assert len(registry.servers) == 2

    stopped = await registry.stop_server("server1")
    assert stopped is True
    assert "server1" not in registry.servers
    assert len(registry.servers) == 1

    await registry.close()
    assert len(registry.servers) == 0


@pytest.mark.asyncio
async def test_register_server_input_validation():
    """Prueba que el registro de servidores rechace entradas inválidas o vacías."""
    registry = OmniMCPRegistry()

    # Nombre inválido o vacío
    assert await registry.register_server(name="", command="python", args=[]) is False
    assert await registry.register_server(name=None, command="python", args=[]) is False

    # Comando inválido o vacío
    assert await registry.register_server(name="srv", command="", args=[]) is False
    assert await registry.register_server(name="srv", command=None, args=[]) is False

    # Argumentos no de tipo lista
    assert await registry.register_server(name="srv", command="python", args="invalid") is False

    # Entorno no de tipo diccionario
    assert await registry.register_server(name="srv", command="python", args=[], env="invalid") is False

    await registry.close()


@pytest.mark.asyncio
async def test_call_tool_input_validation():
    """Prueba que la invocación de herramientas rechace parámetros inválidos."""
    registry = OmniMCPRegistry()

    res1 = await registry.call_tool(server_name="", tool_name="tool", arguments={})
    assert res1["status"] == "error"
    assert "validación" in res1["error"].lower()

    res2 = await registry.call_tool(server_name="srv", tool_name="", arguments={})
    assert res2["status"] == "error"
    assert "validación" in res2["error"].lower()

    res3 = await registry.call_tool(server_name="srv", tool_name="tool", arguments=None)
    assert res3["status"] == "error"
    assert "validación" in res3["error"].lower()

    await registry.close()
