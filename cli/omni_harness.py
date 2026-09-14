# -*- coding: utf-8 -*-

"""
OmniAgent CLI Harness for Enterprise & Advanced Users.

Provides an interactive REPL terminal interface and direct prompt execution tool
for testing, evaluating, and interacting with LLM providers (LM Studio, Ollama, vLLM, Cloud).
"""

import sys
import os
import argparse
import asyncio
from typing import List, Dict, Optional

# Ensure project root is in sys.path when running cli/omni_harness.py directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.inference_router import InferenceRouter


BANNER = r"""
===================================================================
   ___                  _   _                      _
  / _ \ _ __ ___  _ __ (_) /_\   __ _  ___ _ __ | |_
 / /_\ \ '_ ` _ \| '_ \| |//_\\ / _` |/ _ \ '_ \| __|
/ /_\\ \ | | | | | | | | /  _  \ (_| |  __/ | | | |_
\____/|_| |_| |_|_| |_|_\_/ \_/\__, |\___|_| |_|\__|
                               |___/
  OmniAgent Enterprise CLI Harness - NVIDIA Omniverse Agentic Suite
===================================================================
"""


def parse_arguments() -> argparse.Namespace:
    """
    Parses command-line arguments for the CLI harness.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="OmniAgent Enterprise CLI Harness - Multi-Provider LLM Interactive Console"
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
    return parser.parse_args()


class OmniCLI:
    """CLI Harness Session Manager."""

    def __init__(self, router: InferenceRouter, system_prompt: str) -> None:
        """
        Initializes the CLI session with an InferenceRouter.

        Args:
            router (InferenceRouter): Configured router instance.
            system_prompt (str): Base system prompt for conversation.
        """
        self.router = router
        self.system_prompt = system_prompt
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]

    def reset_conversation(self) -> None:
        """Resets the conversation history keeping system prompt."""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        print("\n[CLI] Historial de conversación reiniciado.\n")

    def print_status(self) -> None:
        """Prints current provider configuration status."""
        print(f"\n[Proveedor Activo]: {self.router.provider.upper()}")
        print(f"[Modelo]:           {self.router.model}")
        print(f"[URL Base]:         {self.router.base_url}")
        print(f"[Timeout]:          {self.router.timeout}s")
        print(f"[API Key]:          {'Configurada' if self.router.api_key else 'Ninguna'}\n")

    async def execute_prompt(self, user_prompt: str) -> str:
        """
        Executes a prompt with real-time response streaming to stdout.

        Args:
            user_prompt (str): User input prompt.

        Returns:
            str: Full response accumulated from the stream.
        """
        self.messages.append({"role": "user", "content": user_prompt})

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
                        print("\n¡Hasta luego! Cerrando sesión OmniAgent CLI.\n")
                        break
                    elif command == "/help":
                        print("\nComandos Disponibles:")
                        print("  /switch <provider>  - Cambia el proveedor (lm_studio, ollama, vllm, cloud)")
                        print("  /model <name>       - Cambia el modelo activo")
                        print("  /url <base_url>     - Cambia la URL base del servidor")
                        print("  /key <api_key>      - Establece la API Key")
                        print("  /status             - Muestra la configuración actual")
                        print("  /clear              - Reinicia el historial de chat")
                        print("  /exit | /quit       - Sale del arnés CLI\n")
                    elif command in ["/switch", "/provider"]:
                        if arg in ["lm_studio", "ollama", "vllm", "cloud"]:
                            self.router.set_provider(provider=arg)
                            print(f"\n[CLI] Proveedor cambiado a: {arg.upper()}")
                            self.print_status()
                        else:
                            print(f"\n[Error] Proveedor inválido '{arg}'. Opciones: lm_studio, ollama, vllm, cloud\n")
                    elif command == "/model":
                        if arg:
                            self.router.set_provider(provider=self.router.provider, model=arg)
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

    cli = OmniCLI(router=router, system_prompt=args.system_prompt)

    if args.prompt:
        # Direct execution mode
        await cli.execute_prompt(args.prompt)
    else:
        # REPL mode
        await cli.run_repl()


if __name__ == "__main__":
    asyncio.run(main())
