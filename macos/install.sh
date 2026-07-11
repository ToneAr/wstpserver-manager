#!/usr/bin/env bash
# Installs the Wolfram Kernel Pool (WSTPServer) as a per-user launchd agent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/Library/Application Support/wstpserver"
LOG_DIR="$HOME/Library/Logs/wstpserver"
AGENT_DIR="$HOME/Library/LaunchAgents"
CONFIG_FILE="$CONFIG_DIR/wstpserver.conf"
LOG_FILE="$LOG_DIR/wstpserver.log"
PLIST_FILE="$AGENT_DIR/com.wolfram.wstpserver.plist"
TRAY_LABEL="dev.local.wstpserver-manager.tray"
TRAY_PLIST_FILE="$AGENT_DIR/$TRAY_LABEL.plist"
TRAY_APP_BUNDLE="${WSTPSERVER_MANAGER_APP_BUNDLE:-/Applications/WSTPServerManager.app}"

source "$SCRIPT_DIR/../common/detect-wolfram.sh"

# wolframscript -showkernels is the primary detection method; fall back to
# scanning /Applications if wolframscript isn't on PATH.
WSTPSERVER_BIN="${WSTPSERVER_BIN:-$(find_first_match \
    "/Applications/Wolfram"*.app/Contents/SystemFiles/Links/WSTPServer/wstpserver \
    "/Applications/Mathematica"*.app/Contents/SystemFiles/Links/WSTPServer/wstpserver \
    || true)}"

KERNEL_BIN="${KERNEL_BIN:-$(find_first_match \
    "/Applications/Wolfram"*.app/Contents/MacOS/WolframKernel \
    "/Applications/Mathematica"*.app/Contents/MacOS/WolframKernel \
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

mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$AGENT_DIR"

if [ -f "$CONFIG_FILE" ]; then
    echo "Config already exists at $CONFIG_FILE, leaving it untouched."
else
    sed "s#__KERNEL_PATH__#$KERNEL_BIN#" "$SCRIPT_DIR/../common/wstpserver.conf.json.template" > "$CONFIG_FILE"
    echo "Wrote $CONFIG_FILE"
fi

sed \
    -e "s#__WSTPSERVER_BIN__#$WSTPSERVER_BIN#" \
    -e "s#__CONFIG_FILE__#$CONFIG_FILE#" \
    -e "s#__LOG_FILE__#$LOG_FILE#g" \
    "$SCRIPT_DIR/com.wolfram.wstpserver.plist.template" > "$PLIST_FILE"
echo "Wrote $PLIST_FILE"

launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load -w "$PLIST_FILE"

if [ -d "$TRAY_APP_BUNDLE" ]; then
    cat > "$TRAY_PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$TRAY_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-gj</string>
        <string>$TRAY_APP_BUNDLE</string>
        <string>--args</string>
        <string>--start-hidden</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
</dict>
</plist>
PLIST
    launchctl unload -w "$TRAY_PLIST_FILE" 2>/dev/null || true
    launchctl load -w "$TRAY_PLIST_FILE" 2>/dev/null || true
    echo "Registered tray app startup: $TRAY_PLIST_FILE"
else
    echo "Tray app bundle not found at $TRAY_APP_BUNDLE; skipped tray startup registration."
fi

echo "Done. Check status with: launchctl list | grep com.wolfram.wstpserver"
