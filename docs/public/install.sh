#!/bin/sh
# bimai installer for macOS and Linux.  Usage:  curl -LsSf https://docs.bimai.nl/install.sh | sh
#
# What it does, for the current user only (no administrator rights, no Python or git needed):
#   1. installs uv (Astral's Python tool manager) into ~/.local/bin if it isn't there yet
#   2. installs or updates bimai with `uv tool install --upgrade bimai`
#      (uv downloads a suitable Python by itself when none is found)
#   3. makes sure ~/.local/bin is on your PATH
# Run it again at any time to update bimai. BIMAI_PACKAGE overrides what is installed (a version or a wheel).
set -eu

PACKAGE="${BIMAI_PACKAGE:-bimai}"

say() { printf '%s\n' "$*"; }
fail() { printf 'bimai install: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "curl is needed to download uv. Install curl and try again."

if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV="$HOME/.local/bin/uv"
else
    say "Installing uv (the tool that installs bimai and its Python) into ~/.local/bin ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null \
        || fail "couldn't install uv from astral.sh. Check your internet connection or proxy."
    UV="$HOME/.local/bin/uv"
    [ -x "$UV" ] || UV="$(command -v uv 2>/dev/null || true)"
    [ -n "$UV" ] && [ -x "$UV" ] || fail "uv was installed but can't be found. Open a new terminal and run this again."
fi

say "Installing bimai ..."
"$UV" tool install --upgrade --quiet "$PACKAGE" \
    || fail "couldn't install bimai. Check your internet connection or proxy (pypi.org must be reachable)."
"$UV" tool update-shell --quiet >/dev/null 2>&1 || true

BIN="$("$UV" tool dir --bin 2>/dev/null || printf '%s' "$HOME/.local/bin")"
VERSION="$("$BIN/bimai" --version 2>/dev/null || true)"
[ -n "$VERSION" ] || fail "bimai was installed but doesn't start. Please report this at https://github.com/StefanDaniels1/BIMAI/issues"

say ""
say "✓ $VERSION is installed."
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "  Open a new terminal so the 'bimai' command is found." ;;
esac
say "Next: go to your project folder and run  bimai init"
