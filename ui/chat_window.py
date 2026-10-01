# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
GUI Primaria Nativa construida con omni.ui (NVIDIA Omniverse Kit SDK).
Implementa la interfaz IChatView aplicando la arquitectura desacoplada Model-Delegate-View (MDV).
"""

import asyncio
import re
from typing import Callable, Any, Optional, List, Dict, Tuple
import omni.ui as ui
import omni.appwindow

from core.interfaces import IChatView, ChatSession
from ui.models import ChatModel
from logic.logger import get_logger

logger = get_logger("ChatWindow")

# Pre-compiled regular expression pattern for Markdown code block parsing
_MARKDOWN_CODE_PATTERN = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)


class ChatDelegate:
    """Delegado para interceptar eventos y desacoplar la vista del modelo (MDV Architecture)."""

    def __init__(self, model: ChatModel, submit_callback: Optional[Callable[[str], Any]] = None) -> None:
        """Inicializa el delegado.

        Args:
            model (ChatModel): Instancia del modelo de chat.
            submit_callback (Optional[Callable[[str], Any]]): Callback al enviar mensajes.
        """
        self._model = model
        self._submit_callback = submit_callback
        self._session_changed_callback: Optional[Callable[[ChatSession], Any]] = None

    def set_submit_callback(self, callback: Callable[[str], Any]) -> None:
        """Establece el callback de envío.

        Args:
            callback (Callable[[str], Any]): Función a invocar.
        """
        self._submit_callback = callback

    def set_session_changed_callback(self, callback: Callable[[ChatSession], Any]) -> None:
        """Establece el callback al cambiar o cargar una sesión.

        Args:
            callback (Callable[[ChatSession], Any]): Función a invocar con la sesión activa.
        """
        self._session_changed_callback = callback

    def on_submit(self, text: str) -> None:
        """Interpreta el evento de envío desde la vista.

        Args:
            text (str): Texto ingresado por el usuario.
        """
        cleaned_text = text.strip() if text else ""
        if not cleaned_text:
            return

        # Registrar en el modelo
        self._model.add_message("user", cleaned_text)
        self._model.set_status("Generando...", is_loading=True)

        if self._submit_callback:
            try:
                self._submit_callback(cleaned_text)
            except Exception as e:
                print(f"[ChatDelegate] Error al ejecutar submit callback: {e}")

    def on_provider_changed(self, provider_name: str) -> None:
        """Maneja el cambio de proveedor de inferencia.

        Args:
            provider_name (str): Nombre del proveedor seleccionado.
        """
        self._model.set_provider(provider_name)

    def on_model_changed(self, model_name: str) -> None:
        """Maneja el cambio de modelo de LLM.

        Args:
            model_name (str): Nombre del modelo seleccionado.
        """
        self._model.set_model(model_name)

    def on_new_session(self, title: Optional[str] = None) -> ChatSession:
        """Inicia una nueva sesión de chat persistente.

        Args:
            title (Optional[str]): Título opcional.

        Returns:
            ChatSession: Nueva sesión creada.
        """
        session = self._model.new_session(title=title)
        if self._session_changed_callback:
            try:
                self._session_changed_callback(session)
            except Exception as e:
                print(f"[ChatDelegate] Error en session_changed_callback: {e}")
        return session

    def on_session_changed(self, session_id: str) -> bool:
        """Carga una sesión existente desde el historial local.

        Args:
            session_id (str): Identificador de la sesión.

        Returns:
            bool: True si la sesión se cargó con éxito.
        """
        success = self._model.load_session(session_id)
        if success and self._session_changed_callback and self._model.current_session:
            try:
                self._session_changed_callback(self._model.current_session)
            except Exception as e:
                print(f"[ChatDelegate] Error en session_changed_callback: {e}")
        return success

    def on_delete_session(self, session_id: Optional[str] = None) -> bool:
        """Elimina una sesión del historial y genera una nueva sesión activa.

        Args:
            session_id (Optional[str]): Identificador de la sesión a eliminar.

        Returns:
            bool: True si se eliminó con éxito.
        """
        sid = session_id or self._model.current_session_id
        if not sid:
            return False
        is_active = (self._model.current_session_id == sid)
        success = self._model.delete_session(sid)
        if success and is_active:
            sessions = self._model.sessions
            if sessions:
                self._model.load_session(sessions[0]["session_id"])
            else:
                self._model.new_session()
            if self._session_changed_callback and self._model.current_session:
                try:
                    self._session_changed_callback(self._model.current_session)
                except Exception as e:
                    print(f"[ChatDelegate] Error en session_changed_callback: {e}")
        return success

    def on_clear_current_session(self) -> None:
        """Limpia los mensajes de la sesión actual."""
        self._model.clear_messages()
        if self._session_changed_callback and self._model.current_session:
            try:
                self._session_changed_callback(self._model.current_session)
            except Exception as e:
                print(f"[ChatDelegate] Error en session_changed_callback: {e}")



class ChatWindow(IChatView):
    """Ventana principal de Chat y Control del Agente en omni.ui (IChatView)."""

    def __init__(
        self,
        on_send_callback: Optional[Callable[[str], Any]] = None,
        model: Optional[ChatModel] = None,
    ) -> None:
        """Inicializa la ventana de chat omni.ui.

        Args:
            on_send_callback (Optional[Callable[[str], Any]]): Callback retrocompatible al enviar mensajes.
            model (Optional[ChatModel]): Modelo de datos opcional (creado automáticamente si es None).
        """
        self._model = model if model is not None else ChatModel()
        self._delegate = ChatDelegate(self._model, submit_callback=on_send_callback)

        self._message_labels: List[ui.Label] = []
        self._last_assistant_bubble_components: Optional[Dict[str, Any]] = None
        self._settings_window: Optional[Any] = None

        # Configuración de la ventana anclable nativa omni.ui
        dock_pref = getattr(ui.DockPreference, "RIGHT_BOTTOM", 0)
        self._window = ui.Window("LM-Chat", width=850, height=650, dock_preference=dock_pref)

        self._model.subscribe(self._on_model_updated)

        self._build_ui()

    @property
    def model(self) -> ChatModel:
        """Acceso al modelo de datos subyacente."""
        return self._model

    @property
    def delegate(self) -> ChatDelegate:
        """Acceso al delegado de eventos."""
        return self._delegate

    def set_session_changed_callback(self, callback: Callable[[ChatSession], Any]) -> None:
        """Registra el callback de cambio o recarga de sesión."""
        self._delegate.set_session_changed_callback(callback)

    def rebuild_messages_ui(self) -> None:
        """Reconstruye las burbujas visuales en el scroll frame según los mensajes del modelo."""
        self._message_labels.clear()
        if hasattr(self, "_messages_stack") and self._messages_stack:
            try:
                self._messages_stack.clear()
            except Exception:
                pass
            for msg in self._model.messages:
                self.add_message_bubble(msg.role, msg.content)
        self._scroll_to_bottom()

    def finalize_last_assistant_message(self, full_text: Optional[str] = None) -> None:
        """Sincroniza y persiste el mensaje final del asistente en el modelo y almacenamiento local."""
        if full_text is None and self._message_labels:
            last_label = self._message_labels[-1]
            if hasattr(last_label, "text"):
                full_text = last_label.text

        if full_text:
            if (
                not self._model.messages
                or self._model.messages[-1].role != "assistant"
                or self._model.messages[-1].content != full_text
            ):
                self._model.add_message("assistant", full_text)

    # --- Implementación de IChatView ---

    def set_submit_callback(self, callback: Callable[[str], Any]) -> None:
        """Establece la función a invocar al enviar un mensaje.

        Args:
            callback (Callable[[str], Any]): Función a invocar.
        """
        self._delegate.set_submit_callback(callback)

    def append_message(self, role: str, message: str) -> None:
        """Agrega un mensaje a la conversación en el hilo de UI.

        Args:
            role (str): Rol del mensaje ("user", "assistant", "system").
            message (str): Contenido del mensaje.
        """
        if role == "assistant" and self._message_labels and self._model.is_loading:
            # Si se está en modo streaming / generando, actualiza el último mensaje del asistente
            self.append_to_last_message(message)
        else:
            self._model.add_message(role, message)
            self.add_message_bubble(role, message)

    def update_status(self, status: str, is_loading: bool = False) -> None:
        """Actualiza el badge de estado en la UI.

        Args:
            status (str): Texto de estado ("Listo", "Generando...", "Auto-corrigiendo").
            is_loading (bool): Si la interfaz se encuentra procesando una solicitud.
        """
        self._model.set_status(status, is_loading=is_loading)
        self.set_button_state(processing=is_loading)
        self._update_status_badge_ui(status, is_loading)

    # --- Construcción y Renderizado de la UI ---

    def _build_ui(self) -> None:
        """Construye la jerarquía visual nativa de omni.ui."""
        with self._window.frame:
            with ui.VStack(spacing=0):
                # Encabezado (Barra Superior de Control y Badges)
                self._build_header()

                # Separador horizontal
                ui.Rectangle(height=1, style={"background_color": 0xFF333333})

                # Barra de Sesiones e Historial Local
                self._build_session_bar()

                # Separador horizontal
                ui.Rectangle(height=1, style={"background_color": 0xFF333333})

                # Área principal de Scroll para el Historial de Mensajes
                self._scrolling_frame = ui.ScrollingFrame(
                    height=ui.Fraction(1),
                    style={"background_color": 0xFF1E1E1E},
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                )
                with self._scrolling_frame:
                    self._messages_stack = ui.VStack(spacing=12, padding=12)

                # Separador horizontal
                ui.Rectangle(height=1, style={"background_color": 0xFF333333})

                # Área Inferior de Entrada de Texto Multilínea y Acciones
                self._build_input_area()

    def _build_header(self) -> None:
        """Renderiza el encabezado con selectores de Proveedor, Modelo, Botón de Settings y Badge de Estado."""
        with ui.HStack(height=45, style={"background_color": 0xFF2A2A2A}, padding=8, spacing=8):
            # Selector de Proveedor
            ui.Label("Proveedor:", width=68, style={"color": 0xFFCCCCCC, "font_size": 13})
            self._provider_combo_frame = ui.Frame(width=130, height=26)
            self._rebuild_provider_combo()

            ui.Spacer(width=6)

            # Selector de Modelo (dinámico)
            ui.Label("Modelo:", width=52, style={"color": 0xFFCCCCCC, "font_size": 13})
            self._model_combo_frame = ui.Frame(width=180, height=26)
            self._rebuild_model_combo()

            ui.Spacer(width=6)

            # Botón de Configuración / Settings
            self._settings_button = ui.Button(
                "⚙ Settings",
                width=85,
                height=26,
                style={"background_color": 0xFF383838, "border_radius": 4, "font_size": 11},
                clicked_fn=self._open_settings_dialog,
            )

            ui.Spacer()

            # Dynamic Status Badge
            with ui.HStack(width=0, spacing=4):
                ui.Label("Estado:", width=50, style={"color": 0xFFAAAAAA, "font_size": 12})
                with ui.ZStack(width=130, height=24):
                    self._status_badge_bg = ui.Rectangle(
                        style={"background_color": 0xFF2E7D32, "border_radius": 12}
                    )
                    self._status_badge_label = ui.Label(
                        self._model.status,
                        alignment=ui.Alignment.CENTER,
                        style={"color": 0xFFFFFFFF, "font_size": 12, "font_weight": "bold"}
                    )

    def _rebuild_provider_combo(self) -> None:
        """Reconstruye el selector de proveedores según la lista activa."""
        if not hasattr(self, "_provider_combo_frame") or not self._provider_combo_frame:
            return

        providers = self._model.providers
        current_prov = self._model.current_provider
        active_idx = 0
        for idx, p in enumerate(providers):
            if p == current_prov:
                active_idx = idx
                break

        self._is_updating_provider_combo = True
        try:
            self._provider_combo_frame.clear()
            with self._provider_combo_frame:
                self._provider_combo = ui.ComboBox(active_idx, *providers, width=130, height=26)
                self._provider_combo.model.add_item_changed_fn(self._on_provider_selection_changed)
        finally:
            self._is_updating_provider_combo = False

    def _open_settings_dialog(self) -> None:
        """Abre la ventana modal de configuración de servicios y modelos."""
        if not hasattr(self, "_settings_window") or self._settings_window is None:
            from ui.settings_window import SettingsWindow
            self._settings_window = SettingsWindow(
                settings_manager=getattr(self._model, "settings_manager", None),
                on_save_callback=self._on_settings_saved,
            )
        self._settings_window.show()

    def _on_settings_saved(self, default_provider: str, default_model: str) -> None:
        """Callback al guardar ajustes en SettingsWindow."""
        self._model.set_provider(default_provider)
        self._model.set_model(default_model)
        self._rebuild_provider_combo()
        self._rebuild_model_combo()

    def _rebuild_model_combo(self) -> None:
        """Reconstruye el selector de modelos según el proveedor activo."""
        if not hasattr(self, "_model_combo_frame") or not self._model_combo_frame:
            return

        models = self._model.available_models
        current_model = self._model.current_model
        active_idx = 0
        for idx, m in enumerate(models):
            if m == current_model:
                active_idx = idx
                break

        self._is_updating_model_combo = True
        try:
            self._model_combo_frame.clear()
            with self._model_combo_frame:
                self._model_combo = ui.ComboBox(active_idx, *models, width=180, height=26)
                self._model_combo.model.add_item_changed_fn(self._on_model_selection_changed)
        finally:
            self._is_updating_model_combo = False


    def _build_session_bar(self) -> None:
        """Renderiza la barra de control de sesiones y selector de historial local."""
        with ui.HStack(height=36, style={"background_color": 0xFF222222}, padding=6, spacing=8):
            ui.Label("Historial:", width=55, style={"color": 0xFFCCCCCC, "font_size": 12, "font_weight": "bold"})

            self._session_combo_frame = ui.Frame(width=ui.Fraction(1), height=24)
            self._rebuild_session_combo()

            self._new_session_btn = ui.Button(
                "+ Nuevo",
                width=68,
                height=24,
                style={"background_color": 0xFF007ACC, "border_radius": 4, "font_size": 11},
                clicked_fn=self._handle_new_session_clicked,
            )

            self._delete_session_btn = ui.Button(
                "Eliminar",
                width=62,
                height=24,
                style={"background_color": 0xFF883333, "border_radius": 4, "font_size": 11},
                clicked_fn=self._handle_delete_session_clicked,
            )

            self._clear_session_btn = ui.Button(
                "Limpiar",
                width=58,
                height=24,
                style={"background_color": 0xFF444444, "border_radius": 4, "font_size": 11},
                clicked_fn=self._handle_clear_session_clicked,
            )

    def _rebuild_session_combo(self) -> None:
        """Reconstruye el ComboBox de sesiones con los títulos y conteo actualizados."""
        if not hasattr(self, "_session_combo_frame") or not self._session_combo_frame:
            return

        sessions = self._model.sessions
        current_id = self._model.current_session_id
        active_idx = 0

        session_titles: List[str] = []
        if not sessions:
            session_titles = ["(Nueva Conversación)"]
        else:
            for idx, s in enumerate(sessions):
                title = s.get("title", "Conversación")
                count = s.get("message_count", 0)
                session_titles.append(f"{title} ({count})")
                if s.get("session_id") == current_id:
                    active_idx = idx

        self._is_updating_session_combo = True
        try:
            self._session_combo_frame.clear()
            with self._session_combo_frame:
                self._session_combo = ui.ComboBox(active_idx, *session_titles, width=ui.Fraction(1), height=24)
                self._session_combo.model.add_item_changed_fn(self._on_session_selection_changed)
        finally:
            self._is_updating_session_combo = False

    def _build_input_area(self) -> None:
        """Renderiza la zona de entrada multilínea con atajo Ctrl + Enter y botón Enviar."""
        with ui.HStack(height=85, style={"background_color": 0xFF252525}, padding=10, spacing=10):
            # Campo de entrada multilínea
            self._input_field = ui.StringField(
                multiline=True,
                height=65,
                width=ui.Fraction(1),
                style={"word_wrap": True, "background_color": 0xFF141414, "border_radius": 6}
            )
            self._input_field.model.set_value("")

            # Subscribir evento de modificación / teclado para Ctrl+Enter
            self._input_field.model.add_value_changed_fn(self._on_input_value_changed)

            # Botón Enviar
            with ui.VStack(width=100):
                ui.Spacer()
                self._send_button = ui.Button(
                    "Enviar",
                    width=100,
                    height=45,
                    style={"background_color": 0xFF007ACC, "border_radius": 6},
                    clicked_fn=self._handle_send_clicked
                )
                ui.Spacer()

    # --- Manejo de Eventos y Callbacks ---

    def _on_provider_selection_changed(self, item_model, item) -> None:
        """Maneja el cambio en el selector desplegable de proveedores."""
        if getattr(self, "_is_updating_provider_combo", False):
            return
        try:
            val_idx = item_model.get_item_value_model().as_int
            providers = self._model.providers
            if 0 <= val_idx < len(providers):
                new_provider = providers[val_idx]
                if new_provider != self._model.current_provider:
                    self._delegate.on_provider_changed(new_provider)
        except Exception:
            pass

    def _on_model_selection_changed(self, item_model, item) -> None:
        """Maneja el cambio en el selector desplegable de modelos."""
        if getattr(self, "_is_updating_model_combo", False):
            return
        try:
            val_idx = item_model.get_item_value_model().as_int
            models = self._model.available_models
            if 0 <= val_idx < len(models):
                new_model = models[val_idx]
                if new_model != self._model.current_model:
                    self._delegate.on_model_changed(new_model)
        except Exception:
            pass

    def _on_input_value_changed(self, value_model) -> None:
        """Detecta atajo de teclado Ctrl + Enter en la entrada multilínea."""
        val = value_model.as_string
        if val and val.endswith("\n") and ("\r\n" in val or val.count("\n") > 1 or getattr(self, "_ctrl_pressed", False)):
            # Atajo de teclado (o Enter intencional si está configurado)
            pass

    def _handle_send_clicked(self) -> None:
        """Callback interno para el botón Enviar."""
        prompt = self._input_field.model.get_value_as_string()
        if prompt and prompt.strip():
            self._input_field.model.set_value("")
            self._delegate.on_submit(prompt)

    def _handle_new_session_clicked(self) -> None:
        """Acción para iniciar una nueva sesión de chat limpia."""
        self._delegate.on_new_session()
        self.rebuild_messages_ui()

    def _handle_delete_session_clicked(self) -> None:
        """Acción para eliminar la sesión de chat actual."""
        self._delegate.on_delete_session()
        self.rebuild_messages_ui()

    def _handle_clear_session_clicked(self) -> None:
        """Acción para limpiar los mensajes de la sesión actual."""
        self._delegate.on_clear_current_session()
        self.rebuild_messages_ui()

    def _on_session_selection_changed(self, item_model, item) -> None:
        """Maneja la selección de una sesión en el desplegable de historial."""
        if getattr(self, "_is_updating_session_combo", False):
            return
        try:
            val_idx = item_model.get_item_value_model().as_int
            sessions = self._model.sessions
            if 0 <= val_idx < len(sessions):
                target_id = sessions[val_idx]["session_id"]
                if target_id != self._model.current_session_id:
                    self._delegate.on_session_changed(target_id)
                    self.rebuild_messages_ui()
        except Exception:
            pass

    def _on_model_updated(self) -> None:
        """Notificación cuando el modelo subyacente cambia de estado."""
        self._update_status_badge_ui(self._model.status, self._model.is_loading)
        self._rebuild_session_combo()
        self._rebuild_provider_combo()
        self._rebuild_model_combo()

    def _update_status_badge_ui(self, status: str, is_loading: bool) -> None:
        """Actualiza los estilos visuales del badge de estado en el hilo principal."""
        try:
            if hasattr(self, "_status_badge_label") and self._status_badge_label:
                self._status_badge_label.text = status

            # Color dinámico del badge según el estado
            bg_color = 0xFF2E7D32  # Verde (Listo por defecto)
            if "Generando" in status:
                bg_color = 0xFF0277BD  # Azul activo
            elif "corrigiendo" in status.lower() or "error" in status.lower():
                bg_color = 0xFFC62828  # Rojo / Púrpura corrección

            if hasattr(self, "_status_badge_bg") and self._status_badge_bg:
                self._status_badge_bg.style = {"background_color": bg_color, "border_radius": 12}
        except Exception as e:
            print(f"[ChatWindow] Error actualizando badge: {e}")

    # --- Renderizado de Mensajes y Markdown ---

    def _parse_markdown(self, text: str) -> List[Tuple[str, str]]:
        """Divide el texto en bloques de texto normal y bloques de código Markdown.

        Args:
            text (str): Mensaje con formato Markdown.

        Returns:
            List[Tuple[str, str]]: Lista de tuplas `(tipo, contenido)` donde tipo es 'text' o 'code'.
        """
        blocks: List[Tuple[str, str]] = []
        last_end = 0

        # Optimization: Use pre-compiled module-level regex pattern
        for match in _MARKDOWN_CODE_PATTERN.finditer(text):
            start, end = match.span()
            if start > last_end:
                plain_text = text[last_end:start]
                if plain_text:
                    blocks.append(("text", plain_text))

            lang = match.group(1).strip() or "python"
            code_content = match.group(2)
            blocks.append(("code", f"[{lang}]\n{code_content}"))
            last_end = end

        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                blocks.append(("text", remaining))

        return blocks if blocks else [("text", text)]

    def add_message_bubble(self, role: str, text: str = "") -> None:
        """Crea una nueva burbuja de mensaje con formato diferenciado (Usuario vs Agente vs Diagnóstico).

        Args:
            role (str): Rol del emisor ("user", "assistant", "system").
            text (str): Texto inicial de la burbuja.
        """
        is_user = (role == "user")
        is_diagnostic = ("Diagnóstico LM-Chat" in text or "Diagnóstico de Conexión" in text or text.strip().startswith("### ⚠️ Diagnóstico"))

        if is_user:
            bg_color = 0xFF2B5278
        elif is_diagnostic:
            bg_color = 0xFF2D1616  # Alerta carmesí para diagnósticos
        else:
            bg_color = 0xFF3A3A3A  # Colores nativos especificados

        margin_fraction = ui.Fraction(1)
        bubble_fraction = ui.Fraction(4)

        with self._messages_stack:
            with ui.HStack(height=0):
                if is_user:
                    ui.Spacer(width=margin_fraction)

                with ui.VStack(width=bubble_fraction):
                    with ui.HStack(height=0):
                        if is_user:
                            ui.Spacer()

                        with ui.HStack(width=0, spacing=6):
                            if is_user:
                                with ui.VStack(width=60):
                                    ui.Spacer()
                                    btn = ui.Button(
                                        "Copiar",
                                        width=60, height=22,
                                        style={"font_size": 12, "background_color": 0xFF444444}
                                    )
                                    btn.set_clicked_fn(lambda t=text: self._copy_to_clipboard(t))

                            # Burbuja Principal (ZStack con bordes redondeados)
                            with ui.ZStack(width=0):
                                bg_rect = ui.Rectangle(style={"background_color": bg_color, "border_radius": 8})
                                with ui.VStack(padding=12, height=0, spacing=6):
                                    # Etiqueta con el rol y badges
                                    if is_user:
                                        role_title = "Usuario"
                                        role_color = 0xFF88C0D0
                                    elif is_diagnostic:
                                        role_title = "⚠️ DIAGNÓSTICO DEL SISTEMA"
                                        role_color = 0xFFFF6B6B
                                    elif role == "assistant":
                                        role_title = "Agente IA"
                                        role_color = 0xFFA3BE8C
                                    else:
                                        role_title = "Sistema"
                                        role_color = 0xFFA3BE8C

                                    role_label = ui.Label(
                                        role_title,
                                        style={"color": role_color, "font_size": 11, "font_weight": "bold"}
                                    )

                                    # Contenido parsed (Texto + Código Markdown)
                                    parsed_blocks = self._parse_markdown(text)
                                    label_ref = None
                                    for block_type, content in parsed_blocks:
                                        if block_type == "code":
                                            # Bloque visual de código resaltado
                                            with ui.ZStack(width=0):
                                                ui.Rectangle(style={"background_color": 0xFF141414, "border_radius": 6})
                                                with ui.VStack(padding=8, spacing=4):
                                                    code_label = ui.Label(
                                                        content,
                                                        word_wrap=True,
                                                        style={"color": 0xFFD8DEE9, "font_size": 13, "font_family": "monospace"}
                                                    )
                                                    if not is_user:
                                                        label_ref = code_label
                                        else:
                                            # Texto llano
                                            text_label = ui.Label(
                                                content,
                                                word_wrap=True,
                                                alignment=ui.Alignment.LEFT_TOP,
                                                style={"color": 0xFFFFFFFF, "font_size": 14}
                                            )
                                            if not is_user:
                                                label_ref = text_label

                                    if not is_user and label_ref:
                                        self._message_labels.append(label_ref)

                            if not is_user:
                                with ui.VStack(width=90 if is_diagnostic else 60) as action_col:
                                    ui.Spacer()
                                    settings_btn = None
                                    if is_diagnostic:
                                        settings_btn = ui.Button(
                                            "⚙ Settings",
                                            width=85, height=22,
                                            style={"font_size": 11, "background_color": 0xFF007ACC, "border_radius": 3},
                                            clicked_fn=self._open_settings_dialog,
                                        )
                                        ui.Spacer(height=4)
                                    btn = ui.Button(
                                        "Copiar",
                                        width=85 if is_diagnostic else 60, height=22,
                                        style={"font_size": 11 if is_diagnostic else 12, "background_color": 0xFF444444, "border_radius": 3},
                                    )
                                    # Dynamically read current text of the bubble at click time so streamed text is copied
                                    btn.set_clicked_fn(lambda lbl=label_ref, t=text: self._copy_to_clipboard(getattr(lbl, "text", "") or t))

                                # Store components of the active assistant bubble for dynamic upgrade if error occurs
                                self._last_assistant_bubble_components = {
                                    "bg_rect": bg_rect,
                                    "role_label": role_label,
                                    "label_ref": label_ref,
                                    "action_col": action_col,
                                    "settings_btn": settings_btn,
                                    "copy_btn": btn,
                                }

                        if not is_user:
                            ui.Spacer()

                if not is_user:
                    ui.Spacer(width=margin_fraction)

        self._scroll_to_bottom()

    def _upgrade_last_bubble_to_diagnostic(self) -> None:
        """Transforma dinámicamente la última burbuja del asistente en una tarjeta visual de diagnóstico."""
        comps = self._last_assistant_bubble_components
        if not comps:
            return
        try:
            bg_rect = comps.get("bg_rect")
            if bg_rect and hasattr(bg_rect, "style"):
                bg_rect.style = {"background_color": 0xFF2D1616, "border_radius": 8}

            role_lbl = comps.get("role_label")
            if role_lbl:
                if hasattr(role_lbl, "text"):
                    role_lbl.text = "⚠️ DIAGNÓSTICO DEL SISTEMA"
                if hasattr(role_lbl, "style"):
                    role_lbl.style = {"color": 0xFFFF6B6B, "font_size": 11, "font_weight": "bold"}

            action_col = comps.get("action_col")
            settings_btn = comps.get("settings_btn")
            if action_col and not settings_btn:
                with action_col:
                    new_btn = ui.Button(
                        "⚙ Settings",
                        width=85, height=22,
                        style={"font_size": 11, "background_color": 0xFF007ACC, "border_radius": 3},
                        clicked_fn=self._open_settings_dialog,
                    )
                    comps["settings_btn"] = new_btn
            elif settings_btn and hasattr(settings_btn, "visible"):
                settings_btn.visible = True

            copy_btn = comps.get("copy_btn")
            if copy_btn and hasattr(copy_btn, "style"):
                copy_btn.style = {"font_size": 11, "background_color": 0xFF444444, "border_radius": 3}
                copy_btn.width = 85
        except Exception as e:
            print(f"[ChatWindow] Error actualizando burbuja a diagnóstico: {e}")

    def append_to_last_message(self, chunk: str) -> None:
        """Agrega texto progresivamente a la última burbuja del asistente (Streaming).

        Args:
            chunk (str): Fragmento de texto recibido del flujo asíncrono.
        """
        if self._message_labels:
            last_label = self._message_labels[-1]
            if hasattr(last_label, "text"):
                last_label.text += chunk
                current_text = str(last_label.text)
                if ("Diagnóstico LM-Chat" in current_text or "Diagnóstico de Conexión" in current_text or current_text.strip().startswith("### ⚠️ Diagnóstico")):
                    self._upgrade_last_bubble_to_diagnostic()
            self._scroll_to_bottom()

    def set_button_state(self, processing: bool) -> None:
        """Alterna el estado del botón enviar.

        Args:
            processing (bool): Si es True, deshabilita el botón y cambia el texto a 'Procesando...'.
        """
        try:
            if hasattr(self, "_send_button") and self._send_button:
                if processing:
                    self._send_button.text = "Procesando..."
                    self._send_button.enabled = False
                else:
                    self._send_button.text = "Enviar"
                    self._send_button.enabled = True
        except Exception as e:
            print(f"[ChatWindow] Error actualizando estado de botón: {e}")

    def _copy_to_clipboard(self, text: str) -> None:
        """Copia el texto al portapapeles del sistema.

        Args:
            text (str): Texto a copiar.
        """
        try:
            app_window = omni.appwindow.get_default_app_window()
            if app_window and hasattr(app_window, "set_clipboard"):
                app_window.set_clipboard(text)
        except Exception as e:
            print(f"[ChatWindow] Error copiando al portapapeles: {e}")

    def _scroll_to_bottom(self) -> None:
        """Fuerza el ScrollingFrame a desplazarse hasta el fondo."""
        async def scroll_down():
            await asyncio.sleep(0.01)
            try:
                if hasattr(self, "_scrolling_frame") and self._scrolling_frame:
                    self._scrolling_frame.scroll_y_max = 1000000.0
                    self._scrolling_frame.scroll_y = self._scrolling_frame.scroll_y_max
            except Exception:
                pass

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(scroll_down())
        except Exception:
            pass

    def destroy(self) -> None:
        """Limpia referencias y destruye la ventana."""
        if self._model:
            self._model.unsubscribe(self._on_model_updated)
        if hasattr(self, "_settings_window") and self._settings_window:
            self._settings_window.destroy()
            self._settings_window = None
        self._window = None

