"""Regresion estatica de argumentos de los instaladores; no instala dependencias."""
import unittest
from pathlib import Path


class InstallerArgumentTests(unittest.TestCase):
    def test_python_download_policy_is_not_a_cli_argument(self):
        # Resuelve las fuentes del repositorio desde la ubicacion de esta prueba.
        root = Path(__file__).resolve().parents[1]
        for name in ("install-local.sh", "install.sh", "install.ps1"):
            with self.subTest(installer=name):
                source = (root / name).read_text(encoding="utf-8")
                # Este argumento causo el error reportado durante la prueba Linux.
                self.assertNotIn("--python-downloads", source)
                # La politica debe seguir permitiendo obtener Python cuando falte.
                self.assertIn("UV_PYTHON_DOWNLOADS", source)
                self.assertIn("automatic", source)
                # Conserva la solicitud de un interprete 3.12 para la herramienta.
                self.assertIn("3.12", source)


if __name__ == "__main__":
    unittest.main()
