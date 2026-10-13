import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Select, Static, Button
from i18n import I18n, get_i18n
from esptui import DEFAULTS, TerminalIDE
import main as base


class I18nUnitTests(unittest.TestCase):
    def test_default_config_lang_folder_has_en_and_es(self):
        project_lang_dir = Path(__file__).resolve().parent.parent / "config" / "lang"
        self.assertTrue(project_lang_dir.is_dir())
        en_file = project_lang_dir / "en.json"
        es_file = project_lang_dir / "es.json"
        self.assertTrue(en_file.is_file())
        self.assertTrue(es_file.is_file())

        en_data = json.loads(en_file.read_text(encoding="utf-8"))
        es_data = json.loads(es_file.read_text(encoding="utf-8"))
        self.assertEqual(en_data.get("_meta", {}).get("code"), "en")
        self.assertEqual(es_data.get("_meta", {}).get("code"), "es")

    def test_i18n_default_language_is_en(self):
        i18n = I18n()
        self.assertEqual(i18n.current_lang, "en")
        self.assertIn("en", i18n.available_languages)
        self.assertIn("es", i18n.available_languages)
        self.assertTrue(i18n.has_multiple_languages)

    def test_i18n_translation_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "en.json").write_text(json.dumps({
                "_meta": {"name": "English"},
                "greeting": "Hello {name}",
                "common": {"ok": "OK"},
            }), encoding="utf-8")
            (tmp_path / "es.json").write_text(json.dumps({
                "_meta": {"name": "Español"},
                "greeting": "Hola {name}",
            }), encoding="utf-8")

            i18n = I18n(default_lang="en", lang_dirs=[tmp_path])
            self.assertEqual(i18n.current_lang, "en")
            self.assertTrue(i18n.has_multiple_languages)
            self.assertEqual(i18n.t("greeting", name="World"), "Hello World")
            self.assertEqual(i18n.t("common.ok"), "OK")

            # Switch to Spanish
            self.assertTrue(i18n.set_language("es"))
            self.assertEqual(i18n.current_lang, "es")
            self.assertEqual(i18n.t("greeting", name="Mundo"), "Hola Mundo")
            # Fallback to English for common.ok
            self.assertEqual(i18n.t("common.ok"), "OK")
            # Missing everywhere falls back to default
            self.assertEqual(i18n.t("missing.key", default="Default Val"), "Default Val")

    def test_single_language_has_multiple_languages_false(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "en.json").write_text(json.dumps({
                "_meta": {"name": "English"},
                "title": "Solo English",
            }), encoding="utf-8")

            i18n = I18n(default_lang="en", lang_dirs=[tmp_path])
            self.assertEqual(len(i18n.available_languages), 1)
            self.assertFalse(i18n.has_multiple_languages)
            self.assertEqual(i18n.current_lang, "en")


class I18nUITests(unittest.IsolatedAsyncioTestCase):
    async def test_top_menu_shows_language_switcher_and_switches_ui(self):
        with patch("main.find_port", side_effect=RuntimeError("No board in test")):
            config = DEFAULTS.copy()
            config["lang"] = "en"
            app = TerminalIDE(config)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Should have top-bar and lang-select when > 1 language exists
                self.assertTrue(app.i18n.has_multiple_languages)
                select = app.query_one("#lang-select", Select)
                self.assertIsNotNone(select)
                self.assertEqual(select.value, "en")

                # Verify English initial UI
                editor_title = app.query_one("#editor-title", Static)
                self.assertIn("Code editor", str(editor_title.render()))
                save_btn = app.query_one("#save-btn", Button)
                self.assertIn("Save", str(save_btn.label))

                # Switch to Spanish via action / select
                app.action_change_language("es")
                await pilot.pause()

                self.assertEqual(app.i18n.current_lang, "es")
                self.assertEqual(select.value, "es")
                self.assertIn("Editor de código", str(editor_title.render()))
                self.assertIn("Guardar", str(save_btn.label))

                # Cycle back to English via F3 / action_cycle_language
                app.action_cycle_language()
                await pilot.pause()
                self.assertEqual(app.i18n.current_lang, "en")
                self.assertEqual(select.value, "en")
                self.assertIn("Code editor", str(editor_title.render()))

    async def test_f3_cycles_language_on_modals(self):
        with patch("main.find_port", side_effect=RuntimeError("No board in test")):
            config = DEFAULTS.copy()
            config["lang"] = "en"
            app = TerminalIDE(config)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Initial modal is PortSelectModal in AUTO mode
                modal = app.screen
                self.assertEqual(type(modal).__name__, "PortSelectModal")
                self.assertEqual(modal.query_one("#port-title", Static).content, "Select Serial Port (ESPTUI)")

                # Press F3 directly on PortSelectModal
                await pilot.press("f3")
                await pilot.pause()
                self.assertEqual(app.i18n.current_lang, "es")
                self.assertEqual(modal.query_one("#port-title", Static).content, "Seleccionar Puerto Serial (ESPTUI)")

                # Dismiss modal
                await pilot.press("escape")
                await pilot.pause()

                # Open KeybindingsHelpModal via F1
                await pilot.press("f1")
                await pilot.pause()
                help_modal = app.screen
                self.assertEqual(type(help_modal).__name__, "KeybindingsHelpModal")
                self.assertEqual(help_modal.query_one("#help-title", Static).content, "Atajos de Teclado — ESPTUI")

                # Press F3 on KeybindingsHelpModal to switch back to English
                await pilot.press("f3")
                await pilot.pause()
                self.assertEqual(app.i18n.current_lang, "en")
                self.assertEqual(help_modal.query_one("#help-title", Static).content, "Keyboard Shortcuts — ESPTUI")
                await pilot.press("escape")
                await pilot.pause()

    async def test_single_language_does_not_show_top_menu_switcher(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "en.json").write_text(json.dumps({
                "_meta": {"name": "English"},
                "sidebar": {"title": "Only English Files"},
            }), encoding="utf-8")

            single_i18n = I18n(default_lang="en", lang_dirs=[tmp_path])
            self.assertFalse(single_i18n.has_multiple_languages)

            with patch("main.get_i18n", return_value=single_i18n):
                with patch("main.find_port", side_effect=RuntimeError("No board in test")):
                    app = TerminalIDE(DEFAULTS.copy())
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        # Because len(languages) == 1, lang-select must NOT exist in top menu
                        self.assertEqual(len(app.query("#lang-select")), 0)
                        self.assertEqual(len(app.query("#top-bar")), 0)


    async def test_footer_and_action_buttons_match_language(self):
        with patch("main.find_port", side_effect=RuntimeError("No board in test")):
            config = DEFAULTS.copy()
            config["lang"] = "en"
            app = TerminalIDE(config)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Dismiss initial PortSelectModal
                await pilot.press("escape")
                await pilot.pause()

                # In English mode:
                save_btn = app.query_one("#save-btn", Button)
                run_btn = app.query_one("#send-btn", Button)
                upload_btn = app.query_one("#upload-btn", Button)
                stop_btn = app.query_one("#stop-btn", Button)
                self.assertEqual(str(save_btn.label), "Save (Ctrl+S)")
                self.assertEqual(str(run_btn.label), "Run (F5)")
                self.assertEqual(str(upload_btn.label), "Upload (F6)")
                self.assertEqual(str(stop_btn.label), "Stop (F8)")

                footer_descriptions = {k.key: k.description for k in app.query("FooterKey")}
                self.assertEqual(footer_descriptions.get("ctrl+s"), "Save")
                self.assertEqual(footer_descriptions.get("f5"), "Run")
                self.assertEqual(footer_descriptions.get("f6"), "Upload")
                self.assertEqual(footer_descriptions.get("f8"), "Stop")
                self.assertEqual(footer_descriptions.get("f3"), "Language")

                # Switch to Spanish
                app.action_change_language("es")
                await pilot.pause()

                self.assertEqual(str(save_btn.label), "Guardar (Ctrl+S)")
                self.assertEqual(str(run_btn.label), "Ejecutar (F5)")
                self.assertEqual(str(upload_btn.label), "Subir (F6)")
                self.assertEqual(str(stop_btn.label), "Parar (F8)")

                footer_descriptions = {k.key: k.description for k in app.query("FooterKey")}
                self.assertEqual(footer_descriptions.get("ctrl+s"), "Guardar")
                self.assertEqual(footer_descriptions.get("f5"), "Ejecutar")
                self.assertEqual(footer_descriptions.get("f6"), "Subir")
                self.assertEqual(footer_descriptions.get("f8"), "Parar")
                self.assertEqual(footer_descriptions.get("f3"), "Idioma")
                self.assertEqual(footer_descriptions.get("f11"), "Paquetes")
                self.assertEqual(footer_descriptions.get("f12"), "Flashear")

    async def test_board_telemetry_and_packages_flasher_modals_ui(self):
        with patch("main.find_port", side_effect=RuntimeError("No board in test")):
            config = DEFAULTS.copy()
            config["lang"] = "en"
            app = TerminalIDE(config)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Dismiss initial PortSelectModal
                await pilot.press("escape")
                await pilot.pause()

                # Verify telemetry widget
                stats = app.query_one("#board-stats", Static)
                self.assertIn("RAM: --", str(stats.render()))

                # Test F11 Package Manager modal
                await pilot.press("f11")
                await pilot.pause()
                pkg_modal = app.screen
                self.assertEqual(type(pkg_modal).__name__, "PackageManagerModal")
                self.assertEqual(
                    pkg_modal.query_one("#pkg-title", Static).content,
                    "MicroPython Package Manager (mip)"
                )

                # Switch to Spanish via F3 inside modal
                await pilot.press("f3")
                await pilot.pause()
                self.assertEqual(app.i18n.current_lang, "es")
                self.assertEqual(
                    pkg_modal.query_one("#pkg-title", Static).content,
                    "Gestor de Paquetes MicroPython (mip)"
                )
                await pilot.press("escape")
                await pilot.pause()

                # Test F12 Firmware Flasher modal
                await pilot.press("f12")
                await pilot.pause()
                flash_modal = app.screen
                self.assertEqual(type(flash_modal).__name__, "FirmwareFlashModal")
                self.assertEqual(
                    flash_modal.query_one("#flasher-title", Static).content,
                    "Flasheador de Firmware ESP32 (esptool)"
                )

                # Switch back to English via F3 inside modal
                await pilot.press("f3")
                await pilot.pause()
                self.assertEqual(app.i18n.current_lang, "en")
                self.assertEqual(
                    flash_modal.query_one("#flasher-title", Static).content,
                    "ESP32 Firmware Flasher (esptool)"
                )
                await pilot.press("escape")
                await pilot.pause()


if __name__ == "__main__":
    unittest.main()
