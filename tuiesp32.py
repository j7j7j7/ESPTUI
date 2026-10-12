"""Installed CLI (tuiesp32); main.py remains the reusable TUI base."""
import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path

from platformdirs import user_config_path
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
import serial.tools.list_ports
import main as base

VERSION = "0.2.0"
LOGO = r"""███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝"""
DEFAULTS = {"port": "AUTO", "baudrate": 115200, "theme": "monokai"}


def config_path():
    return user_config_path("tuiesp32", appauthor=False) / "config.json"


def read_config(path):
    result = DEFAULTS.copy()
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("La configuracion debe contener un objeto JSON")
        result.update(loaded)
    result["baudrate"] = int(result["baudrate"])
    if result["baudrate"] <= 0:
        raise ValueError("baudrate debe ser positivo")
    if not isinstance(result["port"], str) or not result["port"].strip():
        raise ValueError("port debe ser AUTO o un puerto serial")
    if not isinstance(result["theme"], str):
        raise ValueError("theme debe ser un nombre de tema")
    return result


class AsciiSpinner(Static):
    FRAMES = ("|", "/", "-", "\\")

    def on_mount(self):
        self.frame_index = 0
        self.tick()
        self.set_interval(0.1, self.tick)

    def tick(self):
        frame = self.FRAMES[self.frame_index % len(self.FRAMES)]
        self.update(f"{frame} Procesando...")
        self.frame_index += 1


class AsciiBusyScreen(ModalScreen):
    DEFAULT_CSS = """
    AsciiBusyScreen { align: center middle; background: $background 70%; }
    #ascii-busy {
        width: 58;
        height: auto;
        border: heavy cyan;
        background: $surface;
        padding: 1 3;
        align: center middle;
    }
    #modal-logo {
        width: 45;
        height: 6;
        color: cyan;
    }
    #ascii-spinner {
        margin-top: 1;
        width: 100%;
        text-align: center;
        color: yellow;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="ascii-busy"):
            yield Static(LOGO, id="modal-logo", markup=False)
            yield AsciiSpinner(id="ascii-spinner", markup=False)


class TerminalIDE(base.ESP32TUIApp):
    # Sin dibujo de placa en el layout principal para maximizar el área de trabajo
    CSS = base.ESP32TUIApp.CSS

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.current_file = self.user_home / "sketch.py"

    def compose(self):
        # Omitimos el banner estático superior para dejar todo el alto al workspace
        yield from super().compose()

    def on_mount(self):
        super().on_mount()
        self.query_one("#editor-title", Static).update("Editor [Alt+2]: sketch.py")

    def get_busy_screen(self):
        return AsciiBusyScreen()

    def ampy(self, *args):
        result = subprocess.run(
            [sys.executable, "-c", "from ampy.cli import cli; cli()",
             "--port", self.port, "--baud", str(self.config["baudrate"]), *args],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip()
                                or f"ampy termino con codigo {result.returncode}")
        return result.stdout


def main():
    parser = argparse.ArgumentParser(description="ESP32 MicroPython terminal IDE (ESPTUI)")
    parser.add_argument("--version", action="version", version=f"tuiesp32 {VERSION}")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--init-config", action="store_true")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--baudrate", type=int)
    args = parser.parse_args()
    path = args.config or config_path()
    if args.init_config:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                json.dump(DEFAULTS, stream, indent=2)
                stream.write("\n")
        except FileExistsError:
            print(f"Configuracion existente, no se sobrescribe: {path}")
        except OSError as error:
            parser.error(str(error))
        else:
            print(f"Configuracion creada: {path}")
        return
    if args.list_ports:
        matched, others = base.get_filtered_ports()
        all_ports = matched + others
        for idx, port in enumerate(all_ports, start=1):
            tag = " [ESP/USB]" if port in matched else ""
            print(f"[{idx}] {port.device}: {port.description}{tag}")
        if not all_ports:
            print("No se detectaron puertos seriales.")
        return
    try:
        if args.config and not path.is_file():
            raise ValueError(f"No existe la configuracion: {path}")
        config = read_config(path)
        if args.port:
            config["port"] = args.port
        if args.baudrate is not None:
            if args.baudrate <= 0:
                raise ValueError("baudrate debe ser positivo")
            config["baudrate"] = args.baudrate
        TerminalIDE(config).run()
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
