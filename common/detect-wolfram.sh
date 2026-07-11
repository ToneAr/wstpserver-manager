# Shared Wolfram kernel/wstpserver detection for the Linux and macOS install
# scripts. Meant to be sourced, not executed directly.
#
# Sets KERNEL_BIN and WSTPSERVER_BIN if not already set in the environment.

find_first_match() {
    # find_first_match <glob> ...
    for pattern in "$@"; do
        for match in $pattern; do
            [ -x "$match" ] && { echo "$match"; return 0; }
        done
    done
    return 1
}

# Walk up from a WolframKernel path looking for the sibling wstpserver binary
# (the two are installed under the same product root, but the number of
# directory levels between them varies by platform/version).
find_wstpserver_from_kernel() {
    local dir="$(dirname "$1")"
    for _ in 1 2 3 4; do
        if [ -x "$dir/SystemFiles/Links/WSTPServer/wstpserver" ]; then
            echo "$dir/SystemFiles/Links/WSTPServer/wstpserver"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

if [ -z "${KERNEL_BIN:-}" ] && command -v wolframscript >/dev/null 2>&1; then
    _showkernels_output="$(wolframscript -showkernels 2>/dev/null || true)"
    KERNEL_BIN="$(printf '%s\n' "$_showkernels_output" | awk \
        '/best WolframKernel location/{getline; gsub(/^[ \t]+|[ \t]+$/,""); if (length($0)) {print; exit}}')"
    unset _showkernels_output
fi

if [ -z "${WSTPSERVER_BIN:-}" ] && [ -n "${KERNEL_BIN:-}" ]; then
    WSTPSERVER_BIN="$(find_wstpserver_from_kernel "$KERNEL_BIN" || true)"
fi
