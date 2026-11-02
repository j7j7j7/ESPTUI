# ESPTUI

[English](#english) · [Español](#español)

---

<a name="english"></a>
## English

Lightweight terminal IDE for MicroPython on ESP32, ESP8266, and compatible microcontrollers. Built with Python, Textual, pyserial, and ampy.

```text
███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝
```

### Features
- **3-Panel Layout:** Local file explorer, Python code editor, and interactive serial REPL console.
- **Port Auto-detection:** Filtered serial port modal prioritizing ESP chips and USB-to-UART bridges (CP210x, CH34x, FTDI).
- **Remote File Management:** Download, edit, upload, rename, and delete files on board flash storage.
- **Quick Execution:** Run code in RAM via Paste Mode (`F5`) or upload permanently to flash (`F6`).
- **Execution Control:** Interrupt execution with double break (`F8` / `Ctrl+C`) and soft reset (`F9` / `Ctrl+D`).
- **Telemetry & Diagnostics:** Live sidebar metrics showing free RAM (`gc.mem_free()`), flash storage (`os.statvfs('/')`), and CPU frequency (`machine.freq()`).
- **Package Manager (`mip`):** Integrated browser/installer (`F11`) for MicroPython libraries from `micropython.org/pi/v2` directly into `/lib` without requiring Wi-Fi on the board.
- **Firmware Flasher (`esptool`):** Flash official MicroPython firmware binaries (`F12`) with one-click download, baud rate selection, and optional flash erase.
- **Bilingual Interface (i18n):** English default (`en.json`) with full Spanish support (`es.json`). Toggle dynamically via `F3`.
- **Plug & Play on Linux:** Includes udev rules (`99-esptui.rules`) with `uaccess` so non-root users can access serial ports without group re-login.

### Supported Boards
Works with any board running official **MicroPython**:
- **ESP32** (DevKit v1, NodeMCU-32S, ESP32-WROOM-32, WROVER)
- **ESP32-S2 / ESP32-S3 / ESP32-C3 / ESP32-C6**
- **ESP8266** (NodeMCU v2/v3, D1 Mini, ESP-12E/F)
- **Raspberry Pi Pico / Pico W** (with official MicroPython UF2)

### Installation

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.sh | sh
```

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.ps1 | iex
```

#### From Local Source
```bash
git clone https://github.com/j7j7j7/ESPTUI.git
cd ESPTUI
bash install-local.sh
```

Once installed, launch it in your terminal:
```bash
esptui
```
*(The `tuiesp32` command is kept as a backward-compatible alias)*

### Keybindings

| Key | Action |
| --- | --- |
| `Alt+1` | Focus files & board tree |
| `Alt+2` | Focus code editor |
| `Alt+3` | Focus serial REPL console |
| `Ctrl+N` | Create new empty file |
| `F4` | Rename active or board file |
| `Ctrl+S` | Save current file (local or board) |
| `F5` | Run code on board (Paste Mode in RAM) |
| `F6` | Upload file to board flash (`ampy put`) |
| `F8` | Stop board execution (`Ctrl+C` interrupt) |
| `F9` | Soft reset board (`Ctrl+D`) |
| `Ctrl+C` | Copy selection or console log to system clipboard |
| `F1` / `?` | Open help modal with all keybindings |
| `F2` / `Ctrl+P` | Serial port selector & filter |
| `F3` | Toggle UI language (English / Español) |
| `F11` | MicroPython package manager (`mip`) |
| `F12` | ESP32 firmware flasher (`esptool`) |
| `Ctrl+Q` | Quit ESPTUI |

#### Board File Tree Controls:
- **Left Click / `Enter`:** Open & download file to editor.
- **Right Click / `m` / `Space`:** Context menu (Open, Rename, Delete).
- **`Delete`:** Delete selected file from board (with confirmation).
- **`F4`:** Rename selected file on board.

### CLI Flags

```bash
esptui --port /dev/ttyUSB0     # Open direct serial port
esptui --baudrate 115200       # Serial baudrate (default: 115200)
esptui --lang en               # Interface language (en, es)
esptui --list-ports            # List detected serial ports
esptui --init-config           # Generate configuration at ~/.esptui/config.json
```

---

<a name="español"></a>
## Español

IDE ligero de terminal para MicroPython en microcontroladores ESP32, ESP8266 y microcontroladores compatibles. Construido con Python, Textual, pyserial y ampy.

### Características
- **3 Paneles:** Árbol de archivos locales, editor de código Python y consola serial REPL interactiva.
- **Detección de puertos:** Modal con lista enumerada y filtro automático para chips ESP y adaptadores USB-Serial (CP210x, CH34x, FTDI).
- **Gestión remota:** Descarga, edita, sube, renombra y elimina archivos en la memoria flash de la placa.
- **Ejecución rápida:** Ejecución al vuelo en RAM vía Paste Mode (`F5`) o subida permanente a flash (`F6`).
- **Control de ejecución:** Parada inmediata con interrupción doble (`F8` / `Ctrl+C`) y soft reset (`F9` / `Ctrl+D`).
- **Telemetría y Diagnóstico:** Visualización en vivo en la barra lateral de RAM libre (`gc.mem_free()`), almacenamiento Flash disponible (`os.statvfs('/')`) y velocidad de reloj de la CPU (`machine.freq()`).
- **Gestor de Paquetes (`mip`):** Instalador integrado (`F11`) para librerías MicroPython desde el índice oficial `micropython.org/pi/v2` directo a `/lib` en la placa sin requerir WiFi en el microcontrolador.
- **Flasheador de Firmware (`esptool`):** Grabado de binarios MicroPython oficiales (`F12`) con descarga con un clic, selección de velocidad (115200 / 460800 baudios) y borrado previo opcional.
- **Multilenguaje (i18n):** Interfaz en inglés (`en.json`) y español (`es.json`). Selector dinámico vía `F3`.
- **Plug & Play en Linux:** Incluye reglas udev (`99-esptui.rules`) con `uaccess` para que los usuarios sin privilegios root puedan acceder al puerto serial sin tener que reiniciar ni cerrar sesión.

### Placas Compatibles
Funciona con cualquier microcontrolador que ejecute **MicroPython**:
- **ESP32** (DevKit v1, NodeMCU-32S, ESP32-WROOM-32, WROVER)
- **ESP32-S2 / ESP32-S3 / ESP32-C3 / ESP32-C6**
- **ESP8266** (NodeMCU v2/v3, D1 Mini, ESP-12E/F)
- **Raspberry Pi Pico / Pico W** (con firmware MicroPython oficial)

### Instalación

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.sh | sh
```

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.ps1 | iex
```

#### Desde fuentes locales
```bash
git clone https://github.com/j7j7j7/ESPTUI.git
cd ESPTUI
bash install-local.sh
```

Una vez instalado, abre tu terminal y ejecuta:
```bash
esptui
```
*(El comando `tuiesp32` se mantiene disponible como alias por compatibilidad)*

### Atajos de Teclado

| Atajo | Acción |
| --- | --- |
| `Alt+1` | Enfocar panel de archivos locales y placa |
| `Alt+2` | Enfocar editor de código |
| `Alt+3` | Enfocar consola serial REPL |
| `Ctrl+N` | Crear nuevo archivo en blanco |
| `F4` | Renombrar archivo activo o en placa |
| `Ctrl+S` | Guardar archivo actual (local o en placa) |
| `F5` | Ejecutar código en placa (Paste Mode en RAM) |
| `F6` | Subir archivo a la placa (`ampy put` en flash) |
| `F8` | Detener ejecución activa (`Ctrl+C` en placa) |
| `F9` | Reinicio suave de la placa (`Ctrl+D`) |
| `Ctrl+C` | Copiar selección o registro de consola al portapapeles |
| `F1` / `?` | Abrir ventana de ayuda con todos los atajos |
| `F2` / `Ctrl+P` | Selector y filtro de puertos seriales |
| `F3` | Alternar idioma de interfaz (English / Español) |
| `F11` | Gestor de paquetes MicroPython (`mip`) |
| `F12` | Flasheador de firmware ESP32 (`esptool`) |
| `Ctrl+Q` | Salir de ESPTUI |

#### En la lista de archivos de la placa:
- **Clic Izquierdo / `Enter`:** Abrir y descargar al editor.
- **Clic Derecho / `m` / `Espacio`:** Menú contextual (Abrir, Renombrar, Eliminar).
- **`Supr` (`Delete`):** Eliminar archivo de la placa (con confirmación).
- **`F4`:** Renombrar archivo seleccionado en la placa.

### Parámetros CLI

```bash
esptui --port /dev/ttyUSB0     # Especificar puerto serial directo
esptui --baudrate 115200       # Velocidad en baudios (por defecto 115200)
esptui --lang es               # Seleccionar idioma de inicio (ej: en, es)
esptui --list-ports            # Listar puertos detectados
esptui --init-config           # Generar archivo de configuración en ~/.esptui/config.json
```

---

## Licencia / License
MIT
