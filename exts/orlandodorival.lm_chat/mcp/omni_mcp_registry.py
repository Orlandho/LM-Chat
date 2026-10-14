# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Módulo MCP (Model Context Protocol) Client Registry para NVIDIA Omniverse.
Implementa el contrato IMCPClientRegistry para la comunicación asíncrona vía JSON-RPC sobre stdio
con servidores MCP locales o remotos (ej. Google Drive, filesystem, etc.).
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional
from core.interfaces import IMCPClientRegistry

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """
    Gestiona la conexión y comunicación JSON-RPC 2.0 sobre stdio con un servidor MCP específico.
    """

    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        """
        Inicializa la instancia de conexión para un servidor MCP.

        Args:
            name: Nombre identificador único del servidor.
            command: Comando ejecutable para iniciar el subproceso.
            args: Argumentos de línea de comandos.
            env: Variables de entorno adicionales opcionales.
        """
        self.name: str = name
        self.command: str = command
        self.args: List[str] = args
        self.env: Optional[Dict[str, str]] = env
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._early_responses: Dict[int, Any] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._is_initialized: bool = False

    async def start(self, timeout: float = 10.0) -> bool:
        """
        Inicia el subproceso del servidor MCP y realiza el saludo inicial JSON-RPC (initialize).

        Args:
            timeout: Tiempo máximo de espera en segundos para la inicialización.

        Returns:
            bool: True si el servidor fue iniciado e inicializado exitosamente, False de lo contrario.
        """
        try:
            full_env = os.environ.copy()
            if self.env:
                full_env.update(self.env)

            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env
            )

            self._reader_task = asyncio.create_task(self._listen_stdout())

            # Realizar el saludo (initialize)
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "OmniMCPRegistry",
                    "version": "1.0.0"
                }
            }

            response = await asyncio.wait_for(
                self.send_request("initialize", init_params),
                timeout=timeout
            )

            if "error" in response:
                logger.error(f"Error de inicialización en servidor MCP '{self.name}': {response['error']}")
                await self.stop()
                return False

            # Enviar notificación initialized
            await self.send_notification("notifications/initialized", {})
            self._is_initialized = True
            logger.info(f"Servidor MCP '{self.name}' registrado e inicializado correctamente.")
            return True

        except Exception as e:
            logger.error(f"Fallo al iniciar el servidor MCP '{self.name}': {e}", exc_info=True)
            await self.stop()
            return False

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Envía una petición JSON-RPC 2.0 y espera la respuesta asíncrona.

        Args:
            method: Nombre del método JSON-RPC.
            params: Parámetros opcionales del método.

        Returns:
            Dict[str, Any]: Objeto de respuesta JSON-RPC.
        """
        if not self.process or self.process.returncode is not None or not self.process.stdin:
            raise RuntimeError(f"El servidor MCP '{self.name}' no está en ejecución.")

        self._request_id += 1
        req_id = self._request_id

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params if params is not None else {}
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_requests[req_id] = future

        # Si ya arribó una respuesta temprana para este ID, resolver de inmediato
        if req_id in self._early_responses:
            future.set_result(self._early_responses.pop(req_id))
            self._pending_requests.pop(req_id, None)
            return await future

        message = json.dumps(payload) + "\n"
        self.process.stdin.write(message.encode("utf-8"))
        await self.process.stdin.drain()

        try:
            return await future
        finally:
            self._pending_requests.pop(req_id, None)

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Envía una notificación JSON-RPC 2.0 sin esperar respuesta.

        Args:
            method: Nombre del método de notificación.
            params: Parámetros de la notificación.
        """
        if not self.process or self.process.returncode is not None or not self.process.stdin:
            return

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {}
        }

        message = json.dumps(payload) + "\n"
        self.process.stdin.write(message.encode("utf-8"))
        await self.process.stdin.drain()

    async def _listen_stdout(self) -> None:
        """
        Lee continuamente la salida estándar (stdout) del servidor MCP procesando mensajes JSON-RPC.
        """
        if not self.process or not self.process.stdout:
            return

        while True:
            try:
                line = await self.process.stdout.readline()
                # Optimization: readline() returning empty bytes indicates EOF (stream closed).
                # Breaking out prevents CPU-spinning infinite polling loops.
                if not line:
                    break

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                data = json.loads(line_str)
                req_id = data.get("id")

                if req_id is not None:
                    if req_id in self._pending_requests:
                        future = self._pending_requests[req_id]
                        if not future.done():
                            future.set_result(data)
                    else:
                        # Almacenar en buffer de respuestas tempranas evitando pérdidas por condiciones de carrera
                        self._early_responses[req_id] = data

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error procesando línea de stdout en servidor MCP '{self.name}': {e}")

        # Cancelar futuras solicitudes pendientes si el subproceso se cierra
        for req_id, future in self._pending_requests.items():
            if not future.done():
                future.set_exception(RuntimeError(f"La conexión con el servidor MCP '{self.name}' se cerró."))

    async def stop(self) -> None:
        """
        Detiene el subproceso y libera recursos.
        """
        self._pending_requests.clear()
        self._early_responses.clear()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self.process:
            try:
                if self.process.returncode is None:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                if self.process.returncode is None:
                    self.process.kill()
            self.process = None

        self._is_initialized = False


class OmniMCPRegistry(IMCPClientRegistry):
    """
    Registro centralizado y administrador del ciclo de vida para clientes de servidores MCP.
    """

    def __init__(self):
        """Inicializa el registro de servidores MCP."""
        self.servers: Dict[str, MCPServerConnection] = {}

    async def register_server(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Registra e inicia un servidor MCP local de manera asíncrona.

        Args:
            name: Nombre identificador único para el servidor MCP.
            command: Ejecutable o comando a ejecutar (ej. 'node', 'python').
            args: Argumentos pasados al comando.
            env: Variables de entorno específicas para la ejecución.

        Returns:
            bool: True si el registro e inicialización fueron exitosos, False en caso contrario.
        """
        if name in self.servers:
            logger.warning(f"El servidor MCP '{name}' ya se encuentra registrado. Se reiniciará.")
            await self.stop_server(name)

        server_conn = MCPServerConnection(name, command, args, env)
        success = await server_conn.start()
        if success:
            self.servers[name] = server_conn
            return True
        return False

    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """
        Pide el catálogo de herramientas (tools/list) a todos los servidores registrados
        y retorna una lista unificada compatible con esquemas OpenAI / Claude tool-calling.

        Returns:
            List[Dict[str, Any]]: Lista unificada de definiciones de herramientas.
        """
        all_tools: List[Dict[str, Any]] = []

        for server_name, server_conn in self.servers.items():
            if not server_conn._is_initialized:
                continue

            try:
                response = await server_conn.send_request("tools/list", {})
                if "result" in response and "tools" in response["result"]:
                    tools_data = response["result"]["tools"]
                    for tool in tools_data:
                        tool_name = tool.get("name", "")
                        description = tool.get("description", "")
                        input_schema = tool.get("inputSchema", tool.get("parameters", tool.get("input_schema", {})))

                        formatted_tool = {
                            "server": server_name,
                            "name": tool_name,
                            "description": description,
                            "input_schema": input_schema,
                            "parameters": input_schema,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "description": description,
                                "parameters": input_schema
                            }
                        }
                        all_tools.append(formatted_tool)
                elif "error" in response:
                    logger.error(f"Error solicitando tools/list al servidor MCP '{server_name}': {response['error']}")
            except Exception as e:
                logger.error(f"Excepción al listar herramientas del servidor MCP '{server_name}': {e}", exc_info=True)

        return all_tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoca la herramienta solicitada en el servidor MCP especificado vía JSON-RPC (tools/call).

        Args:
            server_name: Nombre del servidor MCP registrado.
            tool_name: Nombre de la herramienta a ejecutar.
            arguments: Parámetros/Argumentos dictados para la herramienta.

        Returns:
            Dict[str, Any]: Respuesta de la invocación con status ('success' o 'error') y datos.
        """
        if server_name not in self.servers:
            return {
                "status": "error",
                "error": f"Servidor MCP '{server_name}' no registrado."
            }

        server_conn = self.servers[server_name]
        if not server_conn._is_initialized:
            return {
                "status": "error",
                "error": f"Servidor MCP '{server_name}' no está inicializado."
            }

        try:
            params = {
                "name": tool_name,
                "arguments": arguments
            }
            response = await server_conn.send_request("tools/call", params)

            if "error" in response:
                return {
                    "status": "error",
                    "error": response["error"]
                }
            elif "result" in response:
                return {
                    "status": "success",
                    "result": response["result"]
                }
            else:
                return {
                    "status": "error",
                    "error": "Respuesta JSON-RPC inesperada sin result ni error."
                }
        except Exception as e:
            logger.error(f"Excepción al invocar la herramienta '{tool_name}' en '{server_name}': {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }

    async def stop_server(self, name: str) -> bool:
        """
        Detiene y remueve un servidor MCP registrado.

        Args:
            name: Nombre del servidor MCP a detener.

        Returns:
            bool: True si fue detenido, False si no existía.
        """
        if name in self.servers:
            server_conn = self.servers.pop(name)
            await server_conn.stop()
            return True
        return False

    async def close(self) -> None:
        """
        Detiene todos los servidores MCP registrados y libera recursos.
        """
        server_names = list(self.servers.keys())
        for name in server_names:
            await self.stop_server(name)
