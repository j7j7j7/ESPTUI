"""ESP32 terminal IDE for MicroPython.
Install: python -m pip install 'textual[syntax]' pyserial adafruit-ampy
Run: python main.py
Optional config.json: {"port": "AUTO", "baudrate": 115200, "theme": "monokai"}
TextArea is not a Vim/Neovim editor. CircuitPython support is not validated.
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


def find_port(configured):
    if configured.upper() != "AUTO":
        return configured
    keywords = ("cp210", "ch340", "ch341", "ftdi", "usb-serial",
                "esp32", "esp8266", "usbserial", "usb jtag")
    ports = list(serial.tools.list_ports.comports())
    matches = [p.device for p in ports if any(
        key in f"{p.description or ''} {p.hwid or ''}".lower()
        for key in keywords
    )]
    if len(matches) == 1:
        return matches[0]
    if not matches and len(ports) == 1:
        return ports[0].device
    candidates = matches or [p.device for p in ports]
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
            yield Static("Procesando...")
            yield LoadingIndicator()


class ESP32TUIApp(App):
    TITLE = "ESP32 Terminal IDE"
    CSS = """
    Screen { layout: vertical; }
    #workspace { height: 1fr; width: 100%; }
    #sidebar { width: 23%; height: 100%; border: solid yellow; padding: 1; }
    #editor-pane { width: 1fr; height: 100%; border: solid green; padding: 1; }
    #console-pane { width: 27%; height: 100%; border: solid blue; padding: 1; }
    #sidebar.collapsed, #console-pane.collapsed {
        width: 7; min-width: 7; padding: 0; overflow: hidden;
    }
    .panel-content { height: 1fr; }
    .collapsed .hideable { display: none; }
    .collapsed-label { display: none; text-align: center; color: yellow; margin-top: 1; }
    .collapsed .collapsed-label { display: block; }
    .title { height: auto; color: cyan; margin-bottom: 1; }
    DirectoryTree { height: 1fr; border: solid cyan; }
    #esp32-files { height: 1fr; border: solid magenta; margin-top: 1; }
    #code-editor { height: 1fr; border: heavy gray; }
    #serial-log { height: 1fr; border: heavy gray; }
    #serial-input { height: 3; margin-top: 1; }
    #editor-buttons { height: 3; margin-top: 1; }
    #editor-buttons Button { width: 1fr; min-width: 0; margin: 0; }
    #refresh-esp32 { width: 100%; margin-top: 1; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save_file", "Guardar", priority=True),
        Binding("f5", "run_code", "Ejecutar", priority=True),
        Binding("f6", "toggle_sidebar", "Archivos", priority=True),
        Binding("f7", "toggle_console", "Consola", priority=True),
        Binding("f8", "send_interrupt", "Interrumpir", priority=True),
        Binding("f9", "send_soft_reset", "Reiniciar", priority=True),
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
        self.current_file = Path.cwd() / "main.py"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static("Archivos locales", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield DirectoryTree(str(Path.cwd()))
                    yield Static("ESP32: sin conectar", id="board-title", classes="title")
                    yield ListView(id="esp32-files")
                    yield Button("Refrescar placa", id="refresh-esp32")
                yield Static("F\nI\nL\nE\nS", classes="collapsed-label")
            with Vertical(id="editor-pane"):
                yield Static("Editor: main.py", id="editor-title", classes="title")
                yield TextArea.code_editor(
                    "# MicroPython\nprint('Hola ESP32')\n",
                    language="python", theme=self.config["theme"], id="code-editor",
                )
                with Horizontal(id="editor-buttons"):
                    yield Button("Guardar", id="save-btn", variant="success")
                    yield Button("Ejecutar", id="send-btn", variant="primary")
                    yield Button("Subir", id="upload-btn", variant="warning")
            with Vertical(id="console-pane"):
                yield Static("Consola REPL", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield RichLog(id="serial-log", markup=False, highlight=False, max_lines=3000)
                    yield Input(placeholder="Comando REPL...", id="serial-input")
                yield Static("R\nE\nP\nL", classes="collapsed-label")
        yield Footer()

    def on_mount(self):
        self.editor = self.query_one("#code-editor", TextArea)
        # App.log pertenece a Textual; el widget REPL necesita un nombre propio.
        self.serial_log = self.query_one("#serial-log", RichLog)
        self.remote_files = self.query_one("#esp32-files", ListView)
        try:
            self.port = find_port(self.config["port"])
        except Exception as error:
            self.serial_log.write(f"Conexion: {error}")
            return
        self.query_one("#board-title", Static).update(f"ESP32: {self.port}")
        self.reader = threading.Thread(target=self.read_serial, daemon=True)
        self.reader.start()
        self.start_board_task("list")

    def log_from_thread(self, text):
        if not self.stopping.is_set():
            try:
                self.call_from_thread(self.serial_log.write, text)
            except RuntimeError:
                pass

    def open_serial(self):
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
                               or f"ampy termino con codigo {result.returncode}")
        return result.stdout

    def start_board_task(self, operation):
        if self.busy:
            self.serial_log.write("Espera a que termine la operacion actual.")
            return
        if not self.port:
            self.serial_log.write("Configura un puerto y reinicia la aplicacion.")
            return
        self.busy = True
        content = self.editor.text
        filename = self.current_file.name
        self.push_screen(BusyScreen())
        threading.Thread(
            target=self.board_task, args=(operation, content, filename), daemon=True,
        ).start()

    def board_task(self, operation, content, filename):
        files = None
        messages = []
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
                    messages.append("Codigo enviado por Paste Mode; revisa la salida del REPL.")
                else:
                    if self.ser and self.ser.is_open:
                        self.ser.close()
                    try:
                        if operation == "upload":
                            with tempfile.TemporaryDirectory(prefix="esp32-tui-") as directory:
                                temporary = Path(directory) / filename
                                temporary.write_text(content, encoding="utf-8")
                                self.ampy("put", str(temporary), filename)
                            messages.append(f"Archivo subido: {filename}")
                        files = self.ampy("ls").splitlines()
                    finally:
                        if not self.stopping.is_set():
                            try:
                                self.open_serial()
                                messages.append(f"Consola conectada: {self.port}")
                            except Exception as error:
                                messages.append(f"No se pudo reconectar: {error}")
        except Exception as error:
            messages.append(f"Operacion {operation}: {error}")
        finally:
            if not self.stopping.is_set():
                try:
                    self.call_from_thread(self.finish_board_task, files, messages)
                except RuntimeError:
                    pass

    async def finish_board_task(self, files, messages):
        try:
            if files is not None:
                await self.remote_files.clear()
                items = [ListItem(Label(name.strip())) for name in files if name.strip()]
                if items:
                    await self.remote_files.extend(items)
            for message in messages:
                self.serial_log.write(message)
        finally:
            self.pop_screen()
            self.busy = False

    def write_repl(self, payload):
        if self.busy:
            self.serial_log.write("Puerto ocupado por otra operacion.")
            return False
        try:
            with self.serial_lock:
                if not self.ser or not self.ser.is_open:
                    raise RuntimeError("La consola serial no esta conectada")
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

    def action_send_interrupt(self):
        self.write_repl(b"\x03")

    def action_send_soft_reset(self):
        self.write_repl(b"\x04")

    def action_run_code(self):
        self.start_board_task("run")

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
            self.query_one("#editor-title", Static).update(f"Editor: {path.name}")
        except Exception as error:
            self.serial_log.write(f"Abrir archivo: {error}")

    def action_save_file(self):
        try:
            self.current_file.write_text(self.editor.text, encoding="utf-8")
            self.serial_log.write(f"Guardado: {self.current_file}")
        except Exception as error:
            self.serial_log.write(f"Guardar archivo: {error}")

    def on_button_pressed(self, event: Button.Pressed):
        actions = {
            "save-btn": self.action_save_file,
            "send-btn": self.action_run_code,
            "refresh-esp32": lambda: self.start_board_task("list"),
            "upload-btn": lambda: self.start_board_task("upload"),
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
