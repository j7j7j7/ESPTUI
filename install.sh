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
ref=${ESPTUI_REF:-${TUIESP32_REF:-main}}
if ! step "Descargando ESPTUI" fetch "https://github.com/j7j7j7/ESPTUI/archive/refs/heads/$ref.tar.gz" "$work/source.tar.gz"; then
    if ! step "Descargando ESPTUI (fallback)" fetch "https://api.github.com/repos/j7j7j7/ESPTUI/tarball/$ref" "$work/source.tar.gz"; then
        echo "No se pudo descargar el repositorio ESPTUI." >&2
        exit 1
    fi
fi
if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
elif [ -x "$HOME/.local/bin/uv" ]; then
    uv_bin="$HOME/.local/bin/uv"
else
    step "Descargando instalador de uv" fetch "https://astral.sh/uv/install.sh" "$work/uv.sh"
    step "Instalando uv" env UV_INSTALL_DIR="$HOME/.local/bin" sh "$work/uv.sh"
    uv_bin="$HOME/.local/bin/uv"
fi
# Habilita descargas por entorno sin enviar un argumento CLI no soportado.
step "Preparando Python y dependencias" env UV_PYTHON_DOWNLOADS=automatic "$uv_bin" tool install --python 3.12 --force --reinstall "$work/source.tar.gz"
step "Configurando PATH" "$uv_bin" tool update-shell
bin_dir=$("$uv_bin" tool dir --bin)
"$bin_dir/esptui" --version

if [ "$(uname -s)" = "Linux" ]; then
    rules_dest="/etc/udev/rules.d/99-esptui.rules"
    rules_src="$work/99-esptui.rules"
    if [ ! -f "$rules_src" ]; then
        tar -xzf "$work/source.tar.gz" --wildcards '*99-esptui.rules' -O > "$rules_src" 2>/dev/null || true
    fi
    if [ ! -f "$rules_src" ] || [ ! -s "$rules_src" ]; then
        cat <<'RULES' > "$rules_src"
# 99-esptui.rules
# Reglas udev para permitir acceso de usuario local (uaccess) a microcontroladores ESP32 y chips seriales USB comunes.
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", MODE="0666", TAG+="uaccess"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="10c4", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", MODE="0666", TAG+="uaccess"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a86", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666", TAG+="uaccess"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0666", TAG+="uaccess"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="303a", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", MODE="0666", TAG+="uaccess"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="2e8a", MODE="0666", TAG+="uaccess"
RULES
    fi
    if [ ! -f "$rules_dest" ] || ! cmp -s "$rules_src" "$rules_dest" 2>/dev/null; then
        printf '\nConfigurando reglas udev para acceso a ESP32 (sin root)...\n'
        if command -v sudo >/dev/null 2>&1; then
            if [ ! -t 0 ] && [ -c /dev/tty ]; then
                if sudo cp "$rules_src" "$rules_dest" </dev/tty && sudo udevadm control --reload-rules </dev/tty && sudo udevadm trigger </dev/tty; then
                    printf '[OK] Reglas udev configuradas correctamente.\n'
                else
                    printf '[AVISO] No se pudieron aplicar las reglas udev automáticamente.\n' >&2
                    printf 'Para habilitar acceso sin root, ejecuta:\n' >&2
                    printf '  sudo cp "%s" "%s" && sudo udevadm control --reload-rules && sudo udevadm trigger\n' "$rules_src" "$rules_dest" >&2
                fi
            elif sudo cp "$rules_src" "$rules_dest" && sudo udevadm control --reload-rules && sudo udevadm trigger; then
                printf '[OK] Reglas udev configuradas correctamente.\n'
            else
                printf '[AVISO] No se pudieron aplicar las reglas udev automáticamente.\n' >&2
                printf 'Para habilitar acceso sin root, ejecuta:\n' >&2
                printf '  sudo cp "%s" "%s" && sudo udevadm control --reload-rules && sudo udevadm trigger\n' "$rules_src" "$rules_dest" >&2
            fi
        else
            printf '[AVISO] sudo no disponible. Para usar ESP32 sin root, copia las reglas a %s\n' "$rules_dest" >&2
        fi
    fi
fi

printf '\nListo. Si el comando no se reconoce de inmediato en esta misma ventana:\n'
printf '  source ~/.bashrc  (o abre una terminal nueva)\n'
printf 'Luego ejecuta: esptui (o tuiesp32)\n'
printf 'Actualiza repitiendo el instalador. Desinstala con: uv tool uninstall esptui\n'
