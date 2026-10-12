# Referencia tecnica del codigo

Esta guia explica la implementacion actual. Los scripts locales tienen comentarios junto a sus instrucciones y bloques. Los comentarios detallados del nucleo Python se prepararan en un commit separado, sin mezclar cambios funcionales.

## main.py: configuracion y puertos

- load_config: empieza con AUTO, 115200 y monokai; lee config.json junto al modulo y valida el objeto, puerto y baudrate. Esta es la configuracion heredada de la entrada de desarrollo.
- find_port: respeta el puerto explicito; enumera puertos con pyserial y compara descripcion/hwid con palabras de chips conocidos. Un unico candidato se devuelve; varios obligan a configurar el puerto. Si no hay coincidencias y solo hay un puerto, se acepta como fallback, sin verificar que sea un ESP32.

## main.py: interfaz

- BusyScreen: modal de carga heredado con LoadingIndicator. La CLI lo sustituye por AsciiBusyScreen.
- ESP32TUIApp.CSS: Screen vertical, workspace horizontal y editor 1fr; laterales de 23%/27% que se reducen a siete columnas al colapsar. No recalcular porcentajes del editor para cada panel.
- BINDINGS: guardar, ejecutar, colapsar paneles, interrumpir, reiniciar y salir. Las acciones de la placa usan teclas de funcion para evitar conflictos con copiar/borrar del editor.
- __init__: crea estado serial, Lock, Event de parada, bandera busy y archivo actual.
- compose: declara widgets; no abre el puerto ni ejecuta operaciones de placa.
- on_mount: guarda referencias a editor/log/listado, detecta el puerto, inicia el lector y solicita el primer listado remoto. Sin puerto mantiene la app abierta con un mensaje.

## main.py: comunicacion y tareas

- log_from_thread: vuelve al hilo de UI con call_from_thread. El escritor no debe mantener serial_lock mientras espera esta llamada.
- open_serial: abre con el baudrate configurado, timeout de lectura 0.1 segundos y timeout de escritura de dos segundos. Se llama dentro de rutas coordinadas por el bloqueo.
- read_serial: mientras no exista parada, entra al bloqueo y lee hasta 4096 bytes disponibles; sale del bloqueo antes de publicar el texto. El Event permite esperas cortas interrumpibles. Cada fragmento se decodifica por separado: no es un decoder UTF-8 incremental.
- ampy: entrada heredada mediante comando externo; subprocess captura salida, aplica timeout y comprueba returncode. La CLI sobreescribe este metodo para usar el mismo interprete de Python.
- start_board_task: rechaza tareas simultaneas, valida puerto, captura texto/nombre en UI, muestra modal y lanza hilo.
- board_task/run: bajo bloqueo, abre el puerto si falta, envia dos Ctrl+C, espera, envia Ctrl+E, espera, manda bloques de 128 bytes y finaliza con Ctrl+D. Son esperas fijas, no confirmaciones del prompt.
- board_task/list/upload: cierra pyserial, usa ampy, crea un temporal seguro si hay subida y lista archivos. finally intenta reabrir la consola. La reconexion puede fallar aunque la subida haya terminado.
- finish_board_task: vuelve a UI, espera clear/extend del ListView, escribe mensajes y retira modal/libera busy en finally.
- write_repl: rechaza comandos mientras hay otra tarea, valida conexion y escribe bytes bajo bloqueo.
- on_input_submitted: agrega CRLF al comando, escribe y limpia el input solo si la escritura fue aceptada.
- action_send_interrupt/action_send_soft_reset: envian bytes 0x03/0x04; no son comandos de texto.
- action_run_code: solicita la operacion run.
- action_toggle_sidebar/action_toggle_console: alternan collapsed cuando no hay tarea; CSS asigna el espacio restante.
- on_directory_tree_file_selected: carga UTF-8 al editor y actualiza archivo/titulo; aun no protege ediciones pendientes.
- action_save_file: escribe el texto al archivo local actual; no lo sube a la placa.
- on_button_pressed: asigna cada ID de boton a la accion correspondiente.
- on_unmount: activa parada y cierra la conexion si sigue abierta. No hace join del hilo ni elimina toda carrera posible durante el cierre.

## tuiesp32.py: CLI y extension

- VERSION/LOGO/DEFAULTS: version mostrada, arte ASCII y valores por defecto. La version debe coordinarse con pyproject.toml.
- config_path: usa platformdirs para no guardar configuracion dentro del paquete instalado.
- read_config: mezcla el JSON de usuario con defaults y valida puerto, baudrate y tipo del tema. El nombre del tema se valida finalmente al construir el editor.
- AsciiSpinner.on_mount: inicializa el cuadro y crea un temporizador de 0.1 segundos. tick rota cuatro caracteres y actualiza Static.
- AsciiBusyScreen.compose: agrupa logo/spinner dentro de un modal.
- TerminalIDE.__init__: reutiliza estado base, aplica config de CLI y empieza en sketch.py. El constructor base aun lee la configuracion heredada antes de aplicar este reemplazo.
- TerminalIDE.compose/on_mount: agrega el logo y corrige el titulo del archivo inicial.
- TerminalIDE.start_board_task: conserva captura/validaciones y sustituye el modal por el ASCII.
- TerminalIDE.ampy: sys.executable -c importa y ejecuta el comando Click de ampy. Asi funciona sin exponer un ejecutable ampy global.
- main: procesa version, ayuda, configuracion, listado y overrides. --init-config usa modo x para no sobrescribir. --list-ports no abre la placa. Sin esas opciones abre TerminalIDE.

## Instaladores locales

install-local.sh valida Linux y usuario no root, localiza fuentes, crea temporales, muestra logo y ejecuta etapas con spinner. fetch descarga el instalador oficial de uv; no descarga el repositorio. step registra el PID y espera su codigo de salida. La limpieza mata el proceso directo pendiente, no garantiza cancelar todos sus descendientes.

uv tool install pide Python 3.12 y permite descargarlo; instala fuentes locales aisladas. --force/--reinstall reemplazan una instalacion previa. tool update-shell puede editar perfiles. Si falla esa etapa, se conserva el acceso mediante run-local.sh. La verificacion --version comprueba arranque de CLI, no USB/REPL.

run-local.sh resuelve uv y su carpeta de comandos. exec sustituye el shell y pasa todos los argumentos; no cambia la carpeta actual del usuario.

## Pruebas y limites de las comprobaciones

Una comprobacion de sintaxis no ejecuta la instalacion ni detecta todos los problemas de concurrencia. Las pruebas existentes verifican configuracion, comando ampy con mock y UI sin placa. La matriz de CI no prueba drivers, permisos ni ejecucion real en hardware. Registrar estos resultados por separado.
