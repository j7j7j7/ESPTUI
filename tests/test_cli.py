import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import TextArea
from tuiesp32 import AsciiBusyScreen, AsciiSpinner, DEFAULTS, TerminalIDE, read_config


class ConfigTests(unittest.TestCase):
    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.assertEqual(read_config(path), DEFAULTS)
            path.write_text(json.dumps({"port": "COM7"}), encoding="utf-8")
            self.assertEqual(read_config(path)["port"], "COM7")
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_config(path)

    def test_ampy_uses_current_interpreter(self):
        app = TerminalIDE(DEFAULTS.copy())
        app.port = "test-port"
        with patch("tuiesp32.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "main.py\n", "")
            self.assertEqual(app.ampy("ls"), "main.py\n")
            command = run.call_args.args[0]
            self.assertEqual(command[0], sys.executable)
            self.assertIn("from ampy.cli import cli; cli()", command)

    def test_spinner_is_ascii(self):
        self.assertTrue(all(frame.isascii() for frame in AsciiSpinner.FRAMES))
        self.assertEqual(len(AsciiSpinner.FRAMES), 4)


class UITests(unittest.IsolatedAsyncioTestCase):
    async def test_headless_layout_and_spinner_without_board(self):
        with patch("main.find_port", side_effect=RuntimeError("No board in CI")):
            app = TerminalIDE(DEFAULTS.copy())
            async with app.run_test(size=(120, 40)) as pilot:
                self.assertEqual(app.current_file.name, "sketch.py")
                self.assertIsInstance(app.editor, TextArea)
                app.action_toggle_sidebar()
                app.action_toggle_console()
                await pilot.pause()
                self.assertTrue(app.query_one("#sidebar").has_class("collapsed"))
                self.assertTrue(app.query_one("#console-pane").has_class("collapsed"))
                app.push_screen(AsciiBusyScreen())
                await pilot.pause()
                self.assertIsInstance(app.screen.query_one("#ascii-spinner"), AsciiSpinner)
                app.pop_screen()
                await pilot.pause()


if __name__ == "__main__":
    unittest.main()
