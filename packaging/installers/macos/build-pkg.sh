#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_NAME="WSTPServerManager"
DIST_APP="${1:-$ROOT_DIR/dist/$APP_NAME.app}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/dist/installers}"
cd "$ROOT_DIR"
VERSION="${VERSION:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
IDENTIFIER="dev.local.wstpserver-manager"
OUT_FILE="$OUT_DIR/${APP_NAME}-${VERSION}-macos.pkg"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "error: macOS installer packages must be built on macOS." >&2
    exit 1
fi
if [ ! -d "$DIST_APP" ]; then
    echo "error: expected PyInstaller app bundle at $DIST_APP" >&2
    echo "Build it first with: python -m PyInstaller --noconfirm packaging/pyinstaller/wstpserver-tray.spec" >&2
    exit 1
fi

WORK_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$OUT_DIR" "$WORK_DIR/root/Applications" "$WORK_DIR/scripts"
cp -a "$DIST_APP" "$WORK_DIR/root/Applications/$APP_NAME.app"
cp "$SCRIPT_DIR/postinstall" "$WORK_DIR/scripts/postinstall"
chmod +x "$WORK_DIR/scripts/postinstall"

pkgbuild \
    --root "$WORK_DIR/root" \
    --scripts "$WORK_DIR/scripts" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    --install-location "/" \
    "$OUT_FILE"

echo "Built $OUT_FILE"
