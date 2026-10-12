# ESPTUI

IDE ligero de terminal para MicroPython en microcontroladores ESP32, ESP8266 y microcontroladores compatibles. Construido con Python, Textual, pyserial y ampy.

```text
███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝
```

## Características
- **3 Paneles:** Árbol de archivos locales, editor de código Python y consola serial REPL interactiva.
- **Detección de puertos:** Modal con lista enumerada y filtro automático para chips ESP y adaptadores USB-Serial (CP210x, CH34x, FTDI).
- **Gestión remota:** Descarga, edita, sube, renombra y elimina archivos en la memoria flash de la placa.
- **Ejecución rápida:** Ejecución al vuelo en RAM vía Paste Mode (`F5`) o subida permanente a flash (`F6`).
- **Control de ejecución:** Parada inmediata con interrupción doble (`F8` / Ctrl+C) y soft reset (`F9` / Ctrl+D).
- **Copiar errores:** Selección de texto con ratón y copiado al portapapeles del sistema (`Ctrl+C` o clic derecho).
- **Configuración limpia:** Carpeta global oculta en `~/.esptui/` para configuraciones sin ensuciar tus directorios de trabajo.

---

## Placas Compatibles
Funciona con cualquier microcontrolador que ejecute **MicroPython**:
- **ESP32** (DevKit v1, NodeMCU-32S, ESP32-WROOM-32, WROVER)
- **ESP32-S2 / ESP32-S3 / ESP32-C3 / ESP32-C6**
- **ESP8266** (NodeMCU v2/v3, D1 Mini, ESP-12E/F)
- **Raspberry Pi Pico / Pico W** (con firmware MicroPython oficial)

---

## Instalación

### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.sh | sh
```

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/j7j7j7/ESPTUI/main/install.ps1 | iex
```

### Desde fuentes locales
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

---

## Atajos de Teclado

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
| `F8` | Detener ejecución activa (Ctrl+C en placa) |
| `F9` | Reinicio suave de la placa (Ctrl+D) |
| `Ctrl+C` | Copiar selección o registro de consola al portapapeles |
| `F1` / `?` | Abrir ventana de ayuda con todos los atajos |
| `F2` / `Ctrl+P` | Selector y filtro de puertos seriales |
| `Ctrl+Q` | Salir de ESPTUI |

### En la lista de archivos de la placa:
- **Clic Izquierdo / `Enter`:** Abrir y descargar al editor.
- **Clic Derecho / `m` / `Espacio`:** Menú contextual (Abrir, Renombrar, Eliminar).
- **`Supr` (`Delete`):** Eliminar archivo de la placa (con confirmación).
- **`F4`:** Renombrar archivo seleccionado en la placa.

---

## Parámetros CLI

```bash
esptui --port /dev/ttyUSB0     # Especificar puerto serial directo
esptui --baudrate 115200       # Velocidad en baudios (por defecto 115200)
esptui --list-ports            # Listar puertos detectados
esptui --init-config           # Generar archivo de configuración en ~/.esptui/config.json
```

---

## Licencia
MIT
