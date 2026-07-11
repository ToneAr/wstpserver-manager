#!/bin/sh
set -eu

REPO="${REPO:-ToneAr/wstpserver-manager}"
VERSION="${VERSION:-latest}"
API_BASE="${GITHUB_API_URL:-https://api.github.com}"
TMPDIR="${TMPDIR:-/tmp}"

usage() {
    cat <<USAGE
Usage: install.sh [installer options]

Downloads and runs the latest WSTPServer Manager installer for this platform.

Environment:
  REPO=owner/repo       GitHub repository. Default: $REPO
  VERSION=v0.2.1       Release tag to install. Default: latest

Linux installer options are forwarded to the .run installer, for example:
  curl -fsSL https://github.com/$REPO/releases/latest/download/install.sh | sh -s -- --skip-service
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

download() {
    url="$1"
    output="$2"
    if command_exists curl; then
        curl -fL "$url" -o "$output"
    elif command_exists wget; then
        wget -O "$output" "$url"
    else
        echo "error: curl or wget is required." >&2
        exit 1
    fi
}

fetch_text() {
    url="$1"
    if command_exists curl; then
        curl -fsSL "$url"
    elif command_exists wget; then
        wget -qO- "$url"
    else
        echo "error: curl or wget is required." >&2
        exit 1
    fi
}

release_api_url() {
    if [ "$VERSION" = "latest" ]; then
        printf '%s/repos/%s/releases/latest\n' "$API_BASE" "$REPO"
    else
        printf '%s/repos/%s/releases/tags/%s\n' "$API_BASE" "$REPO" "$VERSION"
    fi
}

case "$(uname -s)" in
    Linux)
        case "$(uname -m)" in
            x86_64|amd64) asset_pattern='WSTPServerManager-.*-linux-x86_64\.run' ;;
            *)
                echo "error: unsupported Linux architecture: $(uname -m)" >&2
                exit 1
                ;;
        esac
        ;;
    Darwin)
        asset_pattern='WSTPServerManager-.*-macos\.pkg'
        ;;
    *)
        echo "error: unsupported platform: $(uname -s)" >&2
        echo "Download the installer manually from: https://github.com/$REPO/releases" >&2
        exit 1
        ;;
esac

release_json="$(fetch_text "$(release_api_url)")"
asset_url="$(printf '%s\n' "$release_json" |
    sed -n 's/.*"browser_download_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
    grep "/$asset_pattern$" |
    head -n 1)"

if [ -z "$asset_url" ]; then
    echo "error: could not find a matching installer asset in release '$VERSION'." >&2
    echo "Repository: $REPO" >&2
    exit 1
fi

workdir="$(mktemp -d "${TMPDIR%/}/wstpserver-manager.XXXXXX")"
cleanup() {
    rm -rf "$workdir"
}
trap cleanup EXIT INT TERM

asset_name="${asset_url##*/}"
installer="$workdir/$asset_name"

echo "Downloading $asset_url"
download "$asset_url" "$installer"

case "$installer" in
    *.run)
        chmod +x "$installer"
        "$installer" "$@"
        ;;
    *.pkg)
        echo "Installing $asset_name with macOS installer."
        sudo installer -pkg "$installer" -target /
        ;;
    *)
        echo "error: unsupported installer asset: $asset_name" >&2
        exit 1
        ;;
esac
