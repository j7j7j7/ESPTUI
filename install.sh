#!/bin/sh
set -eu
case "$(uname -s)" in Linux|Darwin) ;; *) echo "Usa install.ps1 en Windows." >&2; exit 1;; esac
cat <<'LOGO'
███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝
LOGO
work=$(mktemp -d)
child=''
cleanup() {
    if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; fi
    rm -rf "$work"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' TERM
fetch() {
    url=$1; output=$2
    if command -v curl >/dev/null 2>&1; then
        case "$url" in
            https://api.github.com/*)
                if [ -n "${GITHUB_TOKEN:-}" ]; then
                    curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" "$url" -o "$output"
                else curl -fsSL "$url" -o "$output"; fi ;;
            *) curl -fsSL "$url" -o "$output" ;;
        esac
    elif command -v wget >/dev/null 2>&1; then
        case "$url" in
            https://api.github.com/*)
                if [ -n "${GITHUB_TOKEN:-}" ]; then
                    wget -q --header="Authorization: Bearer $GITHUB_TOKEN" -O "$output" "$url"
                else wget -q -O "$output" "$url"; fi ;;
            *) wget -q -O "$output" "$url" ;;
        esac
    else echo "Se requiere curl o wget para descargar archivos." >&2; return 1; fi
}
step() {
    title=$1; shift
    "$@" >"$work/step.log" 2>&1 &
    child=$!
    if [ -t 2 ] && [ "${TERM:-dumb}" != dumb ]; then
        while kill -0 "$child" 2>/dev/null; do
            for frame in '|' '/' '-' '\'; do
                printf '\r[%s] %s' "$frame" "$title" >&2
                sleep 0.1
                kill -0 "$child" 2>/dev/null || break
            done
        done
    else printf '%s\n' "$title" >&2; fi
    if wait "$child"; then
        child=''; printf '\r[OK] %s\n' "$title" >&2
    else
        status=$?; child=''
        printf '\r[ERROR] %s\n' "$title" >&2
        cat "$work/step.log" >&2
        return "$status"
    fi
}
ref=${TUIESP32_REF:-main}
if ! step "Descargando TUIESP32" fetch "https://github.com/j7j7j7/TUIESP32/archive/refs/heads/$ref.tar.gz" "$work/source.tar.gz"; then
    if ! step "Descargando TUIESP32 (fallback)" fetch "https://api.github.com/repos/j7j7j7/TUIESP32/zipball/$ref" "$work/source.tar.gz"; then
        echo "No se pudo descargar el repositorio TUIESP32." >&2
        exit 1
    fi
fi
if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
else
    step "Descargando instalador de uv" fetch "https://astral.sh/uv/install.sh" "$work/uv.sh"
    step "Instalando uv" env UV_INSTALL_DIR="$HOME/.local/bin" sh "$work/uv.sh"
    uv_bin="$HOME/.local/bin/uv"
fi
# Habilita descargas por entorno sin enviar un argumento CLI no soportado.
step "Preparando Python y dependencias" env UV_PYTHON_DOWNLOADS=automatic "$uv_bin" tool install --python 3.12 --force --reinstall "$work/source.tar.gz"
step "Configurando PATH" "$uv_bin" tool update-shell
bin_dir=$("$uv_bin" tool dir --bin)
"$bin_dir/tuiesp32" --version
printf '\nListo. Reabre la terminal y ejecuta: tuiesp32\n'
printf 'Actualiza repitiendo el instalador. Desinstala con: uv tool uninstall tuiesp32\n'
