# AGENT.md - TUIESP32

## Objetivo

IDE ligero de terminal para editar, enviar y subir codigo MicroPython a ESP32/ESP8266. Construido en Python con Textual, pyserial y adafruit-ampy. Nombre del comando instalado: tuiesp32. Usuario principal: Manuel Mireles; documentacion y comentarios en espanol.

## Preferencias de trabajo

- Avanzar por bloques pequenos y reproducibles.
- Preservar logo y spinner ASCII.
- Registrar las modificaciones del proyecto en commits descriptivos y hacer push. No dar por respaldado un cambio que solo existe en un ZIP o en la maquina local.
- Antes de cada escritura remota, resolver repositorio/rama/archivos, mostrar el contenido exacto y solicitar la confirmacion que exija el entorno. Esta preferencia no elimina esa confirmacion.
- No cambiar la visibilidad del repositorio, permisos de colaboradores ni configuracion de GitHub sin autorizacion especifica.
- Explicar comportamiento con comentarios en espanol, especialmente concurrencia, serial, protocolos y scripts de instalacion.

## Arquitectura actual

- main.py: clase base ESP32TUIApp, layout, lectura serial, bloqueo de acceso, operaciones de placa, guardado y seleccion local. Conserva una entrada de desarrollo heredada con python main.py.
- tuiesp32.py: CLI instalada, configuracion por usuario mediante platformdirs, TerminalIDE, logo y AsciiBusyScreen/AsciiSpinner. Reutiliza la clase base.
- pyproject.toml: metadatos, dependencias, Python >=3.12 y punto de entrada tuiesp32:main. Los instaladores solicitan Python 3.12.
- install.sh: instalador remoto POSIX para Linux/macOS.
- install.ps1: instalador remoto Windows PowerShell.
- install-local.sh: instalacion desde fuentes locales en Linux, sin autenticar con GitHub. Necesita internet para proveedores de dependencias.
- run-local.sh: lanzador auxiliar; conserva argumentos y resuelve la carpeta de comandos con uv.
- tests/test_cli.py: pruebas de configuracion, invocacion de ampy y UI sin placa.
- .github/workflows/ci.yml: matriz Linux/macOS/Windows, construccion del wheel, CLI, pruebas y sintaxis de instaladores.
- docs/REFERENCIA-CODIGO.md: mapa tecnico para leer y depurar el codigo.

## Interfaz

Tres paneles: archivos locales (`~` por defecto) y listado remoto de placa, editor Python y consola REPL. Los laterales se colapsan en indicadores FILES/REPL. Navegación homogénea entre paneles con teclas `Alt+1` (Archivos), `Alt+2` (Editor) y `Alt+3` (Consola REPL). El área de trabajo ocupa el 100% de la altura de pantalla (banner estático retirado). El logo nuevo ESPTUI y spinner ASCII se preservan en instaladores y modales de proceso.

Atajos homogéneos y coherentes:
- `Alt+1` / `Alt+2` / `Alt+3`: Enfocar panel de Archivos / Editor / Consola REPL.
- `Ctrl+N`: Crear nuevo archivo / script limpio.
- `F4`: Renombrar archivo activo o definir nombre de destino en placa.
- `Ctrl+S`: Guardar archivo actual (localmente o en placa si fue descargado).
- `F5`: Enviar y ejecutar código en la placa (Paste Mode).
- `F6`: Subir archivo a la memoria flash de la placa (`ampy put`).
- `F8`: Parar toda ejecución activa (interrupción doble Ctrl+C en placa).
- `F9`: Reinicio suave de la placa (Ctrl+D).
- `F1` / `?`: Modal informativo con listado completo de atajos de teclado.
- `F2` / `Ctrl+P`: Modal de selección rápida de puertos seriales con filtro tipo grep.
- `F7`: Colapsar / expandir consola REPL.
- `F10`: Colapsar / expandir panel de archivos.
- `Ctrl+Q`: Salir del IDE.

## Reglas de concurrencia y serial

1. El lector y todas las operaciones de placa comparten serial_lock.
2. No ejecutar ampy mientras pyserial mantenga abierto el mismo puerto. Dentro del bloqueo, cerrar la conexion, ejecutar operaciones y reabrir en finally.
3. No actualizar widgets directamente desde hilos de trabajo; usar call_from_thread.
4. Capturar el texto y el nombre del archivo en el hilo de UI antes de iniciar la tarea.
5. Mantener busy para rechazar operaciones simultaneas.
6. No ocultar errores de placa, subprocess o reconexion. Mantener timeouts.
7. Usar sys.executable para invocar ampy desde el entorno instalado, no depender de su comando global.
8. Usar TemporaryDirectory para los archivos de subida. Nunca sobrescribir temporales en HOME.

## Configuracion e instalacion

La CLI busca su configuracion en la carpeta de usuario resuelta por platformdirs. --init-config crea sin sobrescribir y muestra la ruta. --config selecciona un JSON explicito. --port y --baudrate permiten sobreescribir valores para la ejecucion. No guardar tokens, configuraciones personales ni sketches privados en Git.

uv instala la herramienta en un entorno aislado y puede obtener Python si falta. Los scripts pueden actualizar perfiles de shell para PATH. No instalar como root ni modificar grupos/permisos USB automaticamente. El instalador local requiere Bash; los remotos usan sh o PowerShell.

El repositorio se encontro privado al preparar estos cambios. Los comandos anonimos curl/irm requieren distribucion publica. Los instaladores remotos admiten GITHUB_TOKEN para leer GitHub; nunca ponerlo en URLs, logs, archivos o commits. No asumir que un usuario tiene acceso porque el conector del asistente lo tenga.

## Estado real y limitaciones

- Editor estándar de Textual (TextArea.code_editor), comportamiento habitual con flechas, ratón y selección; sin modos VIM para evitar interferencias.
- CircuitPython no esta validado. Priorizar MicroPython.
- El explorador remoto descarga y edita archivos con un click, deteniendo previamente cualquier bucle en ejecución.
- Al guardar (`Ctrl+S`) o subir (`F6`) un archivo descargado de la placa, se actualiza directamente en la flash del ESP32.
- La consola es un RichLog, no un emulador de terminal. La decodificacion por fragmentos puede afectar caracteres multibyte.
- Paste Mode usa interrupciones y esperas fijas; no confirma prompts ni dispone de control de flujo completo.
- Listar/subir con ampy puede interrumpir el programa de la placa. Subir archivos no equivale a actualizar firmware.
- La seleccion de puerto serial se automatiza mediante modal filtrado con enumeracion numerica inmediata.
- Dependencias con rangos abiertos; no hay lockfile ni releases firmadas.
- Los instaladores remotos fijan una version de uv; verificar que su URL exista antes de una release. El local usa el instalador oficial sin version fija.
- La CI configurada no demuestra por si sola que haya pasado. No afirmar soporte probado de todos los OS/CPU/placas.

## Validacion

Ejecutar segun disponibilidad:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build
bash -n install-local.sh
sh -n run-local.sh
sh -n install.sh
tuiesp32 --version
tuiesp32 --help
```

Separar en cada entrega: comprobaciones de sintaxis, pruebas ejecutadas, resultados de CI observados, instalacion real y pruebas con placa. No inventar resultados. Para un cambio solo de comentarios Python, comparar AST antes/despues y mantener el comportamiento. Para CSS, evitar insertar comentarios Python dentro de las cadenas.

## Pendientes

- Completar comentarios del nucleo Python en un commit separado.
- Verificar CI e instalacion real sin Python en los tres sistemas.
- Mejorar sincronizacion de REPL, cierre/reconexion y pruebas de desconexion.
- Anadir aviso de confirmacion para cambios locales sin guardar antes de cambiar de archivo.
- Definir distribucion publica, versiones fijadas y actualizacion verificable.

