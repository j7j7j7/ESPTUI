# TUIESP32

Terminal IDE for ESP32/ESP8266 MicroPython, with a Python editor, serial REPL,
local tree, remote file listing/upload, ASCII logo and ASCII loading spinner.
Vim/Neovim mode and CircuitPython compatibility are not implemented/validated.

## Installation

The installers reuse a compatible Python 3.12 interpreter or let uv download one.
They install dependencies into an isolated tool environment, without sudo/admin.
They add the tool directory to the shell PATH; reopen the terminal afterwards.
Internet access and curl/wget on Unix or Windows PowerShell 5.1 are required.
USB drivers and serial permissions are not installed or changed automatically.
The currently intended targets are modern Linux, macOS and Windows. This is not
an assurance of compatibility with every OS version/CPU or USB device.

### Public repository only

These anonymous commands work ONLY if the repository is made public. The installer
files and packaging must first be committed. Review downloaded scripts before execution.

Linux/macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/j7j7j7/TUIESP32/main/install.sh | sh
```

Windows (Windows PowerShell):

```powershell
irm https://raw.githubusercontent.com/j7j7j7/TUIESP32/main/install.ps1 | iex
```

### Private repository

Keep the repository private if desired. Use a GitHub token with Contents: read
access to this repository. Never put tokens in URLs or commit them. Set
GITHUB_TOKEN in your environment through your preferred secure secret mechanism.
Credentials are used for GitHub downloads, never for Astral or PyPI.
Clear the environment variable after installation. Review the script first.

Linux/macOS, with GITHUB_TOKEN already exported:

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H 'Accept: application/vnd.github.raw+json' \
  'https://api.github.com/repos/j7j7j7/TUIESP32/contents/install.sh?ref=main' | sh
```

Windows PowerShell, with $env:GITHUB_TOKEN already set:

```powershell
$headers = @{ Authorization = "Bearer $env:GITHUB_TOKEN"; Accept = 'application/vnd.github.raw+json' }
irm -Headers $headers -Uri 'https://api.github.com/repos/j7j7j7/TUIESP32/contents/install.ps1?ref=main' | iex
```

The scripts default to the main branch. Set TUIESP32_REF to an existing tag or
commit SHA to request a specific source version. These are development installers;
a locked dependency set and signed release artifacts remain future work.

## Usage

```text
tuiesp32
tuiesp32 --version
tuiesp32 --list-ports
tuiesp32 --port COM3
tuiesp32 --port /dev/ttyUSB0
tuiesp32 --init-config
tuiesp32 --config /path/to/config.json
```

Configuration is stored in the user's OS-specific config directory (platformdirs).
--init-config prints the actual location and never overwrites an existing file.
Defaults: port AUTO, baudrate 115200, editor theme monokai.

The installed CLI initially edits sketch.py in the current working directory,
not the IDE's main.py. Choose a local main.py from a separate project folder if
that is the filename you want to upload to the board. Selecting a file currently
discards unsaved edits: save before switching files.

F5 sends code through MicroPython Paste Mode. F6/F7 toggle panels, F8 interrupts,
F9 sends soft reset, Ctrl+S saves locally, Ctrl+Q exits. Upload sends a file;
it does not flash firmware. ampy may interrupt a running board program to access
its filesystem. The REPL is a log, not a complete terminal emulator.

The ASCII spinner uses | / - and backslash, not Unicode animation. The installer
falls back to plain progress lines when output is redirected (Unix) or suppresses
animated output (Windows). Windows downloads print a static progress label.

## Update / uninstall

Repeat the installer to update from the selected source ref.

```text
uv tool uninstall tuiesp32
```

This does not delete configuration, user sketches or a shared uv/Python installation.

## Development and validation

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

CI is configured for Linux, macOS and Windows with Python 3.12. It checks the CLI,
headless layout/spinner and ampy invocation, without hardware. The installer and
USB/REPL behavior need actual machine/board testing; CI does not certify them.
python main.py remains the legacy development entry point; use tuiesp32 for the
new per-user configuration, ASCII UI and packaged ampy invocation.
