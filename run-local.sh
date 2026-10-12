#!/bin/sh
# Detiene la ejecucion ante errores o variables obligatorias ausentes.
set -eu
# Primero busca uv en el PATH de la terminal actual.
if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
# Permite usar la app antes de reabrir una terminal tras instalar uv.
elif [ -x "$HOME/.local/bin/uv" ]; then
    uv_bin="$HOME/.local/bin/uv"
else
    # Explica el paso faltante sin intentar instalar nada automaticamente.
    echo "Primero ejecuta bash install-local.sh" >&2
    exit 1
fi
# Resuelve la carpeta efectiva de comandos administrados por uv.
bin_dir=$("$uv_bin" tool dir --bin)
# Reemplaza este proceso por la app y conserva todos sus argumentos.
exec "$bin_dir/esptui" "$@"
