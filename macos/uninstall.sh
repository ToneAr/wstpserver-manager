#!/usr/bin/env bash
# Removes the Wolfram Kernel Pool (WSTPServer) launchd agent.
# Config and log files are left in place unless --purge is passed.
set -euo pipefail

AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$AGENT_DIR/com.wolfram.wstpserver.plist"
CONFIG_DIR="$HOME/Library/Application Support/wolfram-pool"
LOG_DIR="$HOME/Library/Logs/wolfram-pool"

launchctl unload -w "$PLIST_FILE" 2>/dev/null || true
rm -f "$PLIST_FILE"

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$CONFIG_DIR" "$LOG_DIR"
    echo "Removed service, config, and logs."
else
    echo "Removed service. Config kept at $CONFIG_DIR, logs kept at $LOG_DIR."
fi
