"""Evita volver a sustituir App.log con el widget del REPL."""
import unittest
from unittest.mock import patch

from textual.widgets import RichLog
from main import ESP32TUIApp
from esptui import DEFAULTS, TerminalIDE


class LogWidgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_apps_mount_without_overwriting_textual_logger(self):
        # No abre puertos reales: esta prueba valida el arranque de la interfaz.
        with patch("main.find_port", side_effect=RuntimeError("No board in test")):
            for app in (ESP32TUIApp(), TerminalIDE(DEFAULTS.copy())):
                with self.subTest(app=type(app).__name__):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        # El RichLog del REPL tiene una referencia propia.
                        self.assertIsInstance(app.serial_log, RichLog)
                        self.assertIs(app.serial_log, app.query_one("#serial-log", RichLog))
                        # La propiedad heredada de Textual conserva su logger.
                        self.assertIsNot(app.log, app.serial_log)
                        # La ruta de error sin puerto tambien escribe en el widget correcto.
                        app.start_board_task("list")
                        await pilot.pause()


if __name__ == "__main__":
    unittest.main()
