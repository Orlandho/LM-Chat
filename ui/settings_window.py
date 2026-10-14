# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
Ventana de Configuración de Servicios y Modelos para LM-Chat™ (omni.ui).

Permite al usuario seleccionar el servicio predeterminado (OpenAI, Claude, Ollama,
LM Studio, NVIDIA Spark, Google Gemini), el modelo predeterminado, configurar URLs con presets de 1 clic,
ingresar credenciales y verificar conectividad en tiempo real.
"""

import asyncio
from typing import Optional, Callable, Dict, Any, List
import omni.ui as ui

from core.interfaces import ISettingsManager
from logic.settings_manager import SettingsManager
from logic.logger import get_logger

logger = get_logger("SettingsWindow")


class SettingsWindow:
    """Ventana modal y panel de configuración gráfica omni.ui para LM-Chat™."""

    def __init__(
        self,
        settings_manager: Optional[ISettingsManager] = None,
        on_save_callback: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        """Inicializa la ventana de configuración.

        Args:
            settings_manager (Optional[ISettingsManager]): Instancia de gestión de configuración.
            on_save_callback (Optional[Callable[[str, str], Any]]): Callback al guardar (provider, model).
        """
        self._settings_manager: ISettingsManager = (
            settings_manager if settings_manager is not None else SettingsManager()
        )
        self._on_save_callback = on_save_callback

        self._providers = self._settings_manager.get_all_providers()
        self._selected_provider = self._settings_manager.get_default_provider()
        if self._selected_provider not in self._providers and self._providers:
            self._selected_provider = self._providers[0]

        self._selected_model = self._settings_manager.get_default_model(self._selected_provider)
        self._is_default_provider = True
        self._discover_task: Optional[Any] = None

        self._window = ui.Window(
            "LM-Chat - Configuración de Servicios y Modelos",
            width=650,
            height=580,
            visible=True,
        )

        self._build_ui()

    @property
    def window(self) -> ui.Window:
        """Referencia a la ventana nativa omni.ui."""
        return self._window

    @property
    def selected_provider(self) -> str:
        """Proveedor actualmente en edición."""
        return self._selected_provider

    @property
    def selected_model(self) -> str:
        """Modelo actualmente seleccionado."""
        return self._selected_model

    def show(self) -> None:
        """Muestra y enfoca la ventana de configuración."""
        if self._window:
            self._window.visible = True

    def hide(self) -> None:
        """Oculta la ventana de configuración."""
        if self._window:
            self._window.visible = False

    def destroy(self) -> None:
        """Destruye los recursos de la ventana."""
        if hasattr(self, "_discover_task") and self._discover_task and not self._discover_task.done():
            self._discover_task.cancel()
        if self._window:
            self._window.destroy()
            self._window = None

    def _build_ui(self) -> None:
        """Construye la interfaz de configuración en la ventana omni.ui."""
        with self._window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                style={"background_color": 0xFF222222},
            ):
                with ui.VStack(spacing=12, padding=16):
                    # --- Título y Encabezado ---
                    with ui.VStack(spacing=4):
                        ui.Label(
                            "Configuración de Servicios de Inferencia & Modelos",
                            style={"font_size": 16, "font_weight": "bold", "color": 0xFF00B4D8},
                        )
                        ui.Label(
                            "Configura OpenAI API, Claude API, Ollama, LM Studio, NVIDIA Spark y Google Gemini con presets de 1 clic.",
                            style={"font_size": 12, "color": 0xFFAAAAAA},
                        )

                    ui.Rectangle(height=1, style={"background_color": 0xFF444444})

                    # --- Selección de Servicio a Configurar ---
                    with ui.VStack(spacing=6):
                        ui.Label(
                            "1. Seleccionar Servicio / Proveedor:",
                            style={"font_size": 13, "font_weight": "bold", "color": 0xFFE0E0E0},
                        )
                        with ui.HStack(height=28, spacing=8):
                            active_idx = 0
                            for idx, p in enumerate(self._providers):
                                if p == self._selected_provider:
                                    active_idx = idx
                                    break

                            self._provider_combo = ui.ComboBox(active_idx, *self._providers, width=220, height=28)
                            self._provider_combo.model.add_item_changed_fn(self._on_provider_changed)

                            # Botón para marcar como predeterminado de inicio
                            self._set_default_btn = ui.Button(
                                "★ Establecer como predeterminado",
                                width=210,
                                height=28,
                                style={"background_color": 0xFF2E7D32, "border_radius": 4, "font_size": 11},
                                clicked_fn=self._on_set_as_default_clicked,
                            )

                            self._default_indicator_label = ui.Label(
                                "(Predeterminado)" if self._selected_provider == self._settings_manager.get_default_provider() else "",
                                style={"color": 0xFF4CAF50, "font_size": 11, "font_weight": "bold"},
                                width=120,
                            )

                    # --- Selección de Modelo Predeterminado ---
                    with ui.VStack(spacing=6):
                        ui.Label(
                            "2. Modelo Predeterminado para el Servicio:",
                            style={"font_size": 13, "font_weight": "bold", "color": 0xFFE0E0E0},
                        )
                        with ui.HStack(height=28, spacing=8):
                            self._model_combo_frame = ui.Frame(width=280, height=28)
                            self._rebuild_model_combo()

                            self._discover_models_btn = ui.Button(
                                "🔄 Descubrir en Vivo",
                                width=150,
                                height=28,
                                style={"background_color": 0xFF007ACC, "border_radius": 4, "font_size": 11},
                                clicked_fn=self._on_discover_models_clicked,
                            )
                            self._discover_status_label = ui.Label(
                                "",
                                style={"color": 0xFF4CAF50, "font_size": 11, "font_weight": "bold"},
                                width=ui.Fraction(1),
                            )

                        # Campo para modelo personalizado
                        with ui.HStack(height=26, spacing=8):
                            ui.Label("O escribe un modelo personalizado:", width=210, style={"color": 0xFF888888, "font_size": 11})
                            self._custom_model_field = ui.StringField(height=24, width=ui.Fraction(1))
                            self._custom_model_field.model.set_value("")
                            ui.Button(
                                "Agregar",
                                width=65,
                                height=24,
                                style={"background_color": 0xFF444444, "border_radius": 4, "font_size": 11},
                                clicked_fn=self._on_add_custom_model_clicked,
                            )

                    ui.Rectangle(height=1, style={"background_color": 0xFF333333})

                    # --- Configuración de Red y Presets de 1 Clic ---
                    with ui.VStack(spacing=6):
                        ui.Label(
                            "3. Dirección del Servidor (Base URL) & Presets de 1 Clic:",
                            style={"font_size": 13, "font_weight": "bold", "color": 0xFFE0E0E0},
                        )
                        curr_cfg = self._settings_manager.get_provider_config(self._selected_provider)

                        with ui.HStack(height=28, spacing=8):
                            ui.Label("URL Base:", width=70, style={"color": 0xFFCCCCCC, "font_size": 12})
                            self._url_field = ui.StringField(height=26, width=ui.Fraction(1))
                            self._url_field.model.set_value(curr_cfg.get("base_url", ""))

                        # Presets rápidos de 1 clic
                        with ui.HStack(height=26, spacing=6):
                            ui.Label("Presets 1-Clic:", width=95, style={"color": 0xFFAAAAAA, "font_size": 11})
                            self._presets_frame = ui.Frame(width=ui.Fraction(1), height=26)
                            self._rebuild_presets_buttons()

                    # --- Clave de Autenticación (API Key) ---
                    with ui.VStack(spacing=6):
                        ui.Label(
                            "4. Credenciales de Autenticación (API Key):",
                            style={"font_size": 13, "font_weight": "bold", "color": 0xFFE0E0E0},
                        )
                        with ui.HStack(height=28, spacing=8):
                            ui.Label("API Key:", width=70, style={"color": 0xFFCCCCCC, "font_size": 12})
                            self._api_key_field = ui.StringField(height=26, width=ui.Fraction(1), password_mode=True)
                            self._api_key_field.model.set_value(curr_cfg.get("api_key", ""))

                        env_var = curr_cfg.get("env_key")
                        env_hint = f"Detectado de variable de entorno ${env_var}" if env_var else "No requiere API key para ejecución local"
                        ui.Label(
                            f"💡 {env_hint}. Dejar vacío para autodetectar.",
                            style={"color": 0xFF777777, "font_size": 11},
                        )

                    # --- Prueba de Conexión de 1 Clic ---
                    with ui.HStack(height=32, spacing=10):
                        self._test_conn_btn = ui.Button(
                            "🔌 Probar Conexión",
                            width=150,
                            height=30,
                            style={"background_color": 0xFF007ACC, "border_radius": 4, "font_size": 12},
                            clicked_fn=self._on_test_connection_clicked,
                        )
                        self._test_status_label = ui.Label(
                            "",
                            style={"font_size": 11, "font_weight": "bold"},
                            width=ui.Fraction(1),
                        )

                    ui.Rectangle(height=1, style={"background_color": 0xFF333333})

                    # --- Parámetros Avanzados de Inferencia ---
                    with ui.VStack(spacing=6):
                        ui.Label(
                            "5. Parámetros de Inferencia (Opcional):",
                            style={"font_size": 13, "font_weight": "bold", "color": 0xFFE0E0E0},
                        )
                        with ui.HStack(height=28, spacing=12):
                            ui.Label("Temperatura:", width=85, style={"color": 0xFFCCCCCC, "font_size": 12})
                            self._temp_field = ui.StringField(height=24, width=60)
                            self._temp_field.model.set_value(str(curr_cfg.get("temperature", 0.7)))

                            ui.Label("Timeout (s):", width=75, style={"color": 0xFFCCCCCC, "font_size": 12})
                            self._timeout_field = ui.StringField(height=24, width=65)
                            self._timeout_field.model.set_value(str(curr_cfg.get("timeout", 600.0)))

                            ui.Label("Max Tokens:", width=80, style={"color": 0xFFCCCCCC, "font_size": 12})
                            self._max_tokens_field = ui.StringField(height=24, width=70)
                            self._max_tokens_field.model.set_value(str(curr_cfg.get("max_tokens", 4096)))

                    ui.Rectangle(height=1, style={"background_color": 0xFF444444})

                    # --- Barra Inferior de Acciones ---
                    with ui.HStack(height=36, spacing=10):
                        self._save_btn = ui.Button(
                            "💾 Guardar y Aplicar",
                            width=160,
                            height=34,
                            style={"background_color": 0xFF007ACC, "border_radius": 6, "font_size": 12, "font_weight": "bold"},
                            clicked_fn=self._on_save_clicked,
                        )

                        self._reset_btn = ui.Button(
                            "↺ Restaurar Valores",
                            width=140,
                            height=34,
                            style={"background_color": 0xFF555555, "border_radius": 6, "font_size": 12},
                            clicked_fn=self._on_reset_clicked,
                        )

                        self._close_btn = ui.Button(
                            "Cerrar",
                            width=90,
                            height=34,
                            style={"background_color": 0xFF333333, "border_radius": 6, "font_size": 12},
                            clicked_fn=self.hide,
                        )

                        self._action_status_label = ui.Label(
                            "",
                            style={"color": 0xFF4CAF50, "font_size": 12, "font_weight": "bold"},
                            width=ui.Fraction(1),
                        )

    def _rebuild_model_combo(self) -> None:
        """Reconstruye el desplegable de modelos disponibles para el proveedor seleccionado."""
        if not hasattr(self, "_model_combo_frame") or not self._model_combo_frame:
            return

        models = self._settings_manager.get_available_models(self._selected_provider)
        active_idx = 0
        for idx, m in enumerate(models):
            if m == self._selected_model:
                active_idx = idx
                break

        self._model_combo_frame.clear()
        with self._model_combo_frame:
            self._model_combo = ui.ComboBox(active_idx, *models, width=300, height=28)
            self._model_combo.model.add_item_changed_fn(self._on_model_selection_changed)

    def _rebuild_presets_buttons(self) -> None:
        """Reconstruye la fila de botones de configuración rápida de 1 clic según el proveedor."""
        if not hasattr(self, "_presets_frame") or not self._presets_frame:
            return

        presets = self._settings_manager.get_presets(self._selected_provider)
        self._presets_frame.clear()
        with self._presets_frame:
            with ui.HStack(spacing=6):
                if not presets:
                    ui.Label("(Sin presets adicionales)", style={"color": 0xFF666666, "font_size": 11})
                else:
                    for p in presets:
                        label = p.get("label", "Preset")
                        target_url = p.get("url", "")

                        def _make_apply_fn(url_val: str):
                            def _apply():
                                if hasattr(self, "_url_field") and self._url_field:
                                    self._url_field.model.set_value(url_val)
                                    if hasattr(self, "_test_status_label"):
                                        self._test_status_label.text = f"URL actualizada a {url_val}"
                            return _apply

                        ui.Button(
                            label,
                            height=24,
                            style={"background_color": 0xFF383838, "border_radius": 3, "font_size": 11},
                            clicked_fn=_make_apply_fn(target_url),
                        )

    # --- Callbacks y Manejadores de Eventos ---

    def _on_provider_changed(self, item_model, item) -> None:
        """Maneja el cambio de proveedor en el ComboBox principal."""
        try:
            val_idx = item_model.get_item_value_model().as_int
            if 0 <= val_idx < len(self._providers):
                self._selected_provider = self._providers[val_idx]
                self._selected_model = self._settings_manager.get_default_model(self._selected_provider)

                # Actualizar campos de URL, API Key y parámetros
                curr_cfg = self._settings_manager.get_provider_config(self._selected_provider)
                if hasattr(self, "_url_field") and self._url_field:
                    self._url_field.model.set_value(curr_cfg.get("base_url", ""))
                if hasattr(self, "_api_key_field") and self._api_key_field:
                    self._api_key_field.model.set_value(curr_cfg.get("api_key", ""))
                if hasattr(self, "_temp_field") and self._temp_field:
                    self._temp_field.model.set_value(str(curr_cfg.get("temperature", 0.7)))
                if hasattr(self, "_timeout_field") and self._timeout_field:
                    self._timeout_field.model.set_value(str(curr_cfg.get("timeout", 600.0)))
                if hasattr(self, "_max_tokens_field") and self._max_tokens_field:
                    self._max_tokens_field.model.set_value(str(curr_cfg.get("max_tokens", 4096)))

                # Actualizar etiqueta de predeterminado
                if hasattr(self, "_default_indicator_label"):
                    is_def = (self._selected_provider == self._settings_manager.get_default_provider())
                    self._default_indicator_label.text = "(Predeterminado)" if is_def else ""

                # Limpiar mensaje de prueba
                if hasattr(self, "_test_status_label"):
                    self._test_status_label.text = ""

                # Reconstruir combos y presets
                self._rebuild_model_combo()
                self._rebuild_presets_buttons()
        except Exception as e:
            print(f"[SettingsWindow] Error al cambiar proveedor: {e}")

    def _on_model_selection_changed(self, item_model, item) -> None:
        """Maneja la selección de modelo en el ComboBox de modelos."""
        try:
            val_idx = item_model.get_item_value_model().as_int
            models = self._settings_manager.get_available_models(self._selected_provider)
            if 0 <= val_idx < len(models):
                self._selected_model = models[val_idx]
        except Exception as e:
            print(f"[SettingsWindow] Error al seleccionar modelo: {e}")

    def _on_set_as_default_clicked(self) -> None:
        """Marca el servicio seleccionado como predeterminado en el SettingsManager."""
        self._settings_manager.set_default_provider(self._selected_provider)
        if hasattr(self, "_default_indicator_label"):
            self._default_indicator_label.text = "(Predeterminado)"
        if hasattr(self, "_action_status_label"):
            self._action_status_label.text = f"'{self._selected_provider}' fijado como servicio predeterminado."

    def _on_add_custom_model_clicked(self) -> None:
        """Agrega un modelo personalizado ingresado por el usuario."""
        if hasattr(self, "_custom_model_field") and self._custom_model_field:
            custom_name = self._custom_model_field.model.get_value_as_string().strip()
            if custom_name:
                self._settings_manager.add_custom_model(self._selected_provider, custom_name)
                self._selected_model = custom_name
                self._custom_model_field.model.set_value("")
                self._rebuild_model_combo()
                if hasattr(self, "_action_status_label"):
                    self._action_status_label.text = f"Modelo '{custom_name}' agregado."

    def _on_test_connection_clicked(self) -> None:
        """Dispara la prueba de conexión asíncrona sin bloquear el hilo principal de Omniverse."""
        if hasattr(self, "_test_status_label"):
            self._test_status_label.text = "Probando conexión..."
            self._test_status_label.style = {"color": 0xFF00B4D8, "font_size": 11}

        url_val = self._url_field.model.get_value_as_string().strip() if hasattr(self, "_url_field") else ""
        key_val = self._api_key_field.model.get_value_as_string().strip() if hasattr(self, "_api_key_field") else ""

        asyncio.ensure_future(self._run_async_test_connection(url_val, key_val))

    async def _run_async_test_connection(self, url: str, api_key: str) -> None:
        """Ejecuta la prueba de conexión asíncrona."""
        res = await self._settings_manager.test_connection(
            provider_name=self._selected_provider,
            base_url=url if url else None,
            api_key=api_key if api_key else None,
        )
        if hasattr(self, "_test_status_label") and self._test_status_label:
            if res.get("success"):
                self._test_status_label.text = f"✓ {res.get('message', 'Conexión exitosa')}"
                self._test_status_label.style = {"color": 0xFF4CAF50, "font_size": 11, "font_weight": "bold"}
            else:
                self._test_status_label.text = f"✗ {res.get('message', 'Error de conexión')}"
                self._test_status_label.style = {"color": 0xFFE53935, "font_size": 11}

    def _on_save_clicked(self) -> None:
        """Guarda la configuración modificada y notifica a los escuchas."""
        try:
            url_val = self._url_field.model.get_value_as_string().strip() if hasattr(self, "_url_field") else ""
            key_val = self._api_key_field.model.get_value_as_string().strip() if hasattr(self, "_api_key_field") else ""

            temp_val = 0.7
            if hasattr(self, "_temp_field"):
                try:
                    temp_val = float(self._temp_field.model.get_value_as_string().strip())
                except ValueError:
                    pass

            timeout_val = 600.0
            if hasattr(self, "_timeout_field"):
                try:
                    timeout_val = float(self._timeout_field.model.get_value_as_string().strip())
                except ValueError:
                    pass

            max_tokens_val = 4096
            if hasattr(self, "_max_tokens_field"):
                try:
                    max_tokens_val = int(self._max_tokens_field.model.get_value_as_string().strip())
                except ValueError:
                    pass

            # Actualizar configuración del proveedor activo
            self._settings_manager.update_provider_config(
                self._selected_provider,
                base_url=url_val if url_val else None,
                api_key=key_val,
                default_model=self._selected_model,
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tokens_val,
            )

            # Sincronizar modelo por defecto y establecer proveedor predeterminado
            self._settings_manager.set_default_model(self._selected_provider, self._selected_model)
            self._settings_manager.set_default_provider(self._selected_provider)

            if hasattr(self, "_default_indicator_label") and self._default_indicator_label:
                self._default_indicator_label.text = "(Predeterminado)"

            if hasattr(self, "_action_status_label") and self._action_status_label:
                self._action_status_label.text = "✓ Configuración guardada y establecida como predeterminada."

            # Disparar callback de notificación hacia la vista principal
            if self._on_save_callback:
                try:
                    self._on_save_callback(self._selected_provider, self._selected_model)
                except Exception as e:
                    print(f"[SettingsWindow] Error en on_save_callback: {e}")

        except Exception as e:
            if hasattr(self, "_action_status_label"):
                self._action_status_label.text = f"Error al guardar: {e}"

    def _on_reset_clicked(self) -> None:
        """Restablece los valores por defecto del proveedor activo."""
        self._settings_manager.reset_to_defaults()
        self._selected_provider = self._settings_manager.get_default_provider()
        self._selected_model = self._settings_manager.get_default_model(self._selected_provider)
        if hasattr(self, "_action_status_label"):
            self._action_status_label.text = "Valores de fábrica restablecidos."
        self._build_ui()

    def _on_discover_models_clicked(self) -> None:
        """Consulta asíncronamente los modelos vivos disponibles en el servidor seleccionado."""
        if hasattr(self, "_discover_status_label") and self._discover_status_label:
            self._discover_status_label.text = "Consultando modelos en vivo..."
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            self._discover_task = loop.create_task(self._discover_models_async())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._discover_task = loop.create_task(self._discover_models_async())


    async def _discover_models_async(self) -> None:
        """Tarea asíncrona de fondo para descubrir modelos sin bloquear la UI de Omniverse."""
        try:
            prov = self._selected_provider
            models = await self._settings_manager.fetch_remote_models(prov)
            self._rebuild_model_combo()
            if hasattr(self, "_discover_status_label") and self._discover_status_label:
                if models:
                    self._discover_status_label.text = f"✓ {len(models)} modelos vivos"
                else:
                    self._discover_status_label.text = "Sin modelos nuevos detectados"
        except Exception as e:
            if hasattr(self, "_discover_status_label") and self._discover_status_label:
                self._discover_status_label.text = f"Fallo al descubrir: {e}"

