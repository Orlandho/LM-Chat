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

from core.interfaces import IChatView
from ui.models import ChatModel

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

    def set_submit_callback(self, callback: Callable[[str], Any]) -> None:
        """Establece el callback de envío.

        Args:
            callback (Callable[[str], Any]): Función a invocar.
        """
        self._submit_callback = callback

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

        # Configuración de la ventana anclable nativa omni.ui
        dock_pref = getattr(ui.DockPreference, "RIGHT_BOTTOM", 0)
        self._window = ui.Window("IA Agent Chat", width=850, height=650, dock_preference=dock_pref)

        self._model.subscribe(self._on_model_updated)
        self._build_ui()

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
        """Renderiza el encabezado con selectores de Proveedor, Modelo y Badge de Estado."""
        with ui.HStack(height=45, style={"background_color": 0xFF2A2A2A}, padding=8, spacing=10):
            # Selector de Proveedor
            ui.Label("Proveedor:", width=70, style={"color": 0xFFCCCCCC, "font_size": 13})
            self._provider_combo = ui.ComboBox(0, *self._model.providers, width=130, height=26)
            self._provider_combo.model.add_item_changed_fn(self._on_provider_selection_changed)

            ui.Spacer(width=10)

            # Selector de Modelo
            ui.Label("Modelo:", width=55, style={"color": 0xFFCCCCCC, "font_size": 13})
            self._model_combo = ui.ComboBox(0, *self._model.available_models, width=200, height=26)
            self._model_combo.model.add_item_changed_fn(self._on_model_selection_changed)

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
        try:
            val_idx = item_model.get_item_value_model().as_int
            providers = self._model.providers
            if 0 <= val_idx < len(providers):
                new_provider = providers[val_idx]
                self._delegate.on_provider_changed(new_provider)
        except Exception:
            pass

    def _on_model_selection_changed(self, item_model, item) -> None:
        """Maneja el cambio en el selector desplegable de modelos."""
        try:
            val_idx = item_model.get_item_value_model().as_int
            models = self._model.available_models
            if 0 <= val_idx < len(models):
                new_model = models[val_idx]
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

    def _on_model_updated(self) -> None:
        """Notificación cuando el modelo subyacente cambia de estado."""
        self._update_status_badge_ui(self._model.status, self._model.is_loading)

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
        """Crea una nueva burbuja de mensaje con formato diferenciado (Usuario vs Agente).

        Args:
            role (str): Rol del emisor ("user", "assistant", "system").
            text (str): Texto inicial de la burbuja.
        """
        is_user = (role == "user")
        bg_color = 0xFF2B5278 if is_user else 0xFF3A3A3A  # Colores nativos especificados
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

                            # Burbuja Principal (ZStack con bordes redondeados)
                            with ui.ZStack(width=0):
                                ui.Rectangle(style={"background_color": bg_color, "border_radius": 8})
                                with ui.VStack(padding=12, height=0, spacing=6):
                                    # Etiqueta con el rol
                                    role_title = "Usuario" if is_user else ("Agente IA" if role == "assistant" else "Sistema")
                                    ui.Label(
                                        role_title,
                                        style={"color": 0xFF88C0D0 if is_user else 0xFFA3BE8C, "font_size": 11, "font_weight": "bold"}
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
                                with ui.VStack(width=60):
                                    ui.Spacer()
                                    btn = ui.Button(
                                        "Copiar",
                                        width=60, height=22,
                                        style={"font_size": 12, "background_color": 0xFF444444}
                                    )

                            btn.set_clicked_fn(lambda t=text: self._copy_to_clipboard(t))

                        if not is_user:
                            ui.Spacer()

                if not is_user:
                    ui.Spacer(width=margin_fraction)

        self._scroll_to_bottom()

    def append_to_last_message(self, chunk: str) -> None:
        """Agrega texto progresivamente a la última burbuja del asistente (Streaming).

        Args:
            chunk (str): Fragmento de texto recibido del flujo asíncrono.
        """
        if self._message_labels:
            last_label = self._message_labels[-1]
            if hasattr(last_label, "text"):
                last_label.text += chunk
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
        self._window = None
