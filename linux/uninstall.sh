#!/usr/bin/env bash
# Removes the Wolfram Kernel Pool (WSTPServer) systemd --user service.
# Config and log files are left in place unless --purge is passed.
set -euo pipefail

UNIT_DIR="$HOME/.config/systemd/user"
CONFIG_DIR="$HOME/.config/wolfram-pool"
DATA_DIR="$HOME/.local/share/wolfram-pool"

systemctl --user disable --now wstpserver.service 2>/dev/null || true
rm -f "$UNIT_DIR/wstpserver.service"
systemctl --user daemon-reload

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$CONFIG_DIR" "$DATA_DIR"
    echo "Removed service, config, and logs."
else
    echo "Removed service. Config kept at $CONFIG_DIR, logs kept at $DATA_DIR."
fi
