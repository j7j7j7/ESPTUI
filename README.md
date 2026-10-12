# TUIESP32

IDE de terminal para trabajar con MicroPython en ESP32/ESP8266. Incluye editor Python, arbol local, listado/subida de archivos de la placa y consola serial. Python, Textual, pyserial y adafruit-ampy.

```text
███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝
```

Logo y spinner ASCII en instaladores y modales. Área de trabajo maximizada a pantalla completa, editor estándar predecible, navegación homogénea de paneles (Alt+1/2/3), selección automática de puertos y descarga/edición directa de archivos de la placa.

## Instalacion local en Linux

Desde una copia del proyecto que contenga main.py, tuiesp32.py, pyproject.toml y estos scripts:

```bash
bash install-local.sh
bash run-local.sh --version
bash run-local.sh --list-ports
bash run-local.sh
```

Revisa el script antes de ejecutarlo. No uses sudo. Si uv no existe, lo instala para tu usuario. uv selecciona Python 3.12 o descarga uno compatible si falta e instala las dependencias en un entorno aislado. Necesitas internet; no es una instalacion offline. Si ya existe tuiesp32, esta copia local reemplaza la instalacion anterior. Puede modificar perfiles de shell para PATH.

La app instalada no necesita conservar las fuentes. Conserva los scripts si quieres seguir usando el lanzador auxiliar o reinstalar desde estas fuentes. No se abre automaticamente al terminar la instalacion.

Tras reabrir la terminal:

```bash
tuiesp32
```

## Instalacion remota

Linux/macOS usan install.sh; Windows usa install.ps1. Los objetivos son sistemas modernos compatibles con Python y uv, no cualquier version/CPU. Estos scripts no instalan drivers USB ni cambian permisos seriales.

### Si el repositorio es publico

Estos comandos anonimos requieren que el codigo y los instaladores sean publicos. No funcionan sin autenticacion mientras el repositorio permanezca privado.

Linux/macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/j7j7j7/TUIESP32/main/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/j7j7j7/TUIESP32/main/install.ps1 | iex
```

### Si el repositorio es privado

Configura GITHUB_TOKEN mediante tu mecanismo seguro preferido. El token debe tener acceso de lectura al contenido de este repositorio. No lo escribas en URLs ni lo guardes en Git. Revisa scripts antes de ejecutarlos y elimina la variable cuando ya no la necesites.

Linux/macOS, con GITHUB_TOKEN exportado:

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H 'Accept: application/vnd.github.raw+json' \
  'https://api.github.com/repos/j7j7j7/TUIESP32/contents/install.sh?ref=main' | sh
```

Windows PowerShell, con $env:GITHUB_TOKEN configurado:

```powershell
$headers = @{ Authorization = "Bearer $env:GITHUB_TOKEN"; Accept = 'application/vnd.github.raw+json' }
irm -Headers $headers -Uri 'https://api.github.com/repos/j7j7j7/TUIESP32/contents/install.ps1?ref=main' | iex
```

Los instaladores remotos descargan las fuentes de main por defecto. TUIESP32_REF permite seleccionar una etiqueta o SHA existente para la descarga del archivo. Las URLs de ejemplo para descargar el script siguen apuntando a main; ajusta tambien esa referencia si necesitas fijar ambos. No hay lockfile ni releases firmadas.

## Uso y configuracion

```text
tuiesp32 --version
tuiesp32 --help
tuiesp32 --list-ports
tuiesp32 --port /dev/ttyUSB0
tuiesp32 --port COM3
tuiesp32 --baudrate 115200
tuiesp32 --init-config
tuiesp32 --config /ruta/config.json
```

La configuracion de la CLI vive en una carpeta de usuario resuelta por platformdirs. --init-config imprime la ubicacion, crea el JSON si falta y no sobrescribe uno existente. Defaults:

```json
{
  "port": "AUTO",
  "baudrate": 115200,
  "theme": "monokai"
}
```

El tema corresponde al editor, no necesariamente al tema general de Textual. La deteccion AUTO utiliza informacion de puertos/chips como heuristica; ante varios candidatos, indica --port.

## Atajos de Teclado
 
| Tecla | Acción |
| --- | --- |
| `Alt+1` | Enfocar panel de archivos (local y remoto) |
| `Alt+2` | Enfocar editor de código |
| `Alt+3` | Enfocar consola serial REPL |
| `Ctrl+S` | **Guardar** archivo actual (localmente o en placa) |
| `F5` | **Ejecutar** código en placa vía Paste Mode |
| `F6` | **Subir** archivo actual a la placa (`ampy put`) |
| `F8` | **Parar** toda ejecución (Interrupción doble Ctrl+C en placa) |
| `F9` | **Reiniciar** placa (Soft reset con Ctrl+D) |
| `F1` / `?` | Abrir ventana de ayuda y atajos |
| `F2` / `Ctrl+P` | Selector rápido de puertos seriales filtrados |
| `F7` | Colapsar / expandir consola REPL |
| `F10` | Colapsar / expandir panel de archivos |
| `Ctrl+Q` | Salir del IDE |

La CLI inicia mostrando la raíz de la carpeta personal del usuario (`~`) para proteger el código del proyecto, y abre `sketch.py`. Para editar archivos de la placa, haz click o presiona Enter sobre cualquier archivo del listado remoto: detendrá cualquier ejecución previa y se descargará automáticamente al editor. Guardar (`Ctrl+S`) o Subir (`F6`) actualizará el archivo en la placa.

## Conexión y precauciones

- La placa necesita MicroPython compatible.
- Al iniciar o con `Ctrl+P`, un modal clasifica y enumera puertos seriales con filtro tipo grep priorizando chips CP210x, CH340, FTDI y ESP32.
- El lector serial y las tareas de placa se coordinan con un bloqueo. La conexión de pyserial se cierra antes de ampy y se intenta reabrir después.
- La edición de archivos de la placa descarga el archivo de forma segura y permite su modificación directa.
- El botón **Parar** (`F8`) envía interrupciones limpias para detener scripts y bucles infinitos en ejecución.
- Paste Mode no confirma el prompt ni garantiza la ejecucion con cualquier firmware o programa activo.

Si hay un error de permisos, revisa el grupo propietario del dispositivo y los grupos de tu sesion; no ejecutes el IDE como root para ocultar el problema. Los instaladores no cambian permisos ni drivers.

## Actualizar y desinstalar

Actualizacion local: vuelve a ejecutar bash install-local.sh sobre las fuentes actualizadas. Actualizacion remota: repite el instalador para la referencia elegida.

```text
uv tool uninstall tuiesp32
```

Desinstalar la herramienta no elimina tu configuracion, sketches ni una instalacion compartida de uv/Python.

## Estructura

```text
main.py                     Nucleo de la TUI y conexion serial
tuiesp32.py                  CLI, configuracion y UI ASCII
pyproject.toml              Paquete y dependencias
install.sh                  Instalacion remota Linux/macOS
install.ps1                 Instalacion remota Windows
install-local.sh            Instalacion desde fuentes en Linux
run-local.sh                Lanzador auxiliar
AGENT.md                    Contexto y reglas de trabajo
docs/REFERENCIA-CODIGO.md    Explicacion tecnica
tests/test_cli.py           Pruebas sin placa
.github/workflows/ci.yml    CI para los tres sistemas
```

python main.py conserva la entrada de desarrollo heredada. Para la configuracion por usuario, invocacion de ampy dentro del entorno y UI ASCII, usa tuiesp32.

## Desarrollo y validacion

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build
bash -n install-local.sh
sh -n run-local.sh
sh -n install.sh
```

La CI esta configurada para construir el wheel, comprobar la CLI, ejecutar pruebas sin placa y revisar sintaxis en Linux/macOS/Windows. Tener el workflow no equivale a que haya pasado.

En la preparacion de los scripts locales comentados se verifico bash -n y sh -n. No se verificaron en esa preparacion resultados de CI, una instalacion completa en los tres OS ni pruebas con ESP32. Documentar resultados reales a medida que se ejecuten.

## Respaldo de cambios

Registrar cambios y documentacion en commits descriptivos y subirlos al repositorio. No incluir tokens, configuracion personal, entornos, caches ni archivos privados de la placa. Las escrituras remotas siguen requiriendo la confirmacion del usuario prevista por las herramientas.
