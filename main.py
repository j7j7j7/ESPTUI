"""ESP32 terminal IDE para MicroPython (ESPTUI).
Instalación: python -m pip install 'textual[syntax]' pyserial adafruit-ampy
Ejecución: python main.py o esptui (alias: tuiesp32)
Editor de código estándar, selección rápida de puertos seriales,
navegación homogénea de paneles y edición de archivos locales y remotos.
"""

import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import serial
import serial.tools.list_ports
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DirectoryTree, Footer, Header, Input, Label, ListItem,
    ListView, LoadingIndicator, RichLog, Select, Static, TextArea,
)
from i18n import get_i18n

SERIAL_KEYWORDS = (
    "cp210", "ch340", "ch341", "ftdi", "usb-serial",
    "esp32", "esp8266", "usbserial", "usb jtag", "acm", "ttyusb",
)


def load_config():
    config = {"port": "AUTO", "baudrate": 115200, "theme": "monokai", "lang": "en"}
    path = Path(__file__).resolve().parent / "config.json"
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config.json debe contener un objeto JSON")
        config.update(loaded)
    config["baudrate"] = int(config["baudrate"])
    if config["baudrate"] <= 0:
        raise ValueError("baudrate debe ser positivo")
    if not isinstance(config["port"], str) or not config["port"].strip():
        raise ValueError("port debe ser AUTO o un puerto serial")
    if "lang" in config and not isinstance(config["lang"], str):
        raise ValueError("lang debe ser un código de idioma válido")
    return config


def get_filtered_ports():
    """Detecta y clasifica puertos seriales priorizando chips ESP y adaptadores USB."""
    all_ports = list(serial.tools.list_ports.comports())
    matched = []
    others = []
    for port in all_ports:
        desc = f"{port.device} {port.description or ''} {port.hwid or ''}".lower()
        if any(key in desc for key in SERIAL_KEYWORDS):
            matched.append(port)
        else:
            others.append(port)
    return matched, others


def find_port(configured):
    if configured.upper() != "AUTO":
        return configured
    matched, others = get_filtered_ports()
    if len(matched) == 1:
        return matched[0].device
    if not matched and len(others) == 1:
        return others[0].device
    candidates = [p.device for p in (matched or others)]
    if candidates:
        raise RuntimeError("Varios puertos disponibles; configura port: "
                           + ", ".join(candidates))
    raise RuntimeError("No se detectaron puertos seriales")


def app_t(screen, key: str, default: str | None = None, **kwargs) -> str:
    """Helper to translate strings within modal screens using the active app instance."""
    if hasattr(screen, "app") and hasattr(screen.app, "t"):
        return screen.app.t(key, default=default, **kwargs)
    return default if default is not None else key


class BusyScreen(ModalScreen):
    DEFAULT_CSS = """
    BusyScreen { align: center middle; background: $background; }
    #busy-box { width: 44; height: 9; border: heavy cyan; padding: 1 2; }
    #busy-box Static { text-align: center; height: 1; }
    #busy-box LoadingIndicator { height: 3; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="busy-box"):
            yield Static(app_t(self, "modals.busy.processing", default="Procesando en placa..."))
            yield LoadingIndicator()


class PortSelectModal(ModalScreen):
    """Modal enumerado para selección rápida de puerto serial filtrado por chip ESP/USB."""
    DEFAULT_CSS = """
    PortSelectModal { align: center middle; background: $background; }
    #port-dialog {
        width: 76;
        height: auto;
        max-height: 24;
        border: heavy cyan;
        background: $surface;
        padding: 1 2;
    }
    #port-title { text-align: center; color: cyan; text-style: bold; margin-bottom: 1; }
    #port-subtitle { text-align: center; color: gray; margin-bottom: 1; }
    #port-list { height: auto; max-height: 12; border: solid cyan; margin-bottom: 1; }
    #port-actions { height: 3; align: center middle; }
    #port-actions Button { margin: 0 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cerrar", priority=True),
        Binding("r", "refresh_ports", "Refrescar", priority=True),
        Binding("1", "pick_index(0)", "Puerto 1", priority=True),
        Binding("2", "pick_index(1)", "Puerto 2", priority=True),
        Binding("3", "pick_index(2)", "Puerto 3", priority=True),
        Binding("4", "pick_index(3)", "Puerto 4", priority=True),
        Binding("5", "pick_index(4)", "Puerto 5", priority=True),
        Binding("6", "pick_index(5)", "Puerto 6", priority=True),
        Binding("7", "pick_index(6)", "Puerto 7", priority=True),
        Binding("8", "pick_index(7)", "Puerto 8", priority=True),
        Binding("9", "pick_index(8)", "Puerto 9", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.ports_list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="port-dialog"):
            yield Static(app_t(self, "modals.port_select.title", default="Seleccionar Puerto Serial (ESPTUI)"), id="port-title")
            yield Static(app_t(self, "modals.port_select.subtitle", default="Presiona el número [1-9] del puerto o selecciónalo con Enter:"), id="port-subtitle")
            yield ListView(id="port-list")
            with Horizontal(id="port-actions"):
                yield Button(app_t(self, "modals.port_select.refresh", default="Refrescar (R)"), id="btn-refresh-ports", variant="default")
                yield Button(app_t(self, "modals.port_select.cancel", default="Continuar sin conexión (Esc)"), id="btn-cancel-port", variant="warning")

    def on_mount(self):
        self.load_ports()

    def load_ports(self):
        matched, others = get_filtered_ports()
        self.ports_list = matched + others
        list_view = self.query_one("#port-list", ListView)
        list_view.clear()
        if not self.ports_list:
            list_view.append(ListItem(Label(app_t(self, "modals.port_select.no_ports", default="No se detectaron puertos seriales. Conecta la placa y presiona 'R'."))))
            return

        for idx, port in enumerate(self.ports_list[:9], start=1):
            is_matched = port in matched
            tag = " [ESP/USB]" if is_matched else ""
            desc = port.description or app_t(self, "modals.port_select.device", default="Dispositivo serial")
            label = f"[{idx}] {port.device} — {desc}{tag}"
            list_view.append(ListItem(Label(label)))

    def action_refresh_ports(self):
        self.load_ports()

    def action_dismiss_modal(self):
        self.dismiss(None)

    def action_pick_index(self, index: int):
        if 0 <= index < len(self.ports_list):
            self.dismiss(self.ports_list[index].device)

    def on_list_view_selected(self, event: ListView.Selected):
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self.ports_list):
            self.dismiss(self.ports_list[idx].device)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-refresh-ports":
            self.load_ports()
        elif event.button.id == "btn-cancel-port":
            self.dismiss(None)


class KeybindingsHelpModal(ModalScreen):
    """Modal con la lista de atajos de teclado del IDE."""
    DEFAULT_CSS = """
    KeybindingsHelpModal { align: center middle; background: $background; }
    #help-dialog {
        width: 78;
        height: auto;
        max-height: 28;
        border: heavy cyan;
        background: $surface;
        padding: 1 2;
    }
    #help-title { text-align: center; color: cyan; text-style: bold; margin-bottom: 1; }
    #help-text { height: auto; margin-bottom: 1; }
    #btn-close-help { width: 100%; margin-top: 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cerrar", priority=True),
        Binding("enter", "dismiss_modal", "Cerrar", priority=True),
    ]

    HELP_INFO = """
[b cyan]Navegación entre Paneles:[/]
  [b yellow]Alt+1[/]         Enfocar panel de Archivos locales y placa
  [b yellow]Alt+2[/]         Enfocar Editor de código
  [b yellow]Alt+3[/]         Enfocar Consola REPL

[b cyan]Operaciones de Archivos:[/]
  [b yellow]Ctrl+N[/]        Crear [b green]Nuevo archivo[/]
  [b yellow]F4[/]            [b green]Renombrar / Guardar como[/] (cambiar nombre de archivo o en placa)
  [b yellow]Ctrl+S[/]        [b green]Guardar[/] archivo actual (localmente o en placa)
  [b yellow]F5[/]            [b green]Ejecutar[/] código en la placa (Paste Mode)
  [b yellow]F6[/]            [b green]Subir[/] archivo a la memoria de la placa (ampy put)
  [b yellow]F8[/]            [b red]Parar ejecución[/] (Interrupción Ctrl+C en placa)
  [b yellow]F9[/]            Reinicio suave de la placa (Ctrl+D)

[b cyan]Archivos de la Placa (ESP32):[/]
  [b yellow]Clic Izq / Enter[/]  Abrir y editar archivo en el editor
  [b yellow]Clic Der / m[/]      Menú de opciones (Abrir, Renombrar, Eliminar)
  [b yellow]Supr (Delete)[/]    Eliminar archivo seleccionado de la placa
  [b yellow]F4[/]            Renombrar archivo seleccionado en la placa

[b cyan]Herramientas y Vistas:[/]
  [b yellow]Ctrl+C[/]        [b green]Copiar[/] selección o registro de la consola al portapapeles
  [b yellow]F1[/] o [b yellow]?[/]        Mostrar esta ventana de ayuda y atajos
  [b yellow]F2[/] o [b yellow]Ctrl+P[/]   Selector rápido de puertos seriales
  [b yellow]F7[/]            Colapsar / expandir consola REPL
  [b yellow]F10[/]           Colapsar / expandir panel de archivos
  [b yellow]Ctrl+Q[/]        Salir del IDE
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(app_t(self, "modals.keybindings.title", default="Atajos de Teclado — ESPTUI"), id="help-title")
            yield Static(app_t(self, "modals.keybindings.info", default=self.HELP_INFO.strip()), id="help-text")
            yield Button(app_t(self, "modals.keybindings.close", default="Entendido / Cerrar (Esc)"), id="btn-close-help", variant="primary")

    def action_dismiss_modal(self):
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-close-help":
            self.dismiss()


class FileNameModal(ModalScreen):
    """Modal para crear un nuevo archivo o renombrar / guardar como."""
    DEFAULT_CSS = """
    FileNameModal { align: center middle; background: $background; }
    #filename-dialog {
        width: 60;
        height: auto;
        max-height: 18;
        border: heavy cyan;
        background: $surface;
        padding: 1 2;
    }
    #filename-title { text-align: center; color: cyan; text-style: bold; margin-bottom: 1; }
    #filename-input { width: 100%; margin-bottom: 1; }
    #filename-actions { height: 3; align: center middle; }
    #filename-actions Button { margin: 0 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancelar", priority=True),
    ]

    def __init__(self, title=None, default_name="sketch.py"):
        super().__init__()
        self.dialog_title = title
        self.default_name = default_name

    def compose(self) -> ComposeResult:
        title = self.dialog_title or app_t(self, "modals.file_name.default_title", default="Nombre del archivo")
        with Vertical(id="filename-dialog"):
            yield Static(title, id="filename-title")
            placeholder = app_t(self, "modals.file_name.placeholder", default="nombre_archivo.py")
            yield Input(value=self.default_name, placeholder=placeholder, id="filename-input")
            with Horizontal(id="filename-actions"):
                yield Button(app_t(self, "modals.file_name.accept", default="Aceptar (Enter)"), id="btn-filename-accept", variant="success")
                yield Button(app_t(self, "modals.file_name.cancel", default="Cancelar (Esc)"), id="btn-filename-cancel", variant="warning")

    def on_mount(self):
        self.query_one("#filename-input", Input).focus()

    def action_dismiss_modal(self):
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        val = event.value.strip()
        self.dismiss(val if val else None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-filename-accept":
            val = self.query_one("#filename-input", Input).value.strip()
            self.dismiss(val if val else None)
        elif event.button.id == "btn-filename-cancel":
            self.dismiss(None)


class RemoteFileActionModal(ModalScreen):
    """Modal de menú contextual para archivos de la placa (abrir, renombrar, eliminar)."""
    DEFAULT_CSS = """
    RemoteFileActionModal { align: center middle; background: $background; }
    #remote-action-dialog {
        width: 60;
        height: auto;
        border: heavy magenta;
        background: $surface;
        padding: 1 2;
    }
    #remote-action-title { text-align: center; color: magenta; text-style: bold; margin-bottom: 1; }
    #remote-action-buttons { height: auto; }
    #remote-action-buttons Button { width: 100%; margin-bottom: 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_action('cancel')", "Cancelar", priority=True),
        Binding("1", "dismiss_action('open')", "Abrir", priority=True),
        Binding("2", "dismiss_action('rename')", "Renombrar", priority=True),
        Binding("3", "dismiss_action('delete')", "Eliminar", priority=True),
    ]

    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename

    def compose(self) -> ComposeResult:
        with Vertical(id="remote-action-dialog"):
            title = app_t(self, "modals.remote_file_action.title", filename=self.filename, default=f"Archivo en ESP32: [b cyan]{self.filename}[/]")
            yield Static(title, id="remote-action-title")
            with Vertical(id="remote-action-buttons"):
                yield Button(app_t(self, "modals.remote_file_action.open", default="1. Abrir / Editar en IDE"), id="btn-action-open", variant="success")
                yield Button(app_t(self, "modals.remote_file_action.rename", default="2. Renombrar en placa"), id="btn-action-rename", variant="primary")
                yield Button(app_t(self, "modals.remote_file_action.delete", default="3. Eliminar de placa"), id="btn-action-delete", variant="error")
                yield Button(app_t(self, "modals.remote_file_action.cancel", default="4. Cancelar (Esc)"), id="btn-action-cancel")

    def on_mount(self):
        self.query_one("#btn-action-open", Button).focus()

    def action_dismiss_action(self, action: str):
        self.dismiss(action if action != "cancel" else None)

    def on_button_pressed(self, event: Button.Pressed):
        action_map = {
            "btn-action-open": "open",
            "btn-action-rename": "rename",
            "btn-action-delete": "delete",
            "btn-action-cancel": None,
        }
        self.dismiss(action_map.get(event.button.id))


class ConfirmDeleteModal(ModalScreen):
    """Modal de confirmación para eliminar un archivo de la placa."""
    DEFAULT_CSS = """
    ConfirmDeleteModal { align: center middle; background: $background; }
    #confirm-delete-dialog {
        width: 62;
        height: auto;
        border: heavy red;
        background: $surface;
        padding: 1 2;
    }
    #confirm-delete-title { text-align: center; color: red; text-style: bold; margin-bottom: 1; }
    #confirm-delete-text { text-align: center; margin-bottom: 1; }
    #confirm-delete-actions { height: 3; align: center middle; }
    #confirm-delete-actions Button { margin: 0 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal(False)", "Cancelar", priority=True),
    ]

    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-delete-dialog"):
            yield Static(app_t(self, "modals.confirm_delete.title", default="¿Eliminar archivo de la placa?"), id="confirm-delete-title")
            text = app_t(self, "modals.confirm_delete.text", filename=self.filename, default=f"¿Deseas eliminar permanentemente [b yellow]{self.filename}[/] de la flash?")
            yield Static(text, id="confirm-delete-text")
            with Horizontal(id="confirm-delete-actions"):
                yield Button(app_t(self, "modals.confirm_delete.confirm", default="Sí, eliminar"), id="btn-confirm-delete", variant="error")
                yield Button(app_t(self, "modals.confirm_delete.cancel", default="Cancelar (Esc)"), id="btn-cancel-delete", variant="primary")

    def action_dismiss_modal(self, confirmed: bool):
        self.dismiss(confirmed)

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "btn-confirm-delete")


class RemoteFileItem(ListItem):
    """Elemento de la lista de archivos de la placa con soporte para clic derecho."""
    def __init__(self, filename: str):
        super().__init__(Label(filename))
        self.filename = filename.strip()

    def on_mouse_down(self, event: events.MouseDown):
        if event.button == 3:
            event.stop()
            event.prevent_default()
            self.app.action_remote_file_context(self.filename)


def copy_text_to_system_clipboard(app, text: str) -> bool:
    """Copia texto al portapapeles del sistema (Textual copy, wl-copy, xclip)."""
    if not text:
        return False
    try:
        app.copy_to_clipboard(text)
    except Exception:
        pass
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=2)
                break
            except Exception:
                pass
    return True


class ConsoleLog(RichLog):
    """Consola con soporte de selección, copiado al portapapeles y clic derecho."""
    def on_mouse_down(self, event: events.MouseDown):
        if event.button == 3:
            event.stop()
            event.prevent_default()
            self.app.action_copy_console()


class ESP32TUIApp(App):
    TITLE = "ESPTUI — MicroPython IDE"
    CSS = """
    Screen { layout: vertical; }
    ModalScreen { background: $background; }
    #workspace { height: 1fr; width: 100%; }
    #sidebar { width: 25%; height: 100%; border: solid yellow; padding: 1; }
    #editor-pane { width: 1fr; height: 100%; border: solid green; padding: 1; }
    #console-pane { width: 28%; height: 100%; border: solid blue; padding: 1; }
    #sidebar.collapsed, #console-pane.collapsed {
        width: 7; min-width: 7; padding: 0; overflow: hidden;
    }
    .panel-content { height: 1fr; }
    .collapsed .hideable { display: none; }
    .collapsed-label { display: none; text-align: center; color: yellow; margin-top: 1; }
    .collapsed .collapsed-label { display: block; }
    .title { height: auto; color: cyan; margin-bottom: 1; }
    #local-files { height: 1fr; border: solid cyan; }
    #esp32-files { height: 1fr; border: solid magenta; margin-top: 1; }
    #code-editor { height: 1fr; border: heavy gray; }
    #serial-log { height: 1fr; border: heavy gray; }
    #console-actions { height: 3; margin-top: 1; }
    #console-actions Button { width: 1fr; min-width: 0; margin: 0 1; }
    #serial-input { height: 3; margin-top: 1; }
    #editor-buttons { height: 3; margin-top: 1; }
    #editor-buttons Button { width: 1fr; min-width: 0; margin: 0 1; }
    #refresh-esp32 { width: 100%; margin-top: 1; }
    #top-bar {
        height: 1;
        background: $surface;
        dock: top;
        align-horizontal: right;
        align-vertical: middle;
        padding: 0 1;
    }
    #top-bar-lang-label {
        color: $text-muted;
        margin-right: 1;
        height: 1;
    }
    #lang-select {
        width: 18;
        height: 1;
    }
    #lang-select SelectCurrent {
        border: none;
        padding: 0 1;
        height: 1;
    }
    """
    BINDINGS = [
        # Navegación homogénea entre paneles (oculta del footer para dar más aire)
        Binding("alt+1", "focus_panel('files')", "Archivos", priority=True, show=False),
        Binding("alt+2", "focus_panel('editor')", "Editor", priority=True, show=False),
        Binding("alt+3", "focus_panel('console')", "Consola", priority=True, show=False),
        Binding("1", "focus_panel('files')", "Archivos", priority=False, show=False),
        Binding("2", "focus_panel('editor')", "Editor", priority=False, show=False),
        Binding("3", "focus_panel('console')", "Consola", priority=False, show=False),
        Binding("ctrl+c", "copy_console", "Copiar consola", priority=False, show=False),

        # Operaciones de Archivos, Editor y Placa
        Binding("ctrl+n", "new_file", "Crear archivo", priority=True),
        Binding("f4", "rename_file", "Renombrar", priority=True),
        Binding("ctrl+s", "save_file", "Guardar", priority=True),
        Binding("f5", "run_code", "Ejecutar", priority=True),
        Binding("f6", "upload_file", "Subir", priority=True),
        Binding("f8", "stop_execution", "Parar", priority=True),
        Binding("f9", "send_soft_reset", "Reiniciar", priority=True),

        # Herramientas y modales
        Binding("f1", "show_help", "Ayuda", priority=True),
        Binding("question_mark", "show_help", "Ayuda", priority=False, show=False),
        Binding("f2", "select_port", "Puertos", priority=True),
        Binding("ctrl+p", "select_port", "Puertos", priority=True, show=False),
        Binding("f3", "cycle_language", "Idioma / Lang", priority=True, show=False),

        # Control de paneles y salida
        Binding("f7", "toggle_console", "Consola", priority=True, show=False),
        Binding("f10", "toggle_sidebar", "Archivos", priority=True, show=False),
        Binding("ctrl+q", "quit", "Salir", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.i18n = get_i18n(default_lang=self.config.get("lang", "en"))
        if "lang" in self.config:
            self.i18n.set_language(self.config["lang"])
        self.port = None
        self.ser = None
        self.serial_lock = threading.Lock()
        self.stopping = threading.Event()
        self.busy = False
        # Por defecto la raíz del explorador es la carpeta de usuario
        self.user_home = Path.home()
        self.current_file = self.user_home / "main.py"
        self.is_remote_file = False
        self.current_remote_file = None
        self.remote_content_loaded = None

    def t(self, key_path: str, default: str | None = None, **kwargs) -> str:
        return self.i18n.t(key_path, default=default, **kwargs)

    def compose(self) -> ComposeResult:
        yield Header()
        if self.i18n.has_multiple_languages:
            with Horizontal(id="top-bar"):
                yield Static(self.t("top_bar.language_label", default="🌐 Language:"), id="top-bar-lang-label")
                yield Select(
                    self.i18n.get_language_options(),
                    value=self.i18n.current_lang,
                    id="lang-select",
                    allow_blank=False,
                )
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static(self.t("sidebar.title", default="Archivos locales y placa [Alt+1]"), id="sidebar-title", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield DirectoryTree(str(self.user_home), id="local-files")
                    yield Static(self.t("sidebar.board_disconnected", default="ESP32: sin conectar"), id="board-title", classes="title")
                    yield ListView(id="esp32-files")
                    yield Button(self.t("sidebar.refresh_board", default="Refrescar placa"), id="refresh-esp32")
                yield Static(self.t("sidebar.collapsed_label", default="F\nI\nL\nE\nS"), classes="collapsed-label")
            with Vertical(id="editor-pane"):
                yield Static(self.t("editor.title", filename=self.current_file.name, default=f"Editor de código [Alt+2]: {self.current_file.name}"), id="editor-title", classes="title")
                yield TextArea.code_editor(
                    self.t("editor.default_code", default="# MicroPython\nprint('Hola ESP32')\n"),
                    language="python", theme=self.config.get("theme", "monokai"), id="code-editor",
                )
                with Horizontal(id="editor-buttons"):
                    yield Button(self.t("editor.save", default="Guardar (Ctrl+S)"), id="save-btn", variant="success")
                    yield Button(self.t("editor.run", default="Ejecutar (F5)"), id="send-btn", variant="primary")
                    yield Button(self.t("editor.upload", default="Subir (F6)"), id="upload-btn", variant="warning")
                    yield Button(self.t("editor.stop", default="Parar (F8)"), id="stop-btn", variant="error")
            with Vertical(id="console-pane"):
                yield Static(self.t("console.title", default="Consola serial REPL [Alt+3]"), id="console-title", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield ConsoleLog(id="serial-log", markup=False, highlight=False, max_lines=3000)
                    with Horizontal(id="console-actions"):
                        yield Button(self.t("console.copy", default="Copiar (Ctrl+C)"), id="btn-copy-console")
                        yield Button(self.t("console.clear", default="Limpiar"), id="btn-clear-console")
                    yield Input(placeholder=self.t("console.placeholder", default="Comando REPL..."), id="serial-input")
                yield Static(self.t("console.collapsed_label", default="R\nE\nP\nL"), classes="collapsed-label")
        yield Footer()

    def on_mount(self):
        self.editor = self.query_one("#code-editor", TextArea)
        self.serial_log = self.query_one("#serial-log", ConsoleLog)
        self.remote_files = self.query_one("#esp32-files", ListView)
        self.update_ui_texts()

        # Si se especificó un puerto estático en config distinto a AUTO, conectar directo
        if self.config["port"] != "AUTO":
            self.connect_to_port(self.config["port"])
        else:
            # En modo AUTO, mostrar modal enumerado para selección rápida
            self.call_after_refresh(self.action_select_port)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "lang-select" and event.value != Select.BLANK:
            self.action_change_language(str(event.value))

    def action_change_language(self, lang_code: str):
        if not self.i18n.set_language(lang_code):
            return
        self.config["lang"] = lang_code
        try:
            select = self.query_one("#lang-select", Select)
            if select.value != lang_code:
                select.value = lang_code
        except Exception:
            pass
        self.update_ui_texts()
        self.serial_log.write(self.t("messages.language_changed", lang=lang_code.upper(), default=f"Language changed to: {lang_code.upper()}"))

    def action_cycle_language(self):
        langs = list(self.i18n.available_languages.keys())
        if len(langs) <= 1:
            return
        try:
            idx = langs.index(self.i18n.current_lang)
            next_lang = langs[(idx + 1) % len(langs)]
        except ValueError:
            next_lang = langs[0]
        self.action_change_language(next_lang)

    def update_ui_texts(self):
        try:
            self.query_one("#top-bar-lang-label", Static).update(
                self.t("top_bar.language_label", default="🌐 Language:")
            )
        except Exception:
            pass

        try:
            self.query_one("#sidebar-title", Static).update(
                self.t("sidebar.title", default="Local & board files [Alt+1]")
            )
            if self.port:
                self.query_one("#board-title", Static).update(
                    self.t("sidebar.board_connected", port=self.port, default=f"ESP32: {self.port}")
                )
            else:
                self.query_one("#board-title", Static).update(
                    self.t("sidebar.board_disconnected", default="ESP32: disconnected")
                )
            self.query_one("#refresh-esp32", Button).label = self.t("sidebar.refresh_board", default="Refresh board")
        except Exception:
            pass

        try:
            if self.is_remote_file and self.current_remote_file:
                self.query_one("#editor-title", Static).update(
                    self.t("editor.title_esp32", filename=self.current_remote_file, default=f"Code editor [Alt+2] (ESP32): {self.current_remote_file}")
                )
            else:
                self.query_one("#editor-title", Static).update(
                    self.t("editor.title", filename=self.current_file.name, default=f"Code editor [Alt+2]: {self.current_file.name}")
                )
            self.query_one("#save-btn", Button).label = self.t("editor.save", default="Save (Ctrl+S)")
            self.query_one("#send-btn", Button).label = self.t("editor.run", default="Run (F5)")
            self.query_one("#upload-btn", Button).label = self.t("editor.upload", default="Upload (F6)")
            self.query_one("#stop-btn", Button).label = self.t("editor.stop", default="Stop (F8)")
        except Exception:
            pass

        try:
            self.query_one("#console-title", Static).update(
                self.t("console.title", default="Serial REPL console [Alt+3]")
            )
            self.query_one("#btn-copy-console", Button).label = self.t("console.copy", default="Copy (Ctrl+C)")
            self.query_one("#btn-clear-console", Button).label = self.t("console.clear", default="Clear")
            self.query_one("#serial-input", Input).placeholder = self.t("console.placeholder", default="REPL command...")
        except Exception:
            pass

        bindings_map = {
            "focus_panel('files')": self.t("footer.files", default="Files"),
            "focus_panel('editor')": self.t("footer.editor", default="Editor"),
            "focus_panel('console')": self.t("footer.console", default="Console"),
            "copy_console": self.t("footer.copy_console", default="Copy console"),
            "new_file": self.t("footer.new_file", default="New file"),
            "rename_file": self.t("footer.rename", default="Rename"),
            "save_file": self.t("footer.save", default="Save"),
            "run_code": self.t("footer.run", default="Run"),
            "upload_file": self.t("footer.upload", default="Upload"),
            "stop_execution": self.t("footer.stop", default="Stop"),
            "send_soft_reset": self.t("footer.reset", default="Reset"),
            "show_help": self.t("footer.help", default="Help"),
            "select_port": self.t("footer.ports", default="Ports"),
            "quit": self.t("footer.quit", default="Quit"),
        }
        for key, action in [
            ("alt+1", "focus_panel('files')"),
            ("alt+2", "focus_panel('editor')"),
            ("alt+3", "focus_panel('console')"),
            ("ctrl+c", "copy_console"),
            ("ctrl+n", "new_file"),
            ("f4", "rename_file"),
            ("ctrl+s", "save_file"),
            ("f5", "run_code"),
            ("f6", "upload_file"),
            ("f8", "stop_execution"),
            ("f9", "send_soft_reset"),
            ("f1", "show_help"),
            ("f2", "select_port"),
            ("ctrl+q", "quit"),
        ]:
            desc = bindings_map.get(action)
            if desc:
                self.bind(key, action, description=desc)
        try:
            self.query_one(Footer).refresh(recompose=True)
        except Exception:
            pass

    def action_show_help(self):
        self.push_screen(KeybindingsHelpModal())

    def action_select_port(self):
        def on_port_selected(selected_port):
            if selected_port:
                self.connect_to_port(selected_port)
            else:
                self.serial_log.write(self.t("messages.no_port_working", default="Trabajando sin puerto conectado. Usa Ctrl+P para seleccionar uno."))

        self.push_screen(PortSelectModal(), on_port_selected)

    def connect_to_port(self, port_device):
        try:
            with self.serial_lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            self.port = port_device
            self.query_one("#board-title", Static).update(self.t("sidebar.board_connected", port=self.port, default=f"ESP32: {self.port}"))
            self.open_serial()
            self.serial_log.write(self.t("messages.connected", port=self.port, default=f"Conectado a puerto: {self.port}"))
            if not hasattr(self, "reader") or not self.reader.is_alive():
                self.reader = threading.Thread(target=self.read_serial, daemon=True)
                self.reader.start()
            self.start_board_task("list")
        except Exception as error:
            self.serial_log.write(self.t("messages.connection_error", port=port_device, error=error, default=f"Conexión con {port_device}: {error}"))

    def action_focus_panel(self, panel_name: str):
        if panel_name in ("files", "1"):
            tree = self.query_one("#local-files", DirectoryTree)
            if tree:
                tree.focus()
        elif panel_name in ("editor", "2"):
            self.editor.focus()
        elif panel_name in ("console", "3"):
            inp = self.query_one("#serial-input", Input)
            if inp:
                inp.focus()

    def log_from_thread(self, text):
        if not self.stopping.is_set():
            try:
                self.call_from_thread(self.serial_log.write, text)
            except RuntimeError:
                pass

    def open_serial(self):
        if not self.port:
            return
        for attempt in range(5):
            try:
                self.ser = serial.Serial(
                    self.port, self.config["baudrate"], timeout=0.1, write_timeout=2,
                )
                return
            except (serial.SerialException, OSError):
                if attempt == 4:
                    raise
                time.sleep(0.15)

    def read_serial(self):
        while not self.stopping.is_set():
            data = b""
            try:
                with self.serial_lock:
                    if self.ser and self.ser.is_open:
                        in_waiting = 0
                        try:
                            in_waiting = self.ser.in_waiting or 1
                        except Exception:
                            in_waiting = 1
                        data = self.ser.read(min(in_waiting, 4096))
            except (serial.SerialException, OSError) as error:
                self.log_from_thread(f"Lectura serial: {error}")
                self.stopping.wait(0.5)
            except Exception as error:
                self.stopping.wait(0.2)
            if data:
                self.log_from_thread(data.decode("utf-8", errors="replace").rstrip("\r\n"))
            self.stopping.wait(0.02)

    def ampy(self, *args):
        last_error = None
        for attempt in range(4):
            result = subprocess.run(
                ["ampy", "--port", self.port, "--baud", str(self.config["baudrate"]), *args],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
            err = (result.stderr.strip() or result.stdout.strip()
                   or f"ampy terminó con código {result.returncode}")
            last_error = err
            if any(msg in err for msg in ("Permission denied", "could not open port", "Device or resource busy")):
                time.sleep(0.3)
                continue
            raise RuntimeError(err)
        raise RuntimeError(last_error or "ampy no pudo acceder al puerto serial tras varios intentos")

    def get_busy_screen(self):
        return BusyScreen()

    def start_board_task(self, operation, remote_filename=None, new_filename=None, force=False):
        if self.busy and not force:
            self.serial_log.write(self.t("messages.wait_busy", default="Espera a que termine la operación actual."))
            return
        if not self.port:
            self.serial_log.write(self.t("messages.select_port_first", default="Selecciona un puerto con Ctrl+P para realizar operaciones de placa."))
            return
        self.busy = True
        content = new_filename if operation == "rename" else self.editor.text
        filename = remote_filename if remote_filename else (
            self.current_remote_file if self.is_remote_file else self.current_file.name
        )
        self.push_screen(self.get_busy_screen())
        threading.Thread(
            target=self.board_task, args=(operation, content, filename, remote_filename), daemon=True,
        ).start()

    def board_task(self, operation, content, filename, remote_filename=None):
        files = None
        messages = []
        loaded_remote = None
        try:
            with self.serial_lock:
                if self.stopping.is_set():
                    return
                if operation == "run":
                    if not self.ser or not self.ser.is_open:
                        self.open_serial()
                    self.ser.write(b"\x03\x03")
                    time.sleep(0.2)
                    self.ser.write(b"\x05")
                    time.sleep(0.2)
                    payload = (content.replace("\r\n", "\n").replace("\n", "\r\n")
                                + "\r\n").encode("utf-8")
                    for offset in range(0, len(payload), 128):
                        if self.stopping.is_set():
                            return
                        self.ser.write(payload[offset:offset + 128])
                        time.sleep(0.01)
                    self.ser.write(b"\x04")
                    messages.append(self.t("messages.code_sent", default="Código enviado por Paste Mode; revisa la salida del REPL."))
                else:
                    if self.ser and self.ser.is_open:
                        try:
                            # Detener cualquier script o bucle activo en la placa con Ctrl+C doble
                            self.ser.write(b"\x03\x03")
                            time.sleep(0.15)
                            self.ser.reset_input_buffer()
                        except Exception:
                            pass
                        self.ser.close()
                    # Permitir al driver del kernel de Linux liberar completamente el descriptor del puerto
                    time.sleep(0.25)
                    try:
                        if operation == "upload":
                            clean_filename = Path(filename).name or "main.py"
                            dest_filename = filename.lstrip("/") or "main.py"
                            with tempfile.TemporaryDirectory(prefix="esp32-tui-") as directory:
                                temporary = Path(directory) / clean_filename
                                temporary.write_text(content, encoding="utf-8")
                                self.ampy("put", str(temporary), dest_filename)
                            messages.append(self.t("messages.uploaded", filename=dest_filename, dest_filename=dest_filename, default=f"Archivo subido a placa: {dest_filename}"))
                        elif operation == "get" and remote_filename:
                            clean_remote = remote_filename.lstrip("/") or "main.py"
                            raw = self.ampy("get", clean_remote)
                            loaded_remote = (clean_remote, raw)
                            messages.append(self.t("messages.downloaded", filename=clean_remote, clean_remote=clean_remote, default=f"Archivo de placa descargado: {clean_remote}"))
                        elif operation == "rm" and remote_filename:
                            clean_remote = remote_filename.lstrip("/")
                            self.ampy("rm", clean_remote)
                            messages.append(self.t("messages.deleted", filename=clean_remote, clean_remote=clean_remote, default=f"Archivo eliminado de la placa: {clean_remote}"))
                            if self.is_remote_file and self.current_remote_file == clean_remote:
                                self.is_remote_file = False
                                self.current_remote_file = None
                        elif operation == "rename" and remote_filename:
                            old_remote = remote_filename.lstrip("/")
                            new_remote = (content or "").lstrip("/")
                            if old_remote and new_remote and old_remote != new_remote:
                                raw = self.ampy("get", old_remote)
                                clean_new = Path(new_remote).name or "main.py"
                                with tempfile.TemporaryDirectory(prefix="esp32-tui-") as directory:
                                    temporary = Path(directory) / clean_new
                                    temporary.write_text(raw, encoding="utf-8")
                                    self.ampy("put", str(temporary), new_remote)
                                self.ampy("rm", old_remote)
                                messages.append(self.t("messages.renamed", old=old_remote, new=new_remote, old_remote=old_remote, new_remote=new_remote, default=f"Archivo renombrado en placa: {old_remote} -> {new_remote}"))
                                if self.is_remote_file and self.current_remote_file == old_remote:
                                    self.current_remote_file = new_remote
                        files = [f for f in self.ampy("ls").splitlines() if f.strip() and f.strip() != "/"]
                    finally:
                        if not self.stopping.is_set():
                            time.sleep(0.25)
                            try:
                                self.open_serial()
                                messages.append(self.t("messages.reconnected", port=self.port, default=f"Consola reconectada: {self.port}"))
                            except Exception as error:
                                messages.append(self.t("messages.reconnect_failed", error=error, default=f"No se pudo reconectar: {error}"))
        except Exception as error:
            messages.append(self.t("messages.operation_error", operation=operation, error=error, default=f"Operación {operation}: {error}"))
        finally:
            if not self.stopping.is_set():
                try:
                    self.call_from_thread(self.finish_board_task, files, messages, loaded_remote)
                except RuntimeError:
                    pass

    async def finish_board_task(self, files, messages, loaded_remote=None):
        try:
            if files is not None:
                await self.remote_files.clear()
                items = [
                    RemoteFileItem(name.strip())
                    for name in files
                    if name.strip() and name.strip() != "/"
                ]
                if items:
                    await self.remote_files.extend(items)
            if loaded_remote:
                fname, body = loaded_remote
                self.editor.load_text(body)
                self.is_remote_file = True
                self.current_remote_file = fname
                self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=fname, default=f"Editor de código [Alt+2] (ESP32): {fname}"))
                self.editor.focus()
            elif self.is_remote_file and self.current_remote_file:
                self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=self.current_remote_file, default=f"Editor de código [Alt+2] (ESP32): {self.current_remote_file}"))
            elif not self.is_remote_file:
                self.query_one("#editor-title", Static).update(self.t("editor.title", filename=self.current_file.name, default=f"Editor de código [Alt+2]: {self.current_file.name}"))
            for message in messages:
                self.serial_log.write(message)
        finally:
            try:
                self.pop_screen()
            except Exception:
                pass
            self.busy = False

    def write_repl(self, payload):
        if self.busy:
            self.serial_log.write(self.t("messages.port_busy", default="Puerto ocupado por otra operación."))
            return False
        try:
            with self.serial_lock:
                if not self.ser or not self.ser.is_open:
                    raise RuntimeError(self.t("messages.not_connected", default="La consola serial no está conectada"))
                self.ser.write(payload)
            return True
        except Exception as error:
            self.serial_log.write(f"Escritura serial: {error}")
            return False

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "serial-input":
            if self.write_repl((event.value + "\r\n").encode("utf-8")):
                self.serial_log.write(f">>> {event.value}")
                event.input.value = ""

    def action_stop_execution(self):
        """Parar toda ejecución: envía interrupción doble Ctrl+C al REPL."""
        self.serial_log.write(self.t("messages.stopping", default="[STOP] Deteniendo ejecución en la placa (Ctrl+C)..."))
        self.write_repl(b"\x03\x03")

    def action_send_interrupt(self):
        self.action_stop_execution()

    def action_send_soft_reset(self):
        self.serial_log.write(self.t("messages.resetting", default="[RESET] Reinicio suave (Ctrl+D)..."))
        self.write_repl(b"\x04")

    def action_run_code(self):
        self.start_board_task("run")

    def action_upload_file(self):
        self.start_board_task("upload")

    def action_toggle_sidebar(self):
        if not self.busy:
            self.query_one("#sidebar").toggle_class("collapsed")

    def action_toggle_console(self):
        if not self.busy:
            self.query_one("#console-pane").toggle_class("collapsed")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        path = Path(event.path)
        try:
            content = path.read_text(encoding="utf-8")
            self.editor.load_text(content)
            self.current_file = path
            self.is_remote_file = False
            self.current_remote_file = None
            self.query_one("#editor-title", Static).update(self.t("editor.title", filename=path.name, default=f"Editor de código [Alt+2]: {path.name}"))
            self.serial_log.write(self.t("messages.local_opened", filename=path.name, default=f"Abierto archivo local: {path.name}"))
        except Exception as error:
            self.serial_log.write(f"Abrir archivo: {error}")

    def on_list_view_selected(self, event: ListView.Selected):
        """Al seleccionar un archivo remoto de la placa, detener cualquier script activo y descargarlo de inmediato."""
        if event.list_view.id == "esp32-files" and event.item:
            target_file = getattr(event.item, "filename", None)
            if not target_file:
                labels = event.item.query(Label)
                if labels:
                    target_file = str(labels.first().render()).strip()
            if target_file and target_file != "/":
                self.serial_log.write(self.t("messages.downloading", filename=target_file, default=f"Deteniendo ejecución y descargando {target_file}..."))
                self.start_board_task("get", remote_filename=target_file, force=True)

    def action_remote_file_context(self, target_file: str):
        """Abre modal contextual con opciones para el archivo de la placa."""
        if not target_file or target_file == "/":
            return

        def on_action_chosen(action):
            if action == "open":
                self.serial_log.write(self.t("messages.downloading", filename=target_file, default=f"Deteniendo ejecución y descargando {target_file}..."))
                self.start_board_task("get", remote_filename=target_file, force=True)
            elif action == "rename":
                self.action_rename_remote_file(target_file)
            elif action == "delete":
                self.action_delete_remote_file(target_file)

        self.push_screen(RemoteFileActionModal(filename=target_file), on_action_chosen)

    def action_rename_remote_file(self, target_file: str):
        """Modal para renombrar un archivo existente en la placa."""
        def on_rename_entered(new_name):
            if new_name and new_name != target_file:
                if not new_name.endswith(".py"):
                    new_name += ".py"
                self.serial_log.write(self.t("messages.renaming", old=target_file, new=new_name, default=f"Renombrando {target_file} a {new_name}..."))
                self.start_board_task("rename", remote_filename=target_file, new_filename=new_name, force=True)

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_rename_esp32", filename=target_file, default=f"Renombrar en ESP32: {target_file}"), default_name=target_file), on_rename_entered)

    def action_delete_remote_file(self, target_file: str):
        """Modal de confirmación para eliminar un archivo en la placa."""
        def on_confirm_delete(confirmed):
            if confirmed:
                self.serial_log.write(self.t("messages.deleting", filename=target_file, default=f"Eliminando {target_file} de la placa..."))
                self.start_board_task("rm", remote_filename=target_file, force=True)

        self.push_screen(ConfirmDeleteModal(filename=target_file), on_confirm_delete)

    def on_key(self, event: events.Key):
        """Soporte de teclado contextual cuando la lista de la placa está enfocada."""
        if hasattr(self, "remote_files") and self.remote_files.has_focus:
            child = self.remote_files.highlighted_child
            if child and isinstance(child, RemoteFileItem):
                fname = child.filename
                if event.key in ("m", "space"):
                    event.stop()
                    event.prevent_default()
                    self.action_remote_file_context(fname)
                elif event.key == "delete":
                    event.stop()
                    event.prevent_default()
                    self.action_delete_remote_file(fname)
                elif event.key == "f4":
                    event.stop()
                    event.prevent_default()
                    self.action_rename_remote_file(fname)

    def action_save_file(self):
        if self.is_remote_file and self.current_remote_file:
            # Si estamos editando un archivo descargado de la placa, guardar lo sube de vuelta
            self.start_board_task("upload", remote_filename=self.current_remote_file)
            return
        try:
            self.current_file.write_text(self.editor.text, encoding="utf-8")
            self.serial_log.write(self.t("messages.saved_local", path=str(self.current_file), default=f"Guardado localmente: {self.current_file}"))
        except Exception as error:
            self.serial_log.write(f"Guardar archivo: {error}")

    def action_new_file(self):
        """Crear un nuevo archivo en blanco."""
        def on_name_entered(filename):
            if filename:
                if not filename.endswith(".py"):
                    filename += ".py"
                self.current_file = self.user_home / filename
                self.is_remote_file = False
                self.current_remote_file = None
                self.editor.load_text(self.t("editor.new_script_code", default="# MicroPython\nprint('Nuevo script')\n"))
                self.query_one("#editor-title", Static).update(self.t("editor.title", filename=filename, default=f"Editor de código [Alt+2]: {filename}"))
                self.serial_log.write(self.t("messages.new_file_created", filename=filename, default=f"Nuevo archivo local: {filename}"))
                self.editor.focus()

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_new", default="Crear Nuevo Archivo"), default_name="nuevo_script.py"), on_name_entered)

    def action_rename_file(self):
        """Renombrar el archivo activo o definir con qué nombre se subirá a la placa."""
        current_name = self.current_remote_file if self.is_remote_file else self.current_file.name
        def on_name_entered(filename):
            if filename:
                if not filename.endswith(".py"):
                    filename += ".py"
                if self.is_remote_file:
                    self.current_remote_file = filename
                    self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=filename, default=f"Editor de código [Alt+2] (ESP32): {filename}"))
                else:
                    self.current_file = self.current_file.parent / filename
                    self.query_one("#editor-title", Static).update(self.t("editor.title", filename=filename, default=f"Editor de código [Alt+2]: {filename}"))
                self.serial_log.write(self.t("messages.active_file_changed", filename=filename, default=f"Archivo activo ahora es: {filename}"))
                self.editor.focus()

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_rename", default="Renombrar / Guardar Como"), default_name=current_name), on_name_entered)

    def action_copy_console(self):
        """Copia la selección del usuario o todo el registro de la consola al portapapeles."""
        selected = self.screen.get_selected_text()
        if selected:
            copy_text_to_system_clipboard(self, selected)
            self.serial_log.write(self.t("messages.clipboard_selected", default="[PORTAPAPELES] Texto seleccionado copiado."))
        else:
            lines = [str(getattr(l, "text", l)) for l in self.serial_log.lines]
            text = "\n".join(lines).strip()
            if text:
                copy_text_to_system_clipboard(self, text)
                self.serial_log.write(self.t("messages.clipboard_console", default="[PORTAPAPELES] Consola copiada al portapapeles."))
            else:
                self.serial_log.write(self.t("messages.clipboard_empty", default="[PORTAPAPELES] No hay texto para copiar."))

    def on_button_pressed(self, event: Button.Pressed):
        actions = {
            "save-btn": self.action_save_file,
            "send-btn": self.action_run_code,
            "upload-btn": self.action_upload_file,
            "stop-btn": self.action_stop_execution,
            "refresh-esp32": lambda: self.start_board_task("list"),
            "btn-new-file": self.action_new_file,
            "btn-rename-file": self.action_rename_file,
            "btn-copy-console": self.action_copy_console,
            "btn-clear-console": self.serial_log.clear,
        }
        action = actions.get(event.button.id)
        if action:
            action()

    def on_unmount(self):
        self.stopping.set()
        if self.ser and self.ser.is_open:
            self.ser.close()


if __name__ == "__main__":
    ESP32TUIApp().run()
