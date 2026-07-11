#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_NAME="WSTPServerManager"
DIST_DIR="${1:-$ROOT_DIR/dist/$APP_NAME}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/dist/installers}"
cd "$ROOT_DIR"
VERSION="${VERSION:-$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
OUT_FILE="$OUT_DIR/${APP_NAME}-${VERSION}-linux-x86_64.run"

if [ ! -x "$DIST_DIR/$APP_NAME" ]; then
    echo "error: expected PyInstaller bundle at $DIST_DIR" >&2
    echo "Build it first with: python -m PyInstaller --noconfirm packaging/pyinstaller/wstpserver-tray.spec" >&2
    exit 1
fi

WORK_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$OUT_DIR" "$WORK_DIR/payload"
cp -a "$DIST_DIR" "$WORK_DIR/payload/$APP_NAME"
tar -C "$WORK_DIR/payload" -czf "$WORK_DIR/payload.tar.gz" "$APP_NAME"

awk '1; /^__WSTPSERVER_MANAGER_PAYLOAD_BELOW__$/ { exit 0 }' "$SCRIPT_DIR/installer.sh.in" > "$OUT_FILE"
cat "$WORK_DIR/payload.tar.gz" >> "$OUT_FILE"
chmod +x "$OUT_FILE"

echo "Built $OUT_FILE"
