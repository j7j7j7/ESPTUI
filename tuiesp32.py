"""Compatibility wrapper for tuiesp32 CLI (redirects to esptui)."""
from esptui import (
    AsciiBusyScreen,
    AsciiSpinner,
    DEFAULTS,
    LOGO,
    TerminalIDE,
    VERSION,
    config_dir,
    config_path,
    main,
    read_config,
)

__all__ = [
    "AsciiBusyScreen",
    "AsciiSpinner",
    "DEFAULTS",
    "LOGO",
    "TerminalIDE",
    "VERSION",
    "config_dir",
    "config_path",
    "main",
    "read_config",
]

if __name__ == "__main__":
    main()
