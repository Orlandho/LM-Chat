# -*- coding: utf-8 -*-

"""
LM-Chat™ CLI Harness for Enterprise & Advanced Users.

Provides an interactive REPL terminal interface and direct prompt execution tool
for testing, evaluating, and interacting with LLM providers (LM Studio, Ollama, vLLM, Cloud)
with full persistent local chat history support.
"""

import sys
import os
import argparse
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

# Ensure UTF-8 output encoding in Windows terminals for emojis and Unicode characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path when running cli/omni_harness.py directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.inference_router import InferenceRouter
from logic.chat_history import LocalChatHistoryManager
from core.interfaces import IChatHistoryManager, ChatSession, ChatMessage


BANNER = r"""
===================================================================
    __    __  ___        ________          __ 
   / /   /  |/  /       / ____/ /_  ____ _/ /_
  / /   / /|_/ /  ____ / /   / __ \/ __ `/ __/
 / /___/ /  / /  /___// /___/ / / / /_/ / /_  
/_____/_/  /_/        \____/_/ /_/\__,_/\__/  
                                              
   LM-Chat™ Enterprise CLI Harness - NVIDIA Omniverse Agentic Suite
===================================================================
"""


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments for the CLI harness.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="LM-Chat™ Enterprise CLI Harness - Multi-Provider LLM Interactive Console"
    )
    parser.add_argument(
        "-p",
        "--provider",
        type=str,
        default="lm_studio",
        choices=["lm_studio", "ollama", "vllm", "cloud"],
        help="Inference provider (default: lm_studio)",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Model name (optional, defaults to provider recommendation)",
    )
    parser.add_argument(
        "-u",
        "--base-url",
        type=str,
        default=None,
        help="Custom server base URL (optional)",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        type=str,
        default=None,
        help="API Key for authenticated services (optional)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=600.0,
        help="Request timeout in seconds (default: 600.0s)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Direct prompt to execute (if omitted, starts interactive REPL)",
    )
    parser.add_argument(
        "-s",
        "--system-prompt",
        type=str,
        default="Eres un asistente de IA avanzado para NVIDIA Omniverse y desarrollo de software.",
        help="Custom system prompt for the session",
    )
    parser.add_argument(
        "--storage-dir",
        type=str,
        default=None,
        help="Directorio local personalizado para persistencia del historial de chat",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="ID de sesión para continuar una conversación existente",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Lista todas las conversaciones guardadas en el historial local y sale",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Busca en el historial de sesiones locales por título o contenido y sale",
    )
    return parser.parse_args()


class LMChatCLI:
    """LM-Chat CLI Harness Session Manager with Local History Persistence."""

    def __init__(
        self,
        router: InferenceRouter,
        system_prompt: str,
        history_manager: Optional[IChatHistoryManager] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Initializes the CLI session with an InferenceRouter and Chat History Manager.

        Args:
            router (InferenceRouter): Configured router instance.
            system_prompt (str): Base system prompt for conversation.
            history_manager (Optional[IChatHistoryManager]): Local history manager.
            session_id (Optional[str]): Optional existing session ID to resume.
        """
        self.router = router
        self.system_prompt = system_prompt
        self.history_manager: IChatHistoryManager = (
            history_manager if history_manager is not None else LocalChatHistoryManager()
        )
        self.current_session: Optional[ChatSession] = None

        if session_id:
            loaded = self.history_manager.get_session(session_id)
            if loaded:
                self.current_session = loaded
                if loaded.metadata:
                    prov = loaded.metadata.get("provider")
                    mod = loaded.metadata.get("model")
                    if prov:
                        norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                        if norm_prov in ["lm_studio", "ollama", "vllm", "cloud"]:
                            self.router.set_provider(provider=norm_prov, model=mod)

        if not self.current_session:
            now = datetime.now(timezone.utc).isoformat()
            self.current_session = ChatSession(
                session_id=uuid.uuid4().hex,
                title=LocalChatHistoryManager.DEFAULT_TITLE,
                created_at=now,
                updated_at=now,
                messages=[],
                metadata={"provider": self.router.provider, "model": self.router.model},
            )

        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Replay conversation context if continuing an existing session
        for msg in self.current_session.messages:
            if msg.role in ("user", "assistant", "system"):
                self.messages.append({"role": msg.role, "content": msg.content})

    def reset_conversation(self) -> None:
        """Resets the conversation history keeping system prompt and creates a new local session."""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        now = datetime.now(timezone.utc).isoformat()
        self.current_session = ChatSession(
            session_id=uuid.uuid4().hex,
            title=LocalChatHistoryManager.DEFAULT_TITLE,
            created_at=now,
            updated_at=now,
            messages=[],
            metadata={"provider": self.router.provider, "model": self.router.model},
        )
        print(f"\n[CLI] Historial reiniciado. Nueva sesión ID: {self.current_session.session_id[:8]}\n")

    def print_status(self) -> None:
        """Prints current provider configuration and active session status."""
        session_title = self.current_session.title if self.current_session else "Ninguna"
        session_id = self.current_session.session_id if self.current_session else "N/A"
        msg_count = len(self.current_session.messages) if self.current_session else 0

        print(f"\n[Proveedor Activo]: {self.router.provider.upper()}")
        print(f"[Modelo]:           {self.router.model}")
        print(f"[URL Base]:         {self.router.base_url}")
        print(f"[Timeout]:          {self.router.timeout}s")
        print(f"[API Key]:          {'Configurada' if self.router.api_key else 'Ninguna'}")
        print(f"[Sesión Activa]:    {session_title} (ID: {session_id[:8]}..., {msg_count} msgs)\n")

    def print_history_list(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Prints list of stored chat sessions.

        Args:
            query (Optional[str]): Optional filter query.

        Returns:
            List[Dict[str, Any]]: The listed sessions.
        """
        if query:
            sessions = self.history_manager.search_sessions(query)
            header = f"\n=== Resultados de Búsqueda para '{query}' ({len(sessions)}) ==="
        else:
            sessions = self.history_manager.list_sessions()
            header = f"\n=== Historial de Chats Locales ({len(sessions)} sesiones) ==="

        print(header)
        if not sessions:
            print("  (No hay sesiones guardadas aún)")
            print("-" * 67 + "\n")
            return sessions

        for i, s in enumerate(sessions, start=1):
            is_active = (
                "[*]"
                if (self.current_session and s["session_id"] == self.current_session.session_id)
                else "   "
            )
            title = s.get("title", "Conversación")
            sid = s.get("session_id", "")[:8]
            count = s.get("message_count", 0)
            updated = s.get("updated_at", "")[:19].replace("T", " ")
            print(f" {is_active} [{i}] {sid} | {title[:35]:<35} | {count:2d} msgs | {updated}")
        print("-" * 67 + "\n")
        return sessions

    def load_session_by_identifier(self, identifier: str) -> bool:
        """Loads a session by 1-based index or by session_id prefix.

        Args:
            identifier (str): Session number (with optional '#' prefix) or ID prefix.

        Returns:
            bool: True if successfully loaded.
        """
        clean_id = identifier.strip()
        if clean_id.startswith("#"):
            clean_id = clean_id[1:].strip()

        sessions = self.history_manager.list_sessions()
        target_id: Optional[str] = None

        if clean_id.isdigit():
            idx = int(clean_id) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["session_id"]
        else:
            for s in sessions:
                if s["session_id"].startswith(clean_id):
                    target_id = s["session_id"]
                    break

        if not target_id:
            print(f"\n[Error] No se encontró ninguna sesión que coincida con '{identifier}'.\n")
            return False

        loaded = self.history_manager.get_session(target_id)
        if not loaded:
            print(f"\n[Error] No se pudo leer la sesión '{target_id}'.\n")
            return False

        self.current_session = loaded
        self.messages = [{"role": "system", "content": self.system_prompt}]
        for msg in self.current_session.messages:
            if msg.role in ("user", "assistant", "system"):
                self.messages.append({"role": msg.role, "content": msg.content})

        if loaded.metadata:
            prov = loaded.metadata.get("provider")
            mod = loaded.metadata.get("model")
            if prov:
                norm_prov = prov.lower().replace(" ", "_").replace("apis", "").replace("api", "").strip("_")
                if norm_prov in ["lm_studio", "ollama", "vllm", "cloud"]:
                    self.router.set_provider(provider=norm_prov, model=mod)

        print(f"\n[CLI] Sesión cargada: '{loaded.title}' (ID: {loaded.session_id[:8]}, {len(loaded.messages)} msgs)\n")
        return True

    def delete_session_by_identifier(self, identifier: str) -> bool:
        """Deletes a session by index or ID prefix.

        Args:
            identifier (str): Session index (with optional '#' prefix) or ID prefix.

        Returns:
            bool: True if deleted.
        """
        clean_id = identifier.strip()
        if clean_id.startswith("#"):
            clean_id = clean_id[1:].strip()

        sessions = self.history_manager.list_sessions()
        target_id: Optional[str] = None

        if clean_id.isdigit():
            idx = int(clean_id) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["session_id"]
        else:
            for s in sessions:
                if s["session_id"].startswith(clean_id):
                    target_id = s["session_id"]
                    break

        if not target_id:
            print(f"\n[Error] No se encontró la sesión '{identifier}' para eliminar.\n")
            return False

        success = self.history_manager.delete_session(target_id)
        if success:
            print(f"\n[CLI] Sesión '{target_id[:8]}' eliminada correctamente.")
            if self.current_session and self.current_session.session_id == target_id:
                self.reset_conversation()
        else:
            print(f"\n[Error] Falló la eliminación de la sesión '{target_id}'.\n")
        return success

    async def execute_prompt(self, user_prompt: str) -> str:
        """Executes a prompt with real-time response streaming to stdout and persists to local history.

        Args:
            user_prompt (str): User input prompt.

        Returns:
            str: Full response accumulated from the stream.
        """
        self.messages.append({"role": "user", "content": user_prompt})

        # Persist user prompt to local session
        if self.current_session:
            user_msg = ChatMessage(role="user", content=user_prompt)
            self.current_session.messages.append(user_msg)
            default_titles = (LocalChatHistoryManager.DEFAULT_TITLE, "Nueva Conversación", "Nueva conversación")
            if self.current_session.title in default_titles and len(self.current_session.messages) <= 2:
                self.current_session.title = LocalChatHistoryManager.generate_title_from_prompt(user_prompt)
            self.current_session.updated_at = datetime.now(timezone.utc).isoformat()
            self.history_manager.save_session(self.current_session)

        sys.stdout.write("\nAssistant > ")
        sys.stdout.flush()

        full_content = ""
        error_occurred = False

        async for chunk_obj in self.router.stream_chat_completions(self.messages):
            if chunk_obj.get("success"):
                data = chunk_obj.get("data", {})
                choices = data.get("choices", [{}])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        sys.stdout.write(content)
                        sys.stdout.flush()
            else:
                error_occurred = True
                err_msg = chunk_obj.get("message", "Error desconocido")
                sys.stdout.write(f"\n\n[Error de Inferencia]: {err_msg}\n")
                sys.stdout.flush()
                break

        sys.stdout.write("\n")
        sys.stdout.flush()

        if not error_occurred and full_content:
            self.messages.append({"role": "assistant", "content": full_content})
            # Persist assistant response to local session
            if self.current_session:
                asst_msg = ChatMessage(role="assistant", content=full_content)
                self.current_session.messages.append(asst_msg)
                self.current_session.updated_at = datetime.now(timezone.utc).isoformat()
                self.history_manager.save_session(self.current_session)

        return full_content

    async def run_repl(self) -> None:
        """Runs the interactive REPL read-eval-print loop."""
        print(BANNER)
        self.print_status()
        print("Escribe tus consultas o ingresa '/help' para ver los comandos disponibles.")
        print("Usa '/exit' o Ctrl+C para salir.\n" + "-" * 67 + "\n")

        loop = asyncio.get_event_loop()

        while True:
            try:
                user_input = await loop.run_in_executor(None, input, "User > ")
                user_input = user_input.strip()

                if not user_input:
                    continue

                # Handle CLI commands
                if user_input.startswith("/"):
                    cmd_parts = user_input.split(maxsplit=1)
                    command = cmd_parts[0].lower()
                    arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                    if command in ["/exit", "/quit"]:
                        print("\n¡Hasta luego! Cerrando sesión LM-Chat CLI.\n")
                        break
                    elif command == "/help":
                        print("\nComandos Disponibles:")
                        print("  /switch <provider>   - Cambia el proveedor (lm_studio, ollama, vllm, cloud)")
                        print("  /model <name>        - Cambia el modelo activo")
                        print("  /url <base_url>      - Cambia la URL base del servidor")
                        print("  /key <api_key>       - Establece la API Key")
                        print("  /status              - Muestra la configuración y sesión activa")
                        print("  /history [/sessions] - Lista las conversaciones guardadas en disco local")
                        print("  /load <id | #>       - Carga una sesión anterior del historial")
                        print("  /new [título]        - Inicia una nueva sesión de chat limpia")
                        print("  /delete <id | #>     - Elimina una sesión del historial")
                        print("  /search <texto>      - Busca sesiones por título o palabras clave")
                        print("  /clear               - Limpia la conversación e inicia nueva sesión")
                        print("  /exit | /quit        - Sale del arnés CLI\n")
                    elif command in ["/history", "/sessions"]:
                        self.print_history_list()
                    elif command == "/search":
                        if arg:
                            self.print_history_list(query=arg)
                        else:
                            print("\n[Error] Ingresa el término de búsqueda. Ej: /search robot\n")
                    elif command == "/load":
                        if arg:
                            self.load_session_by_identifier(arg)
                        else:
                            print("\n[Error] Especifica el número [#] o ID de la sesión. Usa '/history' para listar.\n")
                    elif command == "/new":
                        title = arg if arg else None
                        self.current_session = self.history_manager.create_session(
                            title=title,
                            metadata={"provider": self.router.provider, "model": self.router.model},
                        )
                        self.messages = [{"role": "system", "content": self.system_prompt}]
                        print(f"\n[CLI] Nueva sesión creada: '{self.current_session.title}' (ID: {self.current_session.session_id[:8]})\n")
                    elif command == "/delete":
                        if arg:
                            self.delete_session_by_identifier(arg)
                        else:
                            print("\n[Error] Especifica el número [#] o ID de la sesión a eliminar.\n")
                    elif command in ["/switch", "/provider"]:
                        if arg in ["lm_studio", "ollama", "vllm", "cloud"]:
                            self.router.set_provider(provider=arg)
                            if self.current_session:
                                if not self.current_session.metadata:
                                    self.current_session.metadata = {}
                                self.current_session.metadata["provider"] = self.router.provider
                                self.current_session.metadata["model"] = self.router.model
                                self.history_manager.save_session(self.current_session)
                            print(f"\n[CLI] Proveedor cambiado a: {arg.upper()}")
                            self.print_status()
                        else:
                            print(f"\n[Error] Proveedor inválido '{arg}'. Opciones: lm_studio, ollama, vllm, cloud\n")
                    elif command == "/model":
                        if arg:
                            self.router.set_provider(provider=self.router.provider, model=arg)
                            if self.current_session:
                                if not self.current_session.metadata:
                                    self.current_session.metadata = {}
                                self.current_session.metadata["model"] = self.router.model
                                self.history_manager.save_session(self.current_session)
                            print(f"\n[CLI] Modelo actualizado a: {arg}\n")
                        else:
                            print("\n[Error] Especifica el nombre del modelo. Ej: /model llama3\n")
                    elif command == "/url":
                        if arg:
                            self.router.set_provider(provider=self.router.provider, base_url=arg)
                            print(f"\n[CLI] URL base actualizada a: {arg}\n")
                        else:
                            print("\n[Error] Especifica la URL base. Ej: /url http://localhost:1234/v1\n")
                    elif command == "/key":
                        self.router.set_provider(provider=self.router.provider, api_key=arg if arg else None)
                        print(f"\n[CLI] API Key {'actualizada' if arg else 'eliminada'}.\n")
                    elif command == "/status":
                        self.print_status()
                    elif command == "/clear":
                        self.reset_conversation()
                    else:
                        print(f"\n[Error] Comando desconocido '{command}'. Usa '/help' para ayuda.\n")
                    continue

                # Execute prompt
                await self.execute_prompt(user_input)

            except (KeyboardInterrupt, EOFError):
                print("\n\nSesión finalizada por el usuario. ¡Hasta luego!\n")
                break


# Backward compatibility alias
OmniCLI = LMChatCLI


async def main() -> None:
    """Main CLI entrypoint."""
    args = parse_arguments()

    router = InferenceRouter(
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        timeout=args.timeout,
    )

    history_mgr = LocalChatHistoryManager(storage_dir=args.storage_dir) if args.storage_dir else LocalChatHistoryManager()

    cli = LMChatCLI(
        router=router,
        system_prompt=args.system_prompt,
        history_manager=history_mgr,
        session_id=args.session,
    )

    if args.history:
        cli.print_history_list()
        return

    if args.search:
        cli.print_history_list(query=args.search)
        return

    if args.prompt:
        # Direct execution mode
        await cli.execute_prompt(args.prompt)
    else:
        # REPL mode
        await cli.run_repl()


if __name__ == "__main__":
    asyncio.run(main())
