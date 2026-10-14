# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Gestor de Historial de Chats Local para LM-Chat™ (NVIDIA Omniverse Agentic Suite).
Implementa IChatHistoryManager con persistencia atómica en disco local (JSON),
indexación de sesiones, búsqueda de contexto, exportación/importación y auto-titulado.
"""

import os
import re
import json
import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from core.interfaces import IChatHistoryManager, ChatSession, ChatMessage


class LocalChatHistoryManager(IChatHistoryManager):
    """Implementación local y desacoplada del historial de conversaciones."""

    DEFAULT_TITLE = "Nueva Conversación"
    MAX_IMPORT_SIZE: int = 10_000_000  # 10MB payload limit to prevent memory exhaustion DoS

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        """Inicializa el gestor de historial local.

        Args:
            storage_dir (Optional[str]): Directorio de persistencia. Si no se
                especifica, utiliza LM_CHAT_STORAGE_PATH o ~/.lm_chat/sessions.
        """
        if storage_dir:
            self._storage_dir = os.path.abspath(storage_dir)
        else:
            env_path = os.environ.get("LM_CHAT_STORAGE_PATH")
            if env_path:
                self._storage_dir = os.path.abspath(env_path)
            else:
                self._storage_dir = os.path.abspath(
                    os.path.join(os.path.expanduser("~"), ".lm_chat", "sessions")
                )

        self._ensure_storage_dir()

    @property
    def storage_dir(self) -> str:
        """Ruta absoluta del directorio de almacenamiento."""
        return self._storage_dir

    def _ensure_storage_dir(self) -> None:
        """Crea el directorio de almacenamiento si no existe con permisos seguros."""
        try:
            os.makedirs(self._storage_dir, mode=0o700, exist_ok=True)
        except Exception as e:
            print(f"[LocalChatHistoryManager] Error creando directorio {self._storage_dir}: {e}")

    def _sanitize_session_id(self, session_id: Any) -> str:
        """Limpia el identificador de sesión para evitar vulnerabilidades de directory traversal.

        Args:
            session_id (Any): ID a sanitizar. Acepta cualquier tipo sin lanzar excepciones.

        Returns:
            str: ID seguro alfanumérico con guiones y guiones bajos.
        """
        if session_id is None or not isinstance(session_id, (str, int, float)):
            return uuid.uuid4().hex
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(session_id))
        if not safe_id:
            safe_id = uuid.uuid4().hex
        return safe_id

    def _get_session_path(self, session_id: str) -> str:
        """Obtiene la ruta completa del archivo JSON de la sesión."""
        safe_id = self._sanitize_session_id(session_id)
        return os.path.join(self._storage_dir, f"{safe_id}.json")

    def _current_timestamp(self) -> str:
        """Genera una marca de tiempo UTC en formato ISO 8601."""
        return datetime.now(timezone.utc).isoformat()

    # --- Métodos de la Interfaz IChatHistoryManager ---

    def create_session(
        self, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> ChatSession:
        """Crea e inicializa una nueva sesión de chat persistente.

        Args:
            title (Optional[str]): Título opcional de la sesión.
            metadata (Optional[Dict[str, Any]]): Metadatos adicionales (ej: proveedor, modelo).

        Returns:
            ChatSession: Sesión recién creada y guardada.
        """
        session_id = uuid.uuid4().hex
        now = self._current_timestamp()
        session_title = title.strip() if title and title.strip() else self.DEFAULT_TITLE

        session = ChatSession(
            session_id=session_id,
            title=session_title,
            created_at=now,
            updated_at=now,
            messages=[],
            metadata=dict(metadata) if metadata else {},
        )

        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Recupera una sesión existente por su identificador único.

        Args:
            session_id (str): Identificador de la sesión.

        Returns:
            Optional[ChatSession]: La sesión reconstruida o None si no existe o es corrupta.
        """
        if not session_id:
            return None

        file_path = self._get_session_path(session_id)
        if not os.path.exists(file_path):
            return None

        try:
            data = None
            for _attempt in range(5):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    break
                except PermissionError:
                    time.sleep(0.015)
            if data is None:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            if not isinstance(data, dict):
                return None
            return ChatSession.from_dict(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, AttributeError, Exception) as e:
            print(f"[LocalChatHistoryManager] Error leyendo sesión {session_id}: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lista los metadatos resumidos de todas las sesiones ordenadas cronológicamente.

        Returns:
            List[Dict[str, Any]]: Lista de resúmenes de sesión ordenados por updated_at descendente.
        """
        self._ensure_storage_dir()
        summaries: List[Dict[str, Any]] = []

        try:
            filenames = os.listdir(self._storage_dir)
        except OSError as e:
            print(f"[LocalChatHistoryManager] Error listando directorio {self._storage_dir}: {e}")
            return summaries

        for fname in filenames:
            if not fname.endswith(".json") or fname.startswith("."):
                continue

            file_path = os.path.join(self._storage_dir, fname)
            try:
                data = None
                for _attempt in range(5):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        break
                    except PermissionError:
                        time.sleep(0.015)
                if data is None:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                if not isinstance(data, dict):
                    continue

                session_id = data.get("session_id", fname[:-5])
                title = data.get("title") or self.DEFAULT_TITLE
                created_at = data.get("created_at", "")
                updated_at = data.get("updated_at") or created_at
                messages = data.get("messages")
                if not isinstance(messages, list):
                    messages = []
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}

                last_msg_snippet = ""
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        content = last_msg.get("content", "")
                    elif hasattr(last_msg, "content"):
                        content = last_msg.content
                    elif isinstance(last_msg, str):
                        content = last_msg
                    else:
                        content = str(last_msg)
                    last_msg_snippet = content[:60] + ("..." if len(content) > 60 else "")

                summaries.append({
                    "session_id": session_id,
                    "title": title,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "message_count": len(messages),
                    "last_message": last_msg_snippet,
                    "metadata": metadata,
                })
            except (json.JSONDecodeError, OSError, UnicodeDecodeError, AttributeError, Exception) as e:
                # Omitir archivos temporales rotos o corruptos
                print(f"[LocalChatHistoryManager] Archivo corrupto ignorado {fname}: {e}")
                continue

        # Ordenar por updated_at más reciente primero
        summaries.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return summaries

    def save_session(self, session: ChatSession) -> bool:
        """Persiste una sesión en el almacenamiento local de forma atómica.

        Args:
            session (ChatSession): Sesión a guardar.

        Returns:
            bool: True si la escritura atómica fue exitosa, False en caso de error.
        """
        self._ensure_storage_dir()
        file_path = self._get_session_path(session.session_id)
        tmp_path = os.path.join(
            self._storage_dir, f".{self._sanitize_session_id(session.session_id)}.{os.getpid()}.tmp"
        )

        try:
            # Serialización en archivo temporal (compacta y con permisos restringidos 0o600)
            data = session.to_dict()
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY

            try:
                fd = os.open(tmp_path, flags, 0o600)
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

            # Reemplazo atómico para evitar corrupción por caídas abruptas
            os.replace(tmp_path, file_path)
            return True
        except (OSError, TypeError, ValueError, AttributeError, Exception) as e:
            print(f"[LocalChatHistoryManager] Error guardando sesión {session.session_id}: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return False

    def delete_session(self, session_id: str) -> bool:
        """Elimina una sesión del almacenamiento local.

        Args:
            session_id (str): Identificador de la sesión a eliminar.

        Returns:
            bool: True si el archivo fue eliminado, False si no existía o falló.
        """
        file_path = self._get_session_path(session_id)
        if not os.path.exists(file_path):
            return False

        try:
            os.remove(file_path)
            return True
        except OSError as e:
            print(f"[LocalChatHistoryManager] Error eliminando sesión {session_id}: {e}")
            return False

    def clear_all_sessions(self) -> bool:
        """Elimina todas las sesiones almacenadas localmente.

        Returns:
            bool: True si todas las sesiones fueron eliminadas exitosamente.
        """
        self._ensure_storage_dir()
        try:
            for fname in os.listdir(self._storage_dir):
                if fname.endswith(".json") or fname.endswith(".tmp"):
                    file_path = os.path.join(self._storage_dir, fname)
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
            return True
        except OSError as e:
            print(f"[LocalChatHistoryManager] Error limpiando sesiones: {e}")
            return False

    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        """Busca sesiones que coincidan en título, contenido de mensajes o metadatos.

        Optimización: Realiza una única lectura y deserialización JSON por archivo en disco,
        evitando lecturas dobles y la instanciación innecesaria de objetos ChatSession.

        Args:
            query (str): Término de búsqueda.

        Returns:
            List[Dict[str, Any]]: Sesiones coincidentes con información de coincidencias.
        """
        if not query or not query.strip():
            return self.list_sessions()

        normalized_query = query.strip().lower()
        results: List[Dict[str, Any]] = []

        self._ensure_storage_dir()
        try:
            filenames = os.listdir(self._storage_dir)
        except OSError as e:
            print(f"[LocalChatHistoryManager] Error listando directorio {self._storage_dir}: {e}")
            return results

        for fname in filenames:
            if not fname.endswith(".json") or fname.startswith("."):
                continue

            file_path = os.path.join(self._storage_dir, fname)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not isinstance(data, dict):
                    continue

                session_id = data.get("session_id", fname[:-5])
                title = data.get("title") or self.DEFAULT_TITLE
                created_at = data.get("created_at", "")
                updated_at = data.get("updated_at") or created_at
                messages = data.get("messages")
                if not isinstance(messages, list):
                    messages = []
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}

                matched = False
                match_snippets: List[str] = []

                # Coincidencia en título
                if normalized_query in title.lower():
                    matched = True
                    match_snippets.append(f"Título: {title}")

                # Coincidencia en metadatos (proveedor, modelo, tags)
                for k, v in metadata.items():
                    if isinstance(v, str) and normalized_query in v.lower():
                        matched = True
                        match_snippets.append(f"Metadatos ({k}): {v}")
                    elif isinstance(v, list):
                        for item_val in v:
                            if isinstance(item_val, str) and normalized_query in item_val.lower():
                                matched = True
                                match_snippets.append(f"Etiqueta: {item_val}")

                # Coincidencia en contenido de mensajes
                for msg in messages:
                    if isinstance(msg, dict):
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                    elif hasattr(msg, "content"):
                        role = getattr(msg, "role", "user")
                        content = msg.content
                    elif isinstance(msg, str):
                        role = "user"
                        content = msg
                    else:
                        role = "user"
                        content = str(msg)

                    msg_content = content if isinstance(content, str) else str(content or "")
                    if normalized_query in msg_content.lower():
                        matched = True
                        snippet = msg_content[:80] + ("..." if len(msg_content) > 80 else "")
                        match_snippets.append(f"[{role}]: {snippet}")

                if matched:
                    last_msg_snippet = ""
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, dict):
                            c_last = last_msg.get("content", "")
                        elif hasattr(last_msg, "content"):
                            c_last = last_msg.content
                        elif isinstance(last_msg, str):
                            c_last = last_msg
                        else:
                            c_last = str(last_msg)
                        last_msg_snippet = c_last[:60] + ("..." if len(c_last) > 60 else "")

                    results.append({
                        "session_id": session_id,
                        "title": title,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "message_count": len(messages),
                        "last_message": last_msg_snippet,
                        "metadata": metadata,
                        "matches": match_snippets,
                    })
            except (json.JSONDecodeError, OSError, UnicodeDecodeError, AttributeError, Exception) as e:
                print(f"[LocalChatHistoryManager] Archivo corrupto ignorado {fname}: {e}")
                continue

        results.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return results

    def export_session_json(self, session_id: str) -> Optional[str]:
        """Exporta una sesión a formato JSON como string.

        Args:
            session_id (str): Identificador de la sesión.

        Returns:
            Optional[str]: Representación JSON formateada o None si no existe.
        """
        session = self.get_session(session_id)
        if not session:
            return None
        return json.dumps(session.to_dict(), ensure_ascii=False)

    def import_session_json(self, json_content: str) -> Optional[ChatSession]:
        """Importa una sesión desde una cadena JSON y la persiste localmente.

        Args:
            json_content (str): Contenido en formato JSON.

        Returns:
            Optional[ChatSession]: Sesión importada o None si el JSON es inválido o excede el límite.
        """
        if not json_content or not isinstance(json_content, str):
            return None

        if len(json_content) > self.MAX_IMPORT_SIZE:
            print(f"[LocalChatHistoryManager] Payload de importación excede el límite máximo de {self.MAX_IMPORT_SIZE} bytes.")
            return None

        try:
            data = json.loads(json_content)
            if not isinstance(data, dict):
                return None

            # Si no tiene session_id o ya existe, asignar uno nuevo para evitar sobreescritura accidental
            session_id = data.get("session_id")
            if session_id:
                sanitized = self._sanitize_session_id(str(session_id))
                if not sanitized or self.get_session(sanitized) is not None:
                    data["session_id"] = uuid.uuid4().hex
                else:
                    data["session_id"] = sanitized
            else:
                data["session_id"] = uuid.uuid4().hex

            session = ChatSession.from_dict(data)
            session.updated_at = self._current_timestamp()
            self.save_session(session)
            return session
        except (json.JSONDecodeError, Exception) as e:
            print(f"[LocalChatHistoryManager] Error importando sesión: {e}")
            return None

    # --- Utilidades de Auto-titulado y Asistencia ---

    @staticmethod
    def generate_title_from_prompt(prompt: str, max_chars: int = 42) -> str:
        """Genera un título descriptivo y conciso a partir del primer prompt del usuario.

        Args:
            prompt (str): Texto del mensaje del usuario.
            max_chars (int): Longitud máxima del título.

        Returns:
            str: Título limpio.
        """
        if not prompt or not isinstance(prompt, str):
            return LocalChatHistoryManager.DEFAULT_TITLE

        cleaned = prompt.replace("\n", " ").replace("\r", " ").strip()
        # Eliminar bloques de código markdown iniciales y vallas de código
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return LocalChatHistoryManager.DEFAULT_TITLE
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars].rstrip() + "..."
