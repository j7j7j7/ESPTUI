"""ESP32 terminal IDE para MicroPython (ESPTUI).
Instalación: python -m pip install 'textual[syntax]' pyserial adafruit-ampy
Ejecución: python main.py o esptui (alias: tuiesp32)
Editor de código estándar, selección rápida de puertos seriales,
navegación homogénea de paneles y edición de archivos locales y remotos.
"""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import replace
from pathlib import Path

import serial
import serial.tools.list_ports
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, DirectoryTree, Footer, Header, Input, Label, ListItem,
    ListView, LoadingIndicator, ProgressBar, RichLog, Select, Static, TextArea,
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


def update_binding_descriptions(target, key_desc_map: dict[str, str]):
    """Update binding descriptions in place without altering priority or key actions."""
    if not hasattr(target, "_bindings"):
        return
    for key, desc in key_desc_map.items():
        if key in target._bindings.key_to_bindings:
            target._bindings.key_to_bindings[key] = [
                replace(b, description=desc) for b in target._bindings.key_to_bindings[key]
            ]


class BusyScreen(ModalScreen):
    DEFAULT_CSS = """
    BusyScreen { align: center middle; background: $background; }
    #busy-box { width: 44; height: 9; border: heavy cyan; padding: 1 2; }
    #busy-box Static { text-align: center; height: 1; }
    #busy-box LoadingIndicator { height: 3; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="busy-box"):
            yield Static(app_t(self, "modals.busy.processing", default="Processing on board..."))
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
        Binding("escape", "dismiss_modal", "Close", priority=True),
        Binding("r", "refresh_ports", "Refresh", priority=True),
        Binding("f3", "cycle_language", "Language", priority=True),
        Binding("1", "pick_index(0)", "Port 1", priority=True),
        Binding("2", "pick_index(1)", "Port 2", priority=True),
        Binding("3", "pick_index(2)", "Port 3", priority=True),
        Binding("4", "pick_index(3)", "Port 4", priority=True),
        Binding("5", "pick_index(4)", "Port 5", priority=True),
        Binding("6", "pick_index(5)", "Port 6", priority=True),
        Binding("7", "pick_index(6)", "Port 7", priority=True),
        Binding("8", "pick_index(7)", "Port 8", priority=True),
        Binding("9", "pick_index(8)", "Port 9", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.ports_list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="port-dialog"):
            yield Static(app_t(self, "modals.port_select.title", default="Select Serial Port (ESPTUI)"), id="port-title")
            yield Static(app_t(self, "modals.port_select.subtitle", default="Press port number [1-9] or select with Enter:"), id="port-subtitle")
            yield ListView(id="port-list")
            with Horizontal(id="port-actions"):
                yield Button(app_t(self, "modals.port_select.refresh", default="Refresh (R)"), id="btn-refresh-ports", variant="default")
                yield Button(app_t(self, "modals.port_select.cancel", default="Continue without connection (Esc)"), id="btn-cancel-port", variant="warning")

    def on_mount(self):
        self.update_ui_texts()

    def load_ports(self):
        matched, others = get_filtered_ports()
        self.ports_list = matched + others
        list_view = self.query_one("#port-list", ListView)
        list_view.clear()
        if not self.ports_list:
            list_view.append(ListItem(Label(app_t(self, "modals.port_select.no_ports", default="No serial ports detected. Connect board and press 'R'."))))
            return

        for idx, port in enumerate(self.ports_list[:9], start=1):
            is_matched = port in matched
            tag = " [ESP/USB]" if is_matched else ""
            desc = port.description or app_t(self, "modals.port_select.device", default="Serial device")
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

    def update_ui_texts(self):
        try:
            self.query_one("#port-title", Static).update(app_t(self, "modals.port_select.title", default="Select Serial Port (ESPTUI)"))
            self.query_one("#port-subtitle", Static).update(app_t(self, "modals.port_select.subtitle", default="Press port number [1-9] or select with Enter:"))
            self.query_one("#btn-refresh-ports", Button).label = app_t(self, "modals.port_select.refresh", default="Refresh (R)")
            self.query_one("#btn-cancel-port", Button).label = app_t(self, "modals.port_select.cancel", default="Continue without connection (Esc)")
            modal_bindings = {
                "escape": app_t(self, "modals.port_select.close", default="Close"),
                "r": app_t(self, "modals.port_select.refresh_key", default="Refresh"),
                "f3": app_t(self, "footer.language", default="Language"),
            }
            for i in range(1, 10):
                modal_bindings[str(i)] = app_t(self, "modals.port_select.port_key", default=f"Port {i}", num=i)
            update_binding_descriptions(self, modal_bindings)
            if hasattr(self, "refresh_bindings"):
                self.refresh_bindings()
            self.load_ports()
        except Exception:
            pass

    def action_cycle_language(self):
        if hasattr(self.app, "action_cycle_language"):
            self.app.action_cycle_language()
        else:
            self.update_ui_texts()


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
        Binding("escape", "dismiss_modal", "Close", priority=True),
        Binding("enter", "dismiss_modal", "Close", priority=True),
        Binding("f3", "cycle_language", "Language", priority=True),
    ]

    HELP_INFO = """
[b cyan]Panel Navigation:[/]
  [b yellow]Alt+1[/]         Focus Local & Board files panel
  [b yellow]Alt+2[/]         Focus Code Editor
  [b yellow]Alt+3[/]         Focus REPL Console

[b cyan]File Operations:[/]
  [b yellow]Ctrl+N[/]        Create [b green]New file[/]
  [b yellow]F4[/]            [b green]Rename / Save as[/] (rename local or board file)
  [b yellow]Ctrl+S[/]        [b green]Save[/] current file (locally or on board)
  [b yellow]F5[/]            [b green]Run[/] code on board (Paste Mode)
  [b yellow]F6[/]            [b green]Upload[/] file to board memory (ampy put)
  [b yellow]F8[/]            [b red]Stop execution[/] (Ctrl+C interrupt on board)
  [b yellow]F9[/]            Soft reset board (Ctrl+D)

[b cyan]Board Files (ESP32):[/]
  [b yellow]Left Click / Enter[/]  Open & edit file in editor
  [b yellow]Right Click / m[/]     Options menu (Open, Rename, Delete)
  [b yellow]Del (Delete)[/]       Delete selected file from board
  [b yellow]F4[/]                 Rename selected file on board

[b cyan]Tools & Views:[/]
  [b yellow]Ctrl+C[/]        [b green]Copy[/] selection or console log to clipboard
  [b yellow]F1[/] o [b yellow]?[/]        Show this help and shortcuts window
  [b yellow]F2[/] or [b yellow]Ctrl+P[/]   Quick serial port selector
  [b yellow]F3[/]            Switch language (English / Spanish)
  [b yellow]F7[/]            Collapse / expand REPL console
  [b yellow]F10[/]           Collapse / expand files panel
  [b yellow]F11[/]           MicroPython package manager (mip)
  [b yellow]F12[/]           ESP32 firmware flasher (esptool)
  [b yellow]Ctrl+Q[/]        Quit IDE
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(app_t(self, "modals.keybindings.title", default="Keyboard Shortcuts — ESPTUI"), id="help-title")
            yield Static(app_t(self, "modals.keybindings.info", default=self.HELP_INFO.strip()), id="help-text")
            yield Button(app_t(self, "modals.keybindings.close", default="Got it / Close (Esc)"), id="btn-close-help", variant="primary")

    def on_mount(self):
        self.update_ui_texts()

    def action_dismiss_modal(self):
        self.dismiss()

    def update_ui_texts(self):
        try:
            self.query_one("#help-title", Static).update(app_t(self, "modals.keybindings.title", default="Keyboard Shortcuts — ESPTUI"))
            self.query_one("#help-text", Static).update(app_t(self, "modals.keybindings.info", default=self.HELP_INFO.strip()))
            self.query_one("#btn-close-help", Button).label = app_t(self, "modals.keybindings.close", default="Got it / Close (Esc)")
            update_binding_descriptions(self, {
                "escape": app_t(self, "modals.keybindings.close_key", default="Close"),
                "enter": app_t(self, "modals.keybindings.close_key", default="Close"),
                "f3": app_t(self, "footer.language", default="Language"),
            })
            if hasattr(self, "refresh_bindings"):
                self.refresh_bindings()
        except Exception:
            pass

    def action_cycle_language(self):
        if hasattr(self.app, "action_cycle_language"):
            self.app.action_cycle_language()
        else:
            self.update_ui_texts()

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
        Binding("escape", "dismiss_modal", "Cancel", priority=True),
    ]

    def __init__(self, title=None, default_name="sketch.py"):
        super().__init__()
        self.dialog_title = title
        self.default_name = default_name

    def compose(self) -> ComposeResult:
        title = self.dialog_title or app_t(self, "modals.file_name.default_title", default="File Name")
        with Vertical(id="filename-dialog"):
            yield Static(title, id="filename-title")
            placeholder = app_t(self, "modals.file_name.placeholder", default="filename.py")
            yield Input(value=self.default_name, placeholder=placeholder, id="filename-input")
            with Horizontal(id="filename-actions"):
                yield Button(app_t(self, "modals.file_name.accept", default="Accept (Enter)"), id="btn-filename-accept", variant="success")
                yield Button(app_t(self, "modals.file_name.cancel", default="Cancel (Esc)"), id="btn-filename-cancel", variant="warning")

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
        Binding("escape", "dismiss_action('cancel')", "Cancel", priority=True),
        Binding("1", "dismiss_action('open')", "Open", priority=True),
        Binding("2", "dismiss_action('rename')", "Rename", priority=True),
        Binding("3", "dismiss_action('delete')", "Delete", priority=True),
    ]

    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename

    def compose(self) -> ComposeResult:
        with Vertical(id="remote-action-dialog"):
            title = app_t(self, "modals.remote_file_action.title", filename=self.filename, default=f"File on ESP32: [b cyan]{self.filename}[/]")
            yield Static(title, id="remote-action-title")
            with Vertical(id="remote-action-buttons"):
                yield Button(app_t(self, "modals.remote_file_action.open", default="1. Open / Edit in IDE"), id="btn-action-open", variant="success")
                yield Button(app_t(self, "modals.remote_file_action.rename", default="2. Rename on board"), id="btn-action-rename", variant="primary")
                yield Button(app_t(self, "modals.remote_file_action.delete", default="3. Delete from board"), id="btn-action-delete", variant="error")
                yield Button(app_t(self, "modals.remote_file_action.cancel", default="4. Cancel (Esc)"), id="btn-action-cancel")

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
        Binding("escape", "dismiss_modal(False)", "Cancel", priority=True),
    ]

    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-delete-dialog"):
            yield Static(app_t(self, "modals.confirm_delete.title", default="Delete file from board?"), id="confirm-delete-title")
            text = app_t(self, "modals.confirm_delete.text", filename=self.filename, default=f"Permanently delete [b yellow]{self.filename}[/] from flash memory?")
            yield Static(text, id="confirm-delete-text")
            with Horizontal(id="confirm-delete-actions"):
                yield Button(app_t(self, "modals.confirm_delete.confirm", default="Yes, delete"), id="btn-confirm-delete", variant="error")
                yield Button(app_t(self, "modals.confirm_delete.cancel", default="Cancel (Esc)"), id="btn-cancel-delete", variant="primary")

    def action_dismiss_modal(self, confirmed: bool):
        self.dismiss(confirmed)

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "btn-confirm-delete")


CURATED_PACKAGES = [
    ("ssd1306", "I2C/SPI OLED display driver (128x64, 128x32)"),
    ("bme280", "Bosch BME280 temperature, humidity & pressure sensor"),
    ("dht", "DHT11 / DHT22 digital temperature & humidity sensor"),
    ("neopixel", "WS2812 / NeoPixel addressable RGB LED strip driver"),
    ("umqtt.simple", "Lightweight MQTT client for MicroPython"),
    ("umqtt.robust", "Resilient MQTT client with automatic reconnection"),
    ("urequests", "Lightweight HTTP requests client"),
    ("microdot", "Minimal and fast web framework for MicroPython"),
    ("logging", "Standard logging module implementation"),
]

OFFICIAL_ESP32_FIRMWARE_URL = "https://micropython.org/resources/firmware/ESP32_GENERIC-20241129-v1.24.1.bin"


def download_micropython_package(pkg_name: str) -> list[tuple[str, bytes]]:
    """Downloads package files from MicroPython mip index, micropython-lib, or PyPI.
    Returns list of (relative_path_str, file_content_bytes)."""
    headers = {"User-Agent": "ESPTUI/1.0 (Textual-MicroPython-IDE)"}
    pkg_clean = pkg_name.strip()
    files = []

    # 1. Try official mip v2 index: https://micropython.org/pi/v2/package/py/{pkg}/latest.json
    try:
        url = f"https://micropython.org/pi/v2/package/py/{pkg_clean}/latest.json"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        hashes = data.get("hashes", [])
        for rel_path, h in hashes:
            short_h = h[:2]
            f_url = f"https://micropython.org/pi/v2/file/{short_h}/{h}"
            f_req = urllib.request.Request(f_url, headers=headers)
            with urllib.request.urlopen(f_req, timeout=10) as f_resp:
                files.append((rel_path, f_resp.read()))
        if files:
            return files
    except Exception:
        pass

    # 2. Try raw GitHub from micropython-lib
    for folder in ("python-ecosys", "micropython", "python-stdlib"):
        for subpath in (f"{pkg_clean}/{pkg_clean}.py", f"{pkg_clean}.py"):
            gh_url = f"https://raw.githubusercontent.com/micropython/micropython-lib/master/{folder}/{subpath}"
            try:
                gh_req = urllib.request.Request(gh_url, headers=headers)
                with urllib.request.urlopen(gh_req, timeout=8) as gh_resp:
                    content = gh_resp.read()
                filename = subpath.split("/")[-1]
                return [(filename, content)]
            except Exception:
                continue

    # 3. Fallback: PyPI wheels or source archive
    try:
        pypi_url = f"https://pypi.org/pypi/{pkg_clean}/json"
        p_req = urllib.request.Request(pypi_url, headers=headers)
        with urllib.request.urlopen(p_req, timeout=8) as p_resp:
            p_data = json.loads(p_resp.read().decode("utf-8"))
        urls = p_data.get("urls", [])
        wheel = next((u for u in urls if u.get("filename", "").endswith(".whl")), None)
        if wheel:
            w_req = urllib.request.Request(wheel["url"], headers=headers)
            with urllib.request.urlopen(w_req, timeout=15) as w_resp:
                w_bytes = w_resp.read()
            with zipfile.ZipFile(io.BytesIO(w_bytes)) as z:
                for name in z.namelist():
                    if name.endswith(".py") and not name.startswith("__pycache__") and ".dist-info" not in name:
                        files.append((name, z.read(name)))
            if files:
                return files
    except Exception:
        pass

    raise RuntimeError(f"Package '{pkg_clean}' not found on micropython-lib index or PyPI.")


class CuratedPackageItem(ListItem):
    """Elemento para mostrar un paquete curado en el Package Manager."""
    def __init__(self, name: str, desc: str):
        clean_id = "curated-" + name.replace(".", "-")
        super().__init__(Label(f"[b cyan]{name}[/] — {desc}"), id=clean_id)
        self.pkg_name = name


class PackageManagerModal(ModalScreen[bool]):
    """Modal para buscar e instalar paquetes MicroPython en la placa."""
    DEFAULT_CSS = """
    PackageManagerModal { align: center middle; background: $background; }
    #pkg-dialog {
        width: 76;
        height: auto;
        max-height: 32;
        border: heavy cyan;
        background: $surface;
        padding: 1 2;
    }
    #pkg-title { text-align: center; color: cyan; text-style: bold; margin-bottom: 1; }
    #pkg-input-row { height: 3; margin-bottom: 1; }
    #pkg-input { width: 1fr; margin-right: 1; }
    #btn-pkg-install { width: 18; }
    #pkg-curated-title { color: $text-muted; margin-bottom: 1; }
    #pkg-list { height: 9; border: solid gray; margin-bottom: 1; }
    #pkg-status { height: auto; min-height: 1; color: yellow; margin-bottom: 1; }
    #pkg-actions { height: 3; align-horizontal: right; }
    #btn-pkg-close { width: 18; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", priority=True),
        Binding("f3", "cycle_language", "Language", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="pkg-dialog"):
            yield Static(app_t(self, "modals.package_manager.title", default="MicroPython Package Manager (mip)"), id="pkg-title")
            with Horizontal(id="pkg-input-row"):
                yield Input(placeholder=app_t(self, "modals.package_manager.placeholder", default="Package name (e.g. ssd1306, bme280, dht)..."), id="pkg-input")
                yield Button(app_t(self, "modals.package_manager.install_btn", default="Install (Enter)"), id="btn-pkg-install", variant="success")
            yield Static(app_t(self, "modals.package_manager.curated_title", default="Popular Packages (Click to select):"), id="pkg-curated-title")
            with ListView(id="pkg-list"):
                for name, desc in CURATED_PACKAGES:
                    yield CuratedPackageItem(name, desc)
            yield Static(app_t(self, "modals.package_manager.status_ready", default="Enter package name or choose from list."), id="pkg-status")
            with Horizontal(id="pkg-actions"):
                yield Button(app_t(self, "modals.package_manager.close_btn", default="Close (Esc)"), id="btn-pkg-close", variant="primary")

    def on_mount(self):
        self.update_ui_texts()
        self.query_one("#pkg-input", Input).focus()

    def action_dismiss_modal(self):
        self.dismiss(False)

    def action_cycle_language(self):
        if hasattr(self.app, "action_cycle_language"):
            self.app.action_cycle_language()
        else:
            self.update_ui_texts()

    def update_ui_texts(self):
        try:
            self.query_one("#pkg-title", Static).update(app_t(self, "modals.package_manager.title", default="MicroPython Package Manager (mip)"))
            self.query_one("#pkg-input", Input).placeholder = app_t(self, "modals.package_manager.placeholder", default="Package name (e.g. ssd1306, bme280, dht)...")
            self.query_one("#btn-pkg-install", Button).label = app_t(self, "modals.package_manager.install_btn", default="Install (Enter)")
            self.query_one("#pkg-curated-title", Static).update(app_t(self, "modals.package_manager.curated_title", default="Popular Packages (Click to select):"))
            self.query_one("#btn-pkg-close", Button).label = app_t(self, "modals.package_manager.close_btn", default="Close (Esc)")
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected):
        if isinstance(event.item, CuratedPackageItem):
            inp = self.query_one("#pkg-input", Input)
            inp.value = event.item.pkg_name
            inp.focus()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "pkg-input":
            self.start_install()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-pkg-install":
            self.start_install()
        elif event.button.id == "btn-pkg-close":
            self.dismiss(False)

    def set_status(self, text: str):
        try:
            self.query_one("#pkg-status", Static).update(text)
        except Exception:
            pass

    def start_install(self):
        pkg_name = self.query_one("#pkg-input", Input).value.strip()
        if not pkg_name:
            return
        if not getattr(self.app, "port", None):
            self.set_status(app_t(self, "modals.package_manager.no_board", default="Connect to a board first to install packages."))
            return

        btn = self.query_one("#btn-pkg-install", Button)
        btn.disabled = True
        self.set_status(app_t(self, "modals.package_manager.status_downloading", pkg=pkg_name, default=f"Downloading {pkg_name} from micropython-lib..."))

        threading.Thread(target=self._install_worker, args=(pkg_name,), daemon=True).start()

    def _install_worker(self, pkg_name: str):
        try:
            files = download_micropython_package(pkg_name)
            self.app.call_from_thread(
                self.set_status,
                app_t(self, "modals.package_manager.status_uploading", pkg=pkg_name, default=f"Uploading {pkg_name} files to /lib on board...")
            )
            with self.app.serial_lock:
                if self.app.ser and self.app.ser.is_open:
                    try:
                        self.app.ser.write(b"\x03\x03")
                        time.sleep(0.15)
                        self.app.ser.reset_input_buffer()
                    except Exception:
                        pass
                    self.app.ser.close()
                time.sleep(0.25)
                try:
                    try:
                        self.app.ampy("mkdir", "lib")
                    except Exception:
                        pass

                    for rel_path, content in files:
                        clean_rel = rel_path.strip("/")
                        parts = clean_rel.split("/")
                        if len(parts) > 1:
                            sub_dir = "lib"
                            for part in parts[:-1]:
                                sub_dir = f"{sub_dir}/{part}"
                                try:
                                    self.app.ampy("mkdir", sub_dir)
                                except Exception:
                                    pass

                        with tempfile.TemporaryDirectory(prefix="esp32-mip-") as tmpdir:
                            tmp_file = Path(tmpdir) / parts[-1]
                            tmp_file.write_bytes(content)
                            dest_path = f"lib/{clean_rel}"
                            self.app.ampy("put", str(tmp_file), dest_path)
                finally:
                    if not self.app.stopping.is_set():
                        time.sleep(0.2)
                        try:
                            self.app.open_serial()
                        except Exception:
                            pass

            success_msg = app_t(self, "modals.package_manager.status_installed", pkg=pkg_name, default=f"Installed {pkg_name} successfully to /lib!")
            self.app.call_from_thread(self.set_status, success_msg)
            self.app.call_from_thread(
                self.app.serial_log.write,
                app_t(self, "messages.package_installed", pkg=pkg_name, default=f"Package installed to board: {pkg_name}")
            )
            self.app.call_from_thread(self.app.start_board_task, "list", None, None, True)
        except Exception as error:
            err_msg = app_t(self, "modals.package_manager.status_error", error=str(error), default=f"Installation error: {error}")
            self.app.call_from_thread(self.set_status, err_msg)
        finally:
            def reenable():
                try:
                    self.query_one("#btn-pkg-install", Button).disabled = False
                except Exception:
                    pass
            self.app.call_from_thread(reenable)


class FirmwareFlashModal(ModalScreen[bool]):
    """Modal para flashear firmware MicroPython en ESP32 usando esptool."""
    DEFAULT_CSS = """
    FirmwareFlashModal { align: center middle; background: $background; }
    #flasher-dialog {
        width: 78;
        height: auto;
        max-height: 34;
        border: heavy cyan;
        background: $surface;
        padding: 1 2;
    }
    #flasher-title { text-align: center; color: cyan; text-style: bold; margin-bottom: 1; }
    #flasher-port-row { height: 3; margin-bottom: 1; align-vertical: middle; }
    #flasher-port-label { width: 1fr; color: yellow; }
    #flasher-baud-label { width: auto; margin-right: 1; color: $text-muted; }
    #flasher-baud-select { width: 18; }
    #flasher-bin-row { height: 3; margin-bottom: 1; }
    #flasher-bin-input { width: 1fr; }
    #btn-flasher-download { width: auto; margin-bottom: 1; }
    #flasher-erase-cb { margin-bottom: 1; }
    #flasher-progress { width: 100%; margin-bottom: 1; }
    #flasher-status { height: auto; min-height: 1; color: yellow; margin-bottom: 1; }
    #flasher-actions { height: 3; }
    #flasher-actions Button { margin-right: 1; }
    """
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", priority=True),
        Binding("f3", "cycle_language", "Language", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="flasher-dialog"):
            yield Static(app_t(self, "modals.flasher.title", default="ESP32 Firmware Flasher (esptool)"), id="flasher-title")
            with Horizontal(id="flasher-port-row"):
                port_str = getattr(self.app, "port", None) or "None"
                yield Static(app_t(self, "modals.flasher.port_label", port=port_str, default=f"Port: {port_str}"), id="flasher-port-label")
                yield Static(app_t(self, "modals.flasher.baud_label", default="Baudrate:"), id="flasher-baud-label")
                yield Select([("460800", "460800"), ("115200", "115200")], value="460800", allow_blank=False, id="flasher-baud-select")
            with Horizontal(id="flasher-bin-row"):
                yield Input(placeholder=app_t(self, "modals.flasher.bin_path_placeholder", default="Path to MicroPython firmware .bin file..."), id="flasher-bin-input")
            yield Button(app_t(self, "modals.flasher.download_btn", default="Download Official ESP32 Firmware"), id="btn-flasher-download", variant="primary")
            yield Checkbox(app_t(self, "modals.flasher.erase_first", default="Erase entire flash before writing (Recommended)"), value=True, id="flasher-erase-cb")
            yield ProgressBar(id="flasher-progress", show_eta=False, total=100)
            yield Static(app_t(self, "modals.flasher.status_idle", default="Select firmware .bin file and click Write Flash."), id="flasher-status")
            with Horizontal(id="flasher-actions"):
                yield Button(app_t(self, "modals.flasher.flash_btn", default="Write Flash"), id="btn-flasher-flash", variant="success")
                yield Button(app_t(self, "modals.flasher.erase_only_btn", default="Erase Flash Only"), id="btn-flasher-erase", variant="warning")
                yield Button(app_t(self, "modals.flasher.close_btn", default="Close (Esc)"), id="btn-flasher-close")

    def on_mount(self):
        self.update_ui_texts()

    def action_dismiss_modal(self):
        self.dismiss(False)

    def action_cycle_language(self):
        if hasattr(self.app, "action_cycle_language"):
            self.app.action_cycle_language()
        else:
            self.update_ui_texts()

    def update_ui_texts(self):
        try:
            self.query_one("#flasher-title", Static).update(app_t(self, "modals.flasher.title", default="ESP32 Firmware Flasher (esptool)"))
            port_str = getattr(self.app, "port", None) or "None"
            self.query_one("#flasher-port-label", Static).update(app_t(self, "modals.flasher.port_label", port=port_str, default=f"Port: {port_str}"))
            self.query_one("#flasher-baud-label", Static).update(app_t(self, "modals.flasher.baud_label", default="Baudrate:"))
            self.query_one("#flasher-bin-input", Input).placeholder = app_t(self, "modals.flasher.bin_path_placeholder", default="Path to MicroPython firmware .bin file...")
            self.query_one("#btn-flasher-download", Button).label = app_t(self, "modals.flasher.download_btn", default="Download Official ESP32 Firmware")
            self.query_one("#flasher-erase-cb", Checkbox).label = app_t(self, "modals.flasher.erase_first", default="Erase entire flash before writing (Recommended)")
            self.query_one("#btn-flasher-flash", Button).label = app_t(self, "modals.flasher.flash_btn", default="Write Flash")
            self.query_one("#btn-flasher-erase", Button).label = app_t(self, "modals.flasher.erase_only_btn", default="Erase Flash Only")
            self.query_one("#btn-flasher-close", Button).label = app_t(self, "modals.flasher.close_btn", default="Close (Esc)")
        except Exception:
            pass

    def set_status(self, text: str):
        try:
            self.query_one("#flasher-status", Static).update(text)
        except Exception:
            pass

    def set_progress(self, percent: float):
        try:
            bar = self.query_one("#flasher-progress", ProgressBar)
            bar.update(progress=percent)
        except Exception:
            pass

    def set_buttons_disabled(self, disabled: bool):
        for btn_id in ("#btn-flasher-download", "#btn-flasher-flash", "#btn-flasher-erase", "#btn-flasher-close"):
            try:
                self.query_one(btn_id, Button).disabled = disabled
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-flasher-download":
            self.start_download_firmware()
        elif event.button.id == "btn-flasher-flash":
            self.start_flash(erase_only=False)
        elif event.button.id == "btn-flasher-erase":
            self.start_flash(erase_only=True)
        elif event.button.id == "btn-flasher-close":
            self.dismiss(False)

    def start_download_firmware(self):
        self.set_buttons_disabled(True)
        self.set_status(app_t(self, "modals.flasher.status_downloading", default="Downloading MicroPython firmware..."))
        self.set_progress(0)
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            fw_dir = Path.home() / ".esptui" / "firmware"
            fw_dir.mkdir(parents=True, exist_ok=True)
            dest_file = fw_dir / "ESP32_GENERIC-v1.24.1.bin"

            req = urllib.request.Request(OFFICIAL_ESP32_FIRMWARE_URL, headers={"User-Agent": "ESPTUI/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_bytes = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536
                with open(dest_file, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes > 0:
                            pct = round((downloaded / total_bytes) * 100, 1)
                            self.app.call_from_thread(self.set_progress, pct)

            self.app.call_from_thread(self.set_progress, 100)
            def update_input():
                try:
                    self.query_one("#flasher-bin-input", Input).value = str(dest_file)
                except Exception:
                    pass
            self.app.call_from_thread(update_input)
            done_msg = app_t(self, "modals.flasher.status_downloaded", path=str(dest_file), default=f"Downloaded firmware to: {dest_file}")
            self.app.call_from_thread(self.set_status, done_msg)
        except Exception as error:
            err_msg = app_t(self, "modals.flasher.status_error", error=str(error), default=f"Flashing error: {error}")
            self.app.call_from_thread(self.set_status, err_msg)
        finally:
            self.app.call_from_thread(self.set_buttons_disabled, False)

    def start_flash(self, erase_only: bool = False):
        port = getattr(self.app, "port", None)
        if not port:
            self.set_status(app_t(self, "modals.flasher.no_port", default="Select a valid serial port first."))
            return

        bin_path = ""
        if not erase_only:
            bin_path = self.query_one("#flasher-bin-input", Input).value.strip()
            if not bin_path or not Path(bin_path).is_file():
                self.set_status(app_t(self, "modals.flasher.file_not_found", path=bin_path, default=f"Firmware .bin file not found: {bin_path}"))
                return

        erase_first = self.query_one("#flasher-erase-cb", Checkbox).value if not erase_only else False
        baud = str(self.query_one("#flasher-baud-select", Select).value or "460800")

        self.set_buttons_disabled(True)
        self.set_progress(0)
        threading.Thread(
            target=self._flash_worker,
            args=(port, baud, bin_path, erase_first, erase_only),
            daemon=True
        ).start()

    def _flash_worker(self, port: str, baud: str, bin_path: str, erase_first: bool, erase_only: bool):
        try:
            self.app.call_from_thread(
                self.app.serial_log.write,
                app_t(self, "messages.flashing_started", port=port, default=f"Flashing firmware to {port}...")
            )
            with self.app.serial_lock:
                if self.app.ser and self.app.ser.is_open:
                    try:
                        self.app.ser.write(b"\x03\x03")
                        time.sleep(0.15)
                    except Exception:
                        pass
                    self.app.ser.close()
                time.sleep(0.3)

                python_bin = sys.executable

                if erase_first or erase_only:
                    self.app.call_from_thread(
                        self.set_status,
                        app_t(self, "modals.flasher.status_erasing", port=port, default=f"Erasing flash on {port}...")
                    )
                    erase_cmd = [python_bin, "-m", "esptool", "--port", port, "--baud", baud, "erase_flash"]
                    proc = subprocess.run(erase_cmd, capture_output=True, text=True, timeout=60)
                    if proc.returncode != 0:
                        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "esptool erase_flash failed")
                    self.app.call_from_thread(self.set_progress, 50 if not erase_only else 100)

                if not erase_only:
                    self.app.call_from_thread(
                        self.set_status,
                        app_t(self, "modals.flasher.status_flashing", port=port, default=f"Writing firmware to {port}...")
                    )
                    flash_cmd = [
                        python_bin, "-m", "esptool",
                        "--chip", "esp32",
                        "--port", port,
                        "--baud", baud,
                        "write_flash",
                        "-z", "0x1000",
                        str(bin_path)
                    ]
                    proc = subprocess.Popen(flash_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in iter(proc.stdout.readline, ''):
                        if not line:
                            break
                        if "%" in line:
                            try:
                                pct_part = line.split("(")[-1].split("%")[0].strip()
                                pct = float(pct_part)
                                if erase_first:
                                    scaled = 50 + (pct * 0.5)
                                    self.app.call_from_thread(self.set_progress, scaled)
                                else:
                                    self.app.call_from_thread(self.set_progress, pct)
                            except Exception:
                                pass
                    proc.wait(timeout=120)
                    if proc.returncode != 0:
                        raise RuntimeError(f"esptool write_flash exited with code {proc.returncode}")

                self.app.call_from_thread(self.set_progress, 100)
                done_msg = app_t(self, "modals.flasher.status_done", default="Flashing completed successfully! Reset board to start MicroPython.")
                self.app.call_from_thread(self.set_status, done_msg)
                self.app.call_from_thread(
                    self.app.serial_log.write,
                    app_t(self, "messages.flashing_success", port=port, default=f"Firmware flashed successfully to {port}.")
                )
        except Exception as error:
            err_msg = app_t(self, "modals.flasher.status_error", error=str(error), default=f"Flashing error: {error}")
            self.app.call_from_thread(self.set_status, err_msg)
        finally:
            if not self.app.stopping.is_set():
                time.sleep(0.3)
                try:
                    self.app.open_serial()
                except Exception:
                    pass
            self.app.call_from_thread(self.set_buttons_disabled, False)
            self.app.call_from_thread(self.app.start_board_task, "list", None, None, True)


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
        height: 3;
        background: $surface;
        align-horizontal: right;
        align-vertical: middle;
        padding: 0 1;
    }
    #top-bar-lang-label {
        color: $text-muted;
        margin-right: 1;
        width: auto;
        height: 1;
        margin-top: 1;
    }
    #lang-select {
        width: 20;
        height: 3;
    }
    #board-stats {
        height: auto;
        color: $text-muted;
        background: $surface;
        padding: 0 1;
        margin-bottom: 1;
        text-align: center;
    }
    """
    BINDINGS = [
        # Panel navigation (hidden from footer for space)
        Binding("alt+1", "focus_panel('files')", "Files", priority=True, show=False),
        Binding("alt+2", "focus_panel('editor')", "Editor", priority=True, show=False),
        Binding("alt+3", "focus_panel('console')", "Console", priority=True, show=False),
        Binding("1", "focus_panel('files')", "Files", priority=False, show=False),
        Binding("2", "focus_panel('editor')", "Editor", priority=False, show=False),
        Binding("3", "focus_panel('console')", "Console", priority=False, show=False),
        Binding("ctrl+c", "copy_console", "Copy console", priority=False, show=False),

        # File, editor and board operations
        Binding("ctrl+n", "new_file", "New file", priority=True),
        Binding("f4", "rename_file", "Rename", priority=True),
        Binding("ctrl+s", "save_file", "Save", priority=True),
        Binding("f5", "run_code", "Run", priority=True),
        Binding("f6", "upload_file", "Upload", priority=True),
        Binding("f8", "stop_execution", "Stop", priority=True),
        Binding("f9", "send_soft_reset", "Reset", priority=True),

        # Tools and modals
        Binding("f1", "show_help", "Help", priority=True),
        Binding("question_mark", "show_help", "Help", priority=False, show=False),
        Binding("f2", "select_port", "Ports", priority=True),
        Binding("ctrl+p", "select_port", "Ports", priority=True, show=False),
        Binding("f3", "cycle_language", "Language", priority=True, show=True),
        Binding("f11", "open_package_manager", "Packages", priority=True),
        Binding("f12", "open_firmware_flasher", "Flash", priority=True),

        # Panels and quit
        Binding("f7", "toggle_console", "Console", priority=True, show=False),
        Binding("f10", "toggle_sidebar", "Files", priority=True, show=False),
        Binding("ctrl+q", "quit", "Quit", priority=True),
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
                yield Static(self.t("top_bar.language_label", default="Language:"), id="top-bar-lang-label")
                yield Select(
                    self.i18n.get_language_options(),
                    value=self.i18n.current_lang,
                    id="lang-select",
                    allow_blank=False,
                )
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static(self.t("sidebar.title", default="Local & board files [Alt+1]"), id="sidebar-title", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield DirectoryTree(str(self.user_home), id="local-files")
                    yield Static(self.t("sidebar.board_disconnected", default="ESP32: disconnected"), id="board-title", classes="title")
                    yield Static(self.t("sidebar.stats_disconnected", default="RAM: -- | Flash: -- | CPU: --"), id="board-stats")
                    yield ListView(id="esp32-files")
                    yield Button(self.t("sidebar.refresh_board", default="Refresh board"), id="refresh-esp32")
                yield Static(self.t("sidebar.collapsed_label", default="F\nI\nL\nE\nS"), classes="collapsed-label")
            with Vertical(id="editor-pane"):
                yield Static(self.t("editor.title", filename=self.current_file.name, default=f"Code editor [Alt+2]: {self.current_file.name}"), id="editor-title", classes="title")
                yield TextArea.code_editor(
                    self.t("editor.default_code", default="# MicroPython\nprint('Hello ESP32')\n"),
                    language="python", theme=self.config.get("theme", "monokai"), id="code-editor",
                )
                with Horizontal(id="editor-buttons"):
                    yield Button(self.t("editor.save", default="Save (Ctrl+S)"), id="save-btn", variant="success")
                    yield Button(self.t("editor.run", default="Run (F5)"), id="send-btn", variant="primary")
                    yield Button(self.t("editor.upload", default="Upload (F6)"), id="upload-btn", variant="warning")
                    yield Button(self.t("editor.stop", default="Stop (F8)"), id="stop-btn", variant="error")
            with Vertical(id="console-pane"):
                yield Static(self.t("console.title", default="Serial REPL console [Alt+3]"), id="console-title", classes="title hideable")
                with Vertical(classes="panel-content hideable"):
                    yield ConsoleLog(id="serial-log", markup=False, highlight=False, max_lines=3000)
                    with Horizontal(id="console-actions"):
                        yield Button(self.t("console.copy", default="Copy (Ctrl+C)"), id="btn-copy-console")
                        yield Button(self.t("console.clear", default="Clear"), id="btn-clear-console")
                    yield Input(placeholder=self.t("console.placeholder", default="REPL command..."), id="serial-input")
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
            if event.value != self.i18n.current_lang:
                self.action_change_language(str(event.value))

    def action_change_language(self, lang_code: str):
        if not self.i18n.set_language(lang_code):
            return
        self.config["lang"] = lang_code
        try:
            cfg_path = Path.home() / ".esptui" / "config.json"
            if cfg_path.exists():
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg_data, dict):
                    cfg_data["lang"] = lang_code
                    cfg_path.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass
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
                self.t("top_bar.language_label", default="Language:")
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
                if hasattr(self, "board_stats_text") and self.board_stats_text:
                    self.query_one("#board-stats", Static).update(self.board_stats_text)
                else:
                    self.query_one("#board-stats", Static).update(
                        self.t("sidebar.stats_loading", default="Telemetry: reading board stats...")
                    )
            else:
                self.query_one("#board-title", Static).update(
                    self.t("sidebar.board_disconnected", default="ESP32: disconnected")
                )
                self.query_one("#board-stats", Static).update(
                    self.t("sidebar.stats_disconnected", default="RAM: -- | Flash: -- | CPU: --")
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
            "alt+1": self.t("footer.files", default="Files"),
            "alt+2": self.t("footer.editor", default="Editor"),
            "alt+3": self.t("footer.console", default="Console"),
            "ctrl+c": self.t("footer.copy_console", default="Copy console"),
            "ctrl+n": self.t("footer.new_file", default="New file"),
            "f4": self.t("footer.rename", default="Rename"),
            "ctrl+s": self.t("footer.save", default="Save"),
            "f5": self.t("footer.run", default="Run"),
            "f6": self.t("footer.upload", default="Upload"),
            "f8": self.t("footer.stop", default="Stop"),
            "f9": self.t("footer.reset", default="Reset"),
            "f1": self.t("footer.help", default="Help"),
            "f2": self.t("footer.ports", default="Ports"),
            "f3": self.t("footer.language", default="Language"),
            "f11": self.t("footer.packages", default="Packages"),
            "f12": self.t("footer.flash", default="Flash"),
            "ctrl+q": self.t("footer.quit", default="Quit"),
        }
        for target in [self, self.screen]:
            update_binding_descriptions(target, bindings_map)
        try:
            self.screen.refresh_bindings()
        except Exception:
            pass
        try:
            footer = self.query_one(Footer)
            if hasattr(footer, "refresh_bindings"):
                footer.refresh_bindings()
            footer.refresh(recompose=True)
        except Exception:
            pass

        try:
            if hasattr(self.screen, "update_ui_texts") and self.screen is not self:
                self.screen.update_ui_texts()
        except Exception:
            pass

    def action_show_help(self):
        self.push_screen(KeybindingsHelpModal())

    def action_open_package_manager(self):
        self.push_screen(PackageManagerModal())

    def action_open_firmware_flasher(self):
        self.push_screen(FirmwareFlashModal())

    def action_select_port(self):
        if isinstance(self.screen, PortSelectModal):
            return

        def on_port_selected(selected_port):
            if selected_port:
                self.connect_to_port(selected_port)
            else:
                self.serial_log.write(self.t("messages.no_port_working", default="Working without connected port. Use Ctrl+P to select one."))

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
            self.serial_log.write(self.t("messages.connection_error", port=port_device, error=error, default=f"Connection to {port_device}: {error}"))

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
                self.log_from_thread(f"Serial read: {error}")
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
                   or f"ampy exited with code {result.returncode}")
            last_error = err
            if any(msg in err for msg in ("Permission denied", "could not open port", "Device or resource busy")):
                time.sleep(0.3)
                continue
            raise RuntimeError(err)
        raise RuntimeError(last_error or "ampy could not access serial port after several attempts")

    def get_busy_screen(self):
        return BusyScreen()

    def start_board_task(self, operation, remote_filename=None, new_filename=None, force=False):
        if self.busy and not force:
            self.serial_log.write(self.t("messages.wait_busy", default="Wait for current operation to finish."))
            return
        if not self.port:
            self.serial_log.write(self.t("messages.select_port_first", default="Select a port with Ctrl+P to perform board operations."))
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
                    messages.append(self.t("messages.code_sent", default="Code sent via Paste Mode; check REPL output."))
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
                            messages.append(self.t("messages.uploaded", filename=dest_filename, dest_filename=dest_filename, default=f"File uploaded to board: {dest_filename}"))
                        elif operation == "get" and remote_filename:
                            clean_remote = remote_filename.lstrip("/") or "main.py"
                            raw = self.ampy("get", clean_remote)
                            loaded_remote = (clean_remote, raw)
                            messages.append(self.t("messages.downloaded", filename=clean_remote, clean_remote=clean_remote, default=f"Board file downloaded: {clean_remote}"))
                        elif operation == "rm" and remote_filename:
                            clean_remote = remote_filename.lstrip("/")
                            self.ampy("rm", clean_remote)
                            messages.append(self.t("messages.deleted", filename=clean_remote, clean_remote=clean_remote, default=f"File deleted from board: {clean_remote}"))
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
                                messages.append(self.t("messages.renamed", old=old_remote, new=new_remote, old_remote=old_remote, new_remote=new_remote, default=f"File renamed on board: {old_remote} -> {new_remote}"))
                                if self.is_remote_file and self.current_remote_file == old_remote:
                                    self.current_remote_file = new_remote
                        files = [f for f in self.ampy("ls").splitlines() if f.strip() and f.strip() != "/"]
                        stats_text = None
                        if operation == "list":
                            try:
                                stats_script = "import gc,os,machine\ngc.collect()\nprint('__STATS__:'+str(gc.mem_free())+':'+str(os.statvfs('/')[0]*os.statvfs('/')[3])+':'+str(machine.freq()))"
                                with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
                                    tf.write(stats_script)
                                    tf_path = tf.name
                                try:
                                    raw_stats = self.ampy("run", tf_path)
                                    for line in raw_stats.splitlines():
                                        if line.startswith("__STATS__:"):
                                            parts = line.strip().split(":")
                                            if len(parts) == 4:
                                                ram_b = int(parts[1])
                                                flash_b = int(parts[2])
                                                freq_hz = int(parts[3])
                                                ram_kb = round(ram_b / 1024, 1)
                                                flash_mb = round(flash_b / (1024 * 1024), 2)
                                                cpu_mhz = int(freq_hz // 1000000)
                                                stats_text = self.t(
                                                    "sidebar.stats_format",
                                                    ram_free_kb=ram_kb,
                                                    flash_free_mb=flash_mb,
                                                    cpu_mhz=cpu_mhz,
                                                    default=f"RAM: {ram_kb} KB | Flash: {flash_mb} MB | CPU: {cpu_mhz} MHz",
                                                )
                                                break
                                finally:
                                    Path(tf_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                    finally:
                        if not self.stopping.is_set():
                            time.sleep(0.25)
                            try:
                                self.open_serial()
                                messages.append(self.t("messages.reconnected", port=self.port, default=f"Console reconnected: {self.port}"))
                            except Exception as error:
                                messages.append(self.t("messages.reconnect_failed", error=error, default=f"Could not reconnect: {error}"))
        except Exception as error:
            messages.append(self.t("messages.operation_error", operation=operation, error=error, default=f"Operation {operation}: {error}"))
        finally:
            if not self.stopping.is_set():
                try:
                    self.call_from_thread(self.finish_board_task, files, messages, loaded_remote, stats_text)
                except RuntimeError:
                    pass

    async def finish_board_task(self, files, messages, loaded_remote=None, stats_text=None):
        try:
            if stats_text:
                self.board_stats_text = stats_text
                try:
                    self.query_one("#board-stats", Static).update(stats_text)
                except Exception:
                    pass
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
                self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=fname, default=f"Code editor [Alt+2] (ESP32): {fname}"))
                self.editor.focus()
            elif self.is_remote_file and self.current_remote_file:
                self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=self.current_remote_file, default=f"Code editor [Alt+2] (ESP32): {self.current_remote_file}"))
            elif not self.is_remote_file:
                self.query_one("#editor-title", Static).update(self.t("editor.title", filename=self.current_file.name, default=f"Code editor [Alt+2]: {self.current_file.name}"))
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
            self.serial_log.write(self.t("messages.port_busy", default="Port busy with another operation."))
            return False
        try:
            with self.serial_lock:
                if not self.ser or not self.ser.is_open:
                    raise RuntimeError(self.t("messages.not_connected", default="Serial console is not connected"))
                self.ser.write(payload)
            return True
        except Exception as error:
            self.serial_log.write(f"Serial write: {error}")
            return False

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "serial-input":
            if self.write_repl((event.value + "\r\n").encode("utf-8")):
                self.serial_log.write(f">>> {event.value}")
                event.input.value = ""

    def action_stop_execution(self):
        """Stop all execution: sends double Ctrl+C interrupt to REPL."""
        self.serial_log.write(self.t("messages.stopping", default="[STOP] Stopping execution on board (Ctrl+C)..."))
        self.write_repl(b"\x03\x03")

    def action_send_interrupt(self):
        self.action_stop_execution()

    def action_send_soft_reset(self):
        self.serial_log.write(self.t("messages.resetting", default="[RESET] Soft reset (Ctrl+D)..."))
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
            self.query_one("#editor-title", Static).update(self.t("editor.title", filename=path.name, default=f"Code editor [Alt+2]: {path.name}"))
            self.serial_log.write(self.t("messages.local_opened", filename=path.name, default=f"Opened local file: {path.name}"))
        except Exception as error:
            self.serial_log.write(f"Open file: {error}")

    def on_list_view_selected(self, event: ListView.Selected):
        """When selecting a remote board file, stop running script and download immediately."""
        if event.list_view.id == "esp32-files" and event.item:
            target_file = getattr(event.item, "filename", None)
            if not target_file:
                labels = event.item.query(Label)
                if labels:
                    target_file = str(labels.first().render()).strip()
            if target_file and target_file != "/":
                self.serial_log.write(self.t("messages.downloading", filename=target_file, default=f"Stopping execution and downloading {target_file}..."))
                self.start_board_task("get", remote_filename=target_file, force=True)

    def action_remote_file_context(self, target_file: str):
        """Open context menu modal for board file."""
        if not target_file or target_file == "/":
            return

        def on_action_chosen(action):
            if action == "open":
                self.serial_log.write(self.t("messages.downloading", filename=target_file, default=f"Stopping execution and downloading {target_file}..."))
                self.start_board_task("get", remote_filename=target_file, force=True)
            elif action == "rename":
                self.action_rename_remote_file(target_file)
            elif action == "delete":
                self.action_delete_remote_file(target_file)

        self.push_screen(RemoteFileActionModal(filename=target_file), on_action_chosen)

    def action_rename_remote_file(self, target_file: str):
        """Modal to rename an existing file on board."""
        def on_rename_entered(new_name):
            if new_name and new_name != target_file:
                if not new_name.endswith(".py"):
                    new_name += ".py"
                self.serial_log.write(self.t("messages.renaming", old=target_file, new=new_name, default=f"Renaming {target_file} to {new_name}..."))
                self.start_board_task("rename", remote_filename=target_file, new_filename=new_name, force=True)

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_rename_esp32", filename=target_file, default=f"Rename on ESP32: {target_file}"), default_name=target_file), on_rename_entered)

    def action_delete_remote_file(self, target_file: str):
        """Confirmation modal to delete a file from board."""
        def on_confirm_delete(confirmed):
            if confirmed:
                self.serial_log.write(self.t("messages.deleting", filename=target_file, default=f"Deleting {target_file} from board..."))
                self.start_board_task("rm", remote_filename=target_file, force=True)

        self.push_screen(ConfirmDeleteModal(filename=target_file), on_confirm_delete)

    def on_key(self, event: events.Key):
        """Context key support when board list is focused."""
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
            # If editing a downloaded board file, saving uploads it back
            self.start_board_task("upload", remote_filename=self.current_remote_file)
            return
        try:
            self.current_file.write_text(self.editor.text, encoding="utf-8")
            self.serial_log.write(self.t("messages.saved_local", path=str(self.current_file), default=f"Saved locally: {self.current_file}"))
        except Exception as error:
            self.serial_log.write(f"Save file: {error}")

    def action_new_file(self):
        """Create a new empty file."""
        def on_name_entered(filename):
            if filename:
                if not filename.endswith(".py"):
                    filename += ".py"
                self.current_file = self.user_home / filename
                self.is_remote_file = False
                self.current_remote_file = None
                self.editor.load_text(self.t("editor.new_script_code", default="# MicroPython\nprint('New script')\n"))
                self.query_one("#editor-title", Static).update(self.t("editor.title", filename=filename, default=f"Code editor [Alt+2]: {filename}"))
                self.serial_log.write(self.t("messages.new_file_created", filename=filename, default=f"New local file: {filename}"))
                self.editor.focus()

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_new", default="Create New File"), default_name="sketch.py"), on_name_entered)

    def action_rename_file(self):
        """Rename active file or define destination name for board."""
        current_name = self.current_remote_file if self.is_remote_file else self.current_file.name
        def on_name_entered(filename):
            if filename:
                if not filename.endswith(".py"):
                    filename += ".py"
                if self.is_remote_file:
                    self.current_remote_file = filename
                    self.query_one("#editor-title", Static).update(self.t("editor.title_esp32", filename=filename, default=f"Code editor [Alt+2] (ESP32): {filename}"))
                else:
                    self.current_file = self.current_file.parent / filename
                    self.query_one("#editor-title", Static).update(self.t("editor.title", filename=filename, default=f"Code editor [Alt+2]: {filename}"))
                self.serial_log.write(self.t("messages.active_file_changed", filename=filename, default=f"Active file is now: {filename}"))
                self.editor.focus()

        self.push_screen(FileNameModal(title=self.t("modals.file_name.title_rename", default="Rename / Save As"), default_name=current_name), on_name_entered)

    def action_copy_console(self):
        """Copy user selection or all console log to system clipboard."""
        selected = self.screen.get_selected_text()
        if selected:
            copy_text_to_system_clipboard(self, selected)
            self.serial_log.write(self.t("messages.clipboard_selected", default="[CLIPBOARD] Selected text copied."))
        else:
            lines = [str(getattr(l, "text", l)) for l in self.serial_log.lines]
            text = "\n".join(lines).strip()
            if text:
                copy_text_to_system_clipboard(self, text)
                self.serial_log.write(self.t("messages.clipboard_console", default="[CLIPBOARD] Console copied to clipboard."))
            else:
                self.serial_log.write(self.t("messages.clipboard_empty", default="[CLIPBOARD] No text to copy."))

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
