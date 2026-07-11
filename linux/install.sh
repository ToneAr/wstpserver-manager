#!/usr/bin/env bash
# Installs the Wolfram Kernel Pool (WSTPServer) as a systemd --user service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/wstpserver"
DATA_DIR="$HOME/.local/share/wstpserver"
UNIT_DIR="$HOME/.config/systemd/user"
CONFIG_FILE="$CONFIG_DIR/wstpserver.conf"
LOG_FILE="$DATA_DIR/wstpserver.log"

source "$SCRIPT_DIR/../common/detect-wolfram.sh"

# wolframscript -showkernels is the primary detection method; fall back to
# scanning common install roots if wolframscript isn't on PATH.
WSTPSERVER_BIN="${WSTPSERVER_BIN:-$(find_first_match \
    "$HOME"/Wolfram/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver \
    /usr/local/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver \
    /opt/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver \
    || true)}"

KERNEL_BIN="${KERNEL_BIN:-$(find_first_match \
    "$HOME"/Wolfram/Wolfram/*/Executables/WolframKernel \
    /usr/local/Wolfram/*/Executables/WolframKernel \
    /opt/Wolfram/*/Executables/WolframKernel \
    || true)}"

if [ -z "${WSTPSERVER_BIN:-}" ]; then
    echo "error: could not find the wstpserver binary. Set WSTPSERVER_BIN=/path/to/wstpserver and re-run." >&2
    exit 1
fi
if [ -z "${KERNEL_BIN:-}" ]; then
    echo "error: could not find the WolframKernel binary. Set KERNEL_BIN=/path/to/WolframKernel and re-run." >&2
    exit 1
fi

echo "Using wstpserver: $WSTPSERVER_BIN"
echo "Using kernel:     $KERNEL_BIN"

mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$UNIT_DIR"

if [ -f "$CONFIG_FILE" ]; then
    echo "Config already exists at $CONFIG_FILE, leaving it untouched."
else
    sed "s#__KERNEL_PATH__#$KERNEL_BIN#" "$SCRIPT_DIR/../common/wstpserver.conf.json.template" > "$CONFIG_FILE"
    echo "Wrote $CONFIG_FILE"
fi

sed \
    -e "s#__WSTPSERVER_BIN__#$WSTPSERVER_BIN#" \
    -e "s#__CONFIG_FILE__#$CONFIG_FILE#" \
    -e "s#__LOG_FILE__#$LOG_FILE#" \
    "$SCRIPT_DIR/wstpserver.service.template" > "$UNIT_DIR/wstpserver.service"
echo "Wrote $UNIT_DIR/wstpserver.service"

systemctl --user daemon-reload
systemctl --user enable --now wstpserver.service

# Allow the user service to run without an active login session.
if command -v loginctl >/dev/null 2>&1; then
    loginctl enable-linger "$USER" || true
fi

echo "Done. Check status with: systemctl --user status wstpserver.service"
