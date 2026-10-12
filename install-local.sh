#!/usr/bin/env bash
# Activa errores estrictos; evita continuar tras una instalacion incompleta.
set -Eeuo pipefail
# Esta variante local esta destinada a Linux.
if [[ $(uname -s) != Linux ]]; then
    printf 'Este instalador local es para Linux.\n' >&2
    exit 1
fi
# No instala como root: el entorno y la configuracion pertenecen al usuario.
if [[ $EUID -eq 0 ]]; then
    printf 'Ejecuta como tu usuario normal, sin sudo.\n' >&2
    exit 1
fi
# Obtiene la carpeta del script, incluso cuando se ejecuta desde otra carpeta.
src=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Comprueba los archivos necesarios para construir e instalar el paquete.
for required in pyproject.toml main.py tuiesp32.py README.md; do
    [[ -f "$src/$required" ]] || { printf 'Falta %s junto al instalador.\n' "$required" >&2; exit 1; }
done
# El delimitador entre comillas conserva literalmente el logo ASCII.
cat <<'LOGO'
+--------------------------------------+
|  T U I E S P 3 2                     |
|       .----------------.             |
|   ----| ESP32 / Python |----         |
|       '----------------'             |
+--------------------------------------+
LOGO
# Crea una carpeta temporal privada para descargas y registros.
work=$(mktemp -d)
# Guarda el PID del proceso de la etapa actual, si existe.
child=''
# Limpia temporales y termina el proceso directo pendiente al salir.
cleanup() {
    if [[ -n "$child" ]]; then kill "$child" 2>/dev/null || true; fi
    rm -rf -- "$work"
}
# Ejecuta la limpieza al terminar normalmente o por error.
trap cleanup EXIT
# Convierte Ctrl+C en una salida convencional de interrupcion.
trap 'exit 130' INT
# Convierte una solicitud de terminacion en una salida convencional.
trap 'exit 143' TERM
# Descarga por HTTPS con curl o wget, sin consultar el repositorio privado.
fetch() {
    if command -v curl >/dev/null 2>&1; then
        # Limita el tiempo de conexion y de descarga del instalador de uv.
        curl -fsSL --connect-timeout 15 --max-time 120 "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --timeout=120 -O "$2" "$1"
    else
        printf 'Necesitas curl o wget para descargar uv.\n' >&2
        return 1
    fi
}
# Ejecuta una etapa, anima el spinner y conserva los errores para mostrarlos.
step() {
    # El primer argumento es el titulo; el resto es el comando real.
    local title=$1 status frame
    shift
    # Oculta la salida durante el spinner; conserva stdout y stderr juntos.
    "$@" >"$work/step.log" 2>&1 &
    # Registra el PID para esperar el resultado y poder cancelar la etapa.
    child=$!
    # Solo anima cuando hay terminal y no se ha declarado TERM=dumb.
    if [[ -t 2 && ${TERM:-dumb} != dumb ]]; then
        # Mantiene el spinner mientras el proceso siga activo.
        while kill -0 "$child" 2>/dev/null; do
            # Los cuatro cuadros usan exclusivamente caracteres ASCII.
            for frame in '|' '/' '-' '\'; do
                # Retorna al inicio de la misma linea sin generar otra linea.
                printf '\r[%s] %s' "$frame" "$title" >&2
                # Actualiza aproximadamente diez veces por segundo.
                sleep 0.1
                # Evita terminar toda la animacion si la etapa ya concluyo.
                kill -0 "$child" 2>/dev/null || break
            done
        done
    else
        # En logs o redirecciones, imprime una linea sin animacion.
        printf '%s\n' "$title" >&2
    fi
    # Espera el codigo de salida del proceso, no solo que deje de existir.
    if wait "$child"; then
        # Borra el PID para que la limpieza no mate un proceso ya finalizado.
        child=''
        printf '\r[OK] %s\n' "$title" >&2
    else
        # Conserva el codigo de error antes de ejecutar otros comandos.
        status=$?; child=''
        printf '\r[ERROR] %s\n' "$title" >&2
        # Muestra el detalle que estuvo oculto mientras giraba el spinner.
        cat "$work/step.log" >&2
        return "$status"
    fi
}
# Reutiliza uv si ya esta disponible en PATH.
if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
# Tambien encuentra una instalacion previa antes de reabrir la terminal.
elif [[ -x "$HOME/.local/bin/uv" ]]; then
    uv_bin="$HOME/.local/bin/uv"
else
    # Descarga el instalador oficial; revisa proveedores antes de ejecutarlos.
    step 'Descargando uv' fetch 'https://astral.sh/uv/install.sh' "$work/uv.sh"
    # Instala uv en la carpeta del usuario, sin sudo.
    step 'Instalando uv' env UV_INSTALL_DIR="$HOME/.local/bin" sh "$work/uv.sh"
    uv_bin="$HOME/.local/bin/uv"
fi
# Instala estas fuentes locales en un entorno aislado; descarga Python si falta.
# --force/--reinstall reemplazan una instalacion previa de esta misma herramienta.
step 'Instalando app local, Python y dependencias' "$uv_bin" tool install --python 3.12 --python-downloads automatic --force --reinstall "$src"
# Intenta actualizar los perfiles de shell; no invalida la app si esto falla.
if ! step 'Configurando PATH' "$uv_bin" tool update-shell; then
    printf 'La app esta instalada. Puedes abrirla con bash run-local.sh.\n' >&2
fi
# Pregunta a uv donde dejo los comandos, en vez de asumir su ubicacion.
bin_dir=$("$uv_bin" tool dir --bin)
# Verifica que el comando instalado pueda iniciar y mostrar su version.
step 'Verificando comando' "$bin_dir/tuiesp32" --version
# Informa las formas de abrir y reinstalar la app sin lanzarla automaticamente.
printf '\nInstalacion lista. Reabre la terminal y ejecuta: tuiesp32\n'
printf 'Sin reabrir la terminal: bash run-local.sh\n'
printf 'Comando directo: "%s/tuiesp32"\n' "$bin_dir"
printf 'Actualizacion local: vuelve a ejecutar bash install-local.sh\n'
