import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import TextArea
from esptui import (
    AsciiBusyScreen,
    AsciiSpinner,
    DEFAULTS,
    TerminalIDE,
    config_dir,
    config_path,
    read_config,
)
import tuiesp32


class ConfigTests(unittest.TestCase):
    def test_config_path_default(self):
        self.assertEqual(config_dir(), Path.home() / ".esptui")
        # tuiesp32 alias shares functions and defaults
        self.assertEqual(tuiesp32.config_dir(), Path.home() / ".esptui")

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
        with patch("esptui.subprocess.run") as run:
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

                # Editor estándar de Textual
                self.assertIsInstance(app.editor, TextArea)

                # Prueba de parada / stop
                with patch.object(app, "write_repl") as mock_write:
                    app.action_stop_execution()
                    mock_write.assert_called_with(b"\x03\x03")

                # Prueba de navegación de paneles (1, 2, 3)
                app.action_focus_panel("1")
                await pilot.pause()
                app.action_focus_panel("2")
                await pilot.pause()
                self.assertTrue(app.editor.has_focus)
                app.action_focus_panel("3")
                await pilot.pause()
                self.assertTrue(app.query_one("#serial-input").has_focus)

                # Prueba de seleccion de archivo remoto en esp32-files
                from textual.widgets import ListItem, Label
                item = ListItem(Label("boot.py"))
                await app.remote_files.append(item)
                await pilot.pause()
                fake_event = type("FakeSelected", (), {"list_view": app.remote_files, "item": item})()
                with patch.object(app, "start_board_task") as mock_board_task:
                    app.on_list_view_selected(fake_event)
                    mock_board_task.assert_called_with("get", remote_filename="boot.py", force=True)

                # Prueba de creacion de archivo
                from main import FileNameModal
                with patch.object(app, "push_screen") as mock_push:
                    app.action_new_file()
                    self.assertTrue(mock_push.called)
                    modal_arg = mock_push.call_args[0][0]
                    self.assertIsInstance(modal_arg, FileNameModal)

                # Prueba de renombrado de archivo
                with patch.object(app, "push_screen") as mock_push:
                    app.action_rename_file()
                    self.assertTrue(mock_push.called)
                    modal_arg = mock_push.call_args[0][0]
                    self.assertIsInstance(modal_arg, FileNameModal)

                # Prueba de modal contextual de archivo remoto
                from main import RemoteFileActionModal, ConfirmDeleteModal, RemoteFileItem
                with patch.object(app, "push_screen") as mock_push:
                    app.action_remote_file_context("main.py")
                    self.assertTrue(mock_push.called)
                    self.assertIsInstance(mock_push.call_args[0][0], RemoteFileActionModal)

                # Prueba de modal de confirmacion de eliminacion
                with patch.object(app, "push_screen") as mock_push:
                    app.action_delete_remote_file("main.py")
                    self.assertTrue(mock_push.called)
                    self.assertIsInstance(mock_push.call_args[0][0], ConfirmDeleteModal)

                # Prueba de item remoto y clic derecho
                remote_item = RemoteFileItem("test.py")
                self.assertEqual(remote_item.filename, "test.py")
                await app.remote_files.append(remote_item)
                await pilot.pause()
                fake_mouse = type("FakeMouseDown", (), {
                    "button": 3,
                    "stop": lambda *args: None,
                    "prevent_default": lambda *args: None,
                })()
                with patch.object(app, "action_remote_file_context") as mock_context:
                    remote_item.on_mouse_down(fake_mouse)
                    mock_context.assert_called_with("test.py")

                # Prueba de copiado de consola
                from main import copy_text_to_system_clipboard
                app.serial_log.write("Traceback (most recent call last):")
                await pilot.pause()
                with patch("main.copy_text_to_system_clipboard") as mock_clipboard:
                    app.action_copy_console()
                    self.assertTrue(mock_clipboard.called)
                    copied_text = mock_clipboard.call_args[0][1]
                    self.assertIn("Traceback", copied_text)


if __name__ == "__main__":
    unittest.main()

