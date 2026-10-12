"""ESP32 terminal IDE para MicroPython (ESPTUI).
Instalación: python -m pip install 'textual[syntax]' pyserial adafruit-ampy
Ejecución: python main.py o tuiesp32
Soporta edición estándar y modo VIM, selección rápida de puertos seriales,
navegación de paneles estilo lazygit, y edición de archivos locales y remotos.
"""

import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import serial
import serial.tools.list_ports
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DirectoryTree, Footer, Header, Input, Label, ListItem,
    ListView, LoadingIndicator, RichLog, Static, TextArea,
)

SERIAL_KEYWORDS = (
    "cp210", "ch340", "ch341", "ftdi", "usb-serial",
    "esp32", "esp8266", "usbserial", "usb jtag", "acm", "ttyusb",
)


def load_config():
    config = {"port": "AUTO", "baudrate": 115200, "theme": "monokai"}
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


class BusyScreen(ModalScreen):
    DEFAULT_CSS = """
    BusyScreen { align: center middle; background: $background 70%; }
    #busy-box { width: 44; height: 9; border: heavy cyan; padding: 1 2; }
    #busy-box Static { text-align: center; height: 1; }
    #busy-box LoadingIndicator { height: 3; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="busy-box"):
            yield Static("Procesando en placa...")
            yield LoadingIndicator()


class PortSelectModal(ModalScreen):
    """Modal enumerado para selección rápida de puerto serial filtrado por chip ESP/USB."""
    DEFAULT_CSS = """
    PortSelectModal { align: center middle; background: $background 80%; }
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
            yield Static("Seleccionar Puerto Serial (ESPTUI)", id="port-title")
            yield Static("Presiona el número [1-9] del puerto o selecciónalo con Enter:", id="port-subtitle")
            yield ListView(id="port-list")
            with Horizontal(id="port-actions"):
                yield Button("Refrescar (R)", id="btn-refresh-ports", variant="default")
                yield Button("Continuar sin conexión (Esc)", id="btn-cancel-port", variant="warning")

    def on_mount(self):
        self.load_ports()

    def load_ports(self):
        matched, others = get_filtered_ports()
        self.ports_list = matched + others
        list_view = self.query_one("#port-list", ListView)
        list_view.clear()
        if not self.ports_list:
            list_view.append(ListItem(Label("No se detectaron puertos seriales. Conecta la placa y presiona 'R'.")))
            return

        for idx, port in enumerate(self.ports_list[:9], start=1):
            is_matched = port in matched
            tag = " [ESP/USB]" if is_matched else ""
            desc = port.description or "Dispositivo serial"
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
    KeybindingsHelpModal { align: center middle; background: $background 80%; }
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
[b cyan]Navegación de Paneles (Estilo Lazygit):[/]
  [b yellow]1[/]           Enfocar panel de Archivos locales y de la placa
  [b yellow]2[/]           Enfocar Editor de código
  [b yellow]3[/]           Enfocar Consola REPL (comando serial)
  [b yellow]Alt+1/2/3[/]   Navegación directa entre paneles desde cualquier foco

[b cyan]Operaciones de Código y Placa ESP32:[/]
  [b yellow]Ctrl+S[/]      Guardar archivo (local o subir directo si es de la placa)
  [b yellow]F5[/]          Ejecutar código en placa vía Paste Mode
  [b yellow]Ctrl+U[/]      Subir archivo a la placa (ampy put)
  [b yellow]F8[/]          [b red]Parar ejecución[/] (Interrupción Ctrl+C en placa)
  [b yellow]F9[/]          Reinicio suave (Ctrl+D)

[b cyan]Modo de Edición (Estándar vs VIM):[/]
  [b yellow]Ctrl+V[/]      Alternar entre edición Estándar y modo VIM
  * En VIM Normal: [yellow]h/j/k/l[/] mover cursor, [yellow]i/a/o[/] insertar, [yellow]x[/] borrar, [yellow]u[/] deshacer
  * En VIM Normal: teclas [yellow]1[/], [yellow]2[/], [yellow]3[/] saltan directamente a los paneles
  * En VIM Insert: [yellow]Esc[/] vuelve a modo Normal

[b cyan]Control de Interfaz y Conexión:[/]
  [b yellow]Ctrl+P[/]      Abrir selector rápido de puertos seriales
  [b yellow]F6[/]          Colapsar / expandir panel de archivos
  [b yellow]F7[/]          Colapsar / expandir consola REPL
  [b yellow]F1[/] o [b yellow]?[/],    Abrir este modal de atajos
  [b yellow]Ctrl+Q[/]      Salir de la aplicación
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("Atajos de Teclado — ESPTUI", id="help-title")
            yield Static(self.HELP_INFO.strip(), id="help-text")
            yield Button("Entendido / Cerrar (Esc)", id="btn-close-help", variant="primary")

    def action_dismiss_modal(self):
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-close-help":
            self.dismiss()


class VimCodeEditor(TextArea):
    """Editor de código con soporte para modo estándar y modo VIM modal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vim_enabled = False
        self.vim_mode = "NORMAL"

    def on_key(self, event) -> None:
        if not self.vim_enabled:
            return

        if self.vim_mode == "INSERT":
            if event.key == "escape":
                self.vim_mode = "NORMAL"
                if hasattr(self.app, "update_editor_mode_display"):
                    self.app.update_editor_mode_display()
                event.prevent_default()
                event.stop()
            return

        # Modo VIM NORMAL
        if event.key in ("1", "2", "3"):
            if hasattr(self.app, "action_focus_panel"):
                panel_map = {"1": "files", "2": "editor", "3": "console"}
                self.app.action_focus_panel(panel_map[event.key])
            event.prevent_default()
            event.stop()
            return
        elif event.key == "h":
            self.action_cursor_left()
        elif event.key == "l":
            self.action_cursor_right()
        elif event.key == "k":
            self.action_cursor_up()
        elif event.key == "j":
            self.action_cursor_down()
        elif event.key == "w":
            self.action_cursor_word_right()
        elif event.key == "b":
            self.action_cursor_word_left()
        elif event.key in ("0", "home"):
            self.action_cursor_line_start()
        elif event.key in ("dollar", "end"):
            self.action_cursor_line_end()
        elif event.key == "x":
            self.action_delete_right()
        elif event.key == "u":
            self.action_undo()
        elif event.key == "r" and event.ctrl:
            self.action_redo()
        elif event.key == "i":
            self.vim_mode = "INSERT"
            if hasattr(self.app, "update_editor_mode_display"):
                self.app.update_editor_mode_display()
        elif event.key == "a":
            self.action_cursor_right()
            self.vim_mode = "INSERT"
            if hasattr(self.app, "update_editor_mode_display"):
                self.app.update_editor_mode_display()
        elif event.key == "A":
            self.action_cursor_line_end()
            self.vim_mode = "INSERT"
            if hasattr(self.app, "update_editor_mode_display"):
                self.app.update_editor_mode_display()
        elif event.key == "I":
            self.action_cursor_line_start()
            self.vim_mode = "INSERT"
            if hasattr(self.app, "update_editor_mode_display"):
                self.app.update_editor_mode_display()
        elif event.key == "o":
            self.action_cursor_line_end()
            self.insert("\n")
            self.vim_mode = "INSERT"
            if hasattr(self.app, "update_editor_mode_display"):
                self.app.update_editor_mode_display()
        elif event.key == "d":
            self.action_delete_line()

        event.prevent_default()
        event.stop()


class ESP32TUIApp(App):
    TITLE = "ESPTUI — MicroPython IDE"
    CSS = """
    Screen { layout: vertical; }
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
    #serial-input { height: 3; margin-top: 1; }
    #editor-header { height: auto; margin-bottom: 1; }
    #editor-title { width: 1fr; color: cyan; }
    #editor-mode-badge { width: auto; color: yellow; text-style: bold; }
    #editor-buttons { height: 3; margin-top: 1; }
    #editor-buttons Button { width: 1fr; min-width: 0; margin: 0 1; }
    #refresh-esp32 { width: 100%; margin-top: 1; }
    """
    BINDINGS = [
        # Navegación estilo lazygit
        Binding("1", "focus_panel('files')", "Archivos [1]", priority=False),
        Binding("2", "focus_panel('editor')", "Editor [2]", priority=False),
        Binding("3", "focus_panel('console')", "Consola [3]", priority=False),
        Binding("alt+1", "focus_panel('files')", "Archivos", priority=True),
        Binding("alt+2", "focus_panel('editor')", "Editor", priority=True),
        Binding("alt+3", "focus_panel('console')", "Consola", priority=True),

        # Operaciones y botones
        Binding("ctrl+s", "save_file", "Guardar", priority=True),
        Binding("f5", "run_code", "Ejecutar", priority=True),
        Binding("ctrl+u", "upload_file", "Subir", priority=True),
        Binding("f8", "stop_execution", "Parar", priority=True),
        Binding("f9", "send_soft_reset", "Reiniciar", priority=True),

        # Modos y diálogo de ayuda
        Binding("ctrl+v", "toggle_vim_mode", "Modo VIM", priority=True),
        Binding("f1", "show_help", "Atajos", priority=True),
        Binding("question_mark", "show_help", "Ayuda", priority=False),
        Binding("ctrl+p", "select_port", "Puertos", priority=True),

        # Control de paneles
        Binding("f6", "toggle_sidebar", "Archivos", priority=True),
        Binding("f7", "toggle_console", "Consola", priority=True),
        Binding("ctrl+q", "quit", "Salir", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static("Archivos locales [1]", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield DirectoryTree(str(self.user_home), id="local-files")
                    yield Static("ESP32: sin conectar", id="board-title", classes="title")
                    yield ListView(id="esp32-files")
                    yield Button("Refrescar placa", id="refresh-esp32")
                yield Static("F\nI\nL\nE\nS", classes="collapsed-label")
            with Vertical(id="editor-pane"):
                with Horizontal(id="editor-header"):
                    yield Static("Editor [2]: main.py", id="editor-title")
                    yield Static("[Modo: Estándar | Ctrl+V para VIM]", id="editor-mode-badge")
                yield VimCodeEditor(
                    "# MicroPython\nprint('Hola ESP32')\n",
                    language="python", theme=self.config["theme"], id="code-editor",
                )
                with Horizontal(id="editor-buttons"):
                    yield Button("Guardar (Ctrl+S)", id="save-btn", variant="success")
                    yield Button("Ejecutar (F5)", id="send-btn", variant="primary")
                    yield Button("Subir (Ctrl+U)", id="upload-btn", variant="warning")
                    yield Button("Parar (F8)", id="stop-btn", variant="error")
            with Vertical(id="console-pane"):
                yield Static("Consola REPL [3]", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield RichLog(id="serial-log", markup=False, highlight=False, max_lines=3000)
                    yield Input(placeholder="Comando REPL...", id="serial-input")
                yield Static("R\nE\nP\nL", classes="collapsed-label")
        yield Footer()

    def on_mount(self):
        self.editor = self.query_one("#code-editor", VimCodeEditor)
        self.serial_log = self.query_one("#serial-log", RichLog)
        self.remote_files = self.query_one("#esp32-files", ListView)
        self.update_editor_mode_display()

        # Si se especificó un puerto estático en config distinto a AUTO, conectar directo
        if self.config["port"] != "AUTO":
            self.connect_to_port(self.config["port"])
        else:
            # En modo AUTO, mostrar modal enumerado para selección rápida
            self.call_after_refresh(self.action_select_port)

    def update_editor_mode_display(self):
        badge = self.query_one("#editor-mode-badge", Static)
        if not self.editor.vim_enabled:
            badge.update("[Modo: Estándar | Ctrl+V: VIM]")
        else:
            if self.editor.vim_mode == "NORMAL":
                badge.update("[VIM: NORMAL (i:Insert, hjkl, 1-3:Paneles)]")
            else:
                badge.update("[VIM: INSERT (Esc:Normal)]")

    def action_toggle_vim_mode(self):
        self.editor.vim_enabled = not self.editor.vim_enabled
        self.editor.vim_mode = "NORMAL"
        self.update_editor_mode_display()
        modo_txt = "Activado" if self.editor.vim_enabled else "Desactivado"
        self.serial_log.write(f"Modo VIM {modo_txt}. (Usa Ctrl+V para alternar)")

    def action_show_help(self):
        self.push_screen(KeybindingsHelpModal())

    def action_select_port(self):
        def on_port_selected(selected_port):
            if selected_port:
                self.connect_to_port(selected_port)
            else:
                self.serial_log.write("Trabajando sin puerto conectado. Usa Ctrl+P para seleccionar uno.")

        self.push_screen(PortSelectModal(), on_port_selected)

    def connect_to_port(self, port_device):
        try:
            with self.serial_lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            self.port = port_device
            self.query_one("#board-title", Static).update(f"ESP32: {self.port}")
            self.open_serial()
            self.serial_log.write(f"Conectado a puerto: {self.port}")
            if not hasattr(self, "reader") or not self.reader.is_alive():
                self.reader = threading.Thread(target=self.read_serial, daemon=True)
                self.reader.start()
            self.start_board_task("list")
        except Exception as error:
            self.serial_log.write(f"Conexión con {port_device}: {error}")

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
        self.ser = serial.Serial(
            self.port, self.config["baudrate"], timeout=0.1, write_timeout=2,
        )

    def read_serial(self):
        while not self.stopping.is_set():
            data = b""
            try:
                with self.serial_lock:
                    if self.ser and self.ser.is_open:
                        data = self.ser.read(min(self.ser.in_waiting or 1, 4096))
            except serial.SerialException as error:
                self.log_from_thread(f"Lectura serial: {error}")
                self.stopping.wait(0.5)
            if data:
                self.log_from_thread(data.decode("utf-8", errors="replace").rstrip("\r\n"))
            self.stopping.wait(0.02)

    def ampy(self, *args):
        result = subprocess.run(
            ["ampy", "--port", self.port, "--baud", str(self.config["baudrate"]), *args],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip()
                                or f"ampy terminó con código {result.returncode}")
        return result.stdout

    def get_busy_screen(self):
        return BusyScreen()

    def start_board_task(self, operation, remote_filename=None):
        if self.busy:
            self.serial_log.write("Espera a que termine la operación actual.")
            return
        if not self.port:
            self.serial_log.write("Selecciona un puerto con Ctrl+P para realizar operaciones de placa.")
            return
        self.busy = True
        content = self.editor.text
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
                    messages.append("Código enviado por Paste Mode; revisa la salida del REPL.")
                else:
                    if self.ser and self.ser.is_open:
                        self.ser.close()
                    try:
                        if operation == "upload":
                            with tempfile.TemporaryDirectory(prefix="esp32-tui-") as directory:
                                temporary = Path(directory) / filename
                                temporary.write_text(content, encoding="utf-8")
                                self.ampy("put", str(temporary), filename)
                            messages.append(f"Archivo subido a placa: {filename}")
                        elif operation == "get" and remote_filename:
                            raw = self.ampy("get", remote_filename)
                            loaded_remote = (remote_filename, raw)
                            messages.append(f"Archivo de placa descargado: {remote_filename}")
                        files = self.ampy("ls").splitlines()
                    finally:
                        if not self.stopping.is_set():
                            try:
                                self.open_serial()
                                messages.append(f"Consola reconectada: {self.port}")
                            except Exception as error:
                                messages.append(f"No se pudo reconectar: {error}")
        except Exception as error:
            messages.append(f"Operación {operation}: {error}")
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
                items = [ListItem(Label(name.strip())) for name in files if name.strip()]
                if items:
                    await self.remote_files.extend(items)
            if loaded_remote:
                fname, body = loaded_remote
                self.editor.load_text(body)
                self.is_remote_file = True
                self.current_remote_file = fname
                self.query_one("#editor-title", Static).update(f"Editor [2] (ESP32): {fname}")
            for message in messages:
                self.serial_log.write(message)
        finally:
            self.pop_screen()
            self.busy = False

    def write_repl(self, payload):
        if self.busy:
            self.serial_log.write("Puerto ocupado por otra operación.")
            return False
        try:
            with self.serial_lock:
                if not self.ser or not self.ser.is_open:
                    raise RuntimeError("La consola serial no está conectada")
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
        self.serial_log.write("[STOP] Deteniendo ejecución en la placa (Ctrl+C)...")
        self.write_repl(b"\x03\x03")

    def action_send_interrupt(self):
        self.action_stop_execution()

    def action_send_soft_reset(self):
        self.serial_log.write("[RESET] Reinicio suave (Ctrl+D)...")
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
            self.query_one("#editor-title", Static).update(f"Editor [2]: {path.name}")
            self.serial_log.write(f"Abierto archivo local: {path.name}")
        except Exception as error:
            self.serial_log.write(f"Abrir archivo: {error}")

    def on_list_view_selected(self, event: ListView.Selected):
        """Al seleccionar un archivo remoto de la placa, descargarlo para editarlo."""
        if event.list_view.id == "esp32-files" and event.item:
            labels = event.item.query(Label)
            if labels:
                target_file = str(labels.first().renderable).strip()
                if target_file:
                    self.serial_log.write(f"Cargando archivo de la placa: {target_file}...")
                    self.start_board_task("get", remote_filename=target_file)

    def action_save_file(self):
        if self.is_remote_file and self.current_remote_file:
            # Si estamos editando un archivo descargado de la placa, guardar lo sube de vuelta
            self.start_board_task("upload", remote_filename=self.current_remote_file)
            return
        try:
            self.current_file.write_text(self.editor.text, encoding="utf-8")
            self.serial_log.write(f"Guardado localmente: {self.current_file}")
        except Exception as error:
            self.serial_log.write(f"Guardar archivo: {error}")

    def on_button_pressed(self, event: Button.Pressed):
        actions = {
            "save-btn": self.action_save_file,
            "send-btn": self.action_run_code,
            "upload-btn": self.action_upload_file,
            "stop-btn": self.action_stop_execution,
            "refresh-esp32": lambda: self.start_board_task("list"),
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
