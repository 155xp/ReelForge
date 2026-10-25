#!/usr/bin/env bash
# ReelForge setup for macOS and Linux.
#   ./setup.sh          one list of what's missing, one yes, then onboarding
#   ./setup.sh --yes    the same without questions (for an AI setting up for you, with your OK)
# Everything goes inside this folder (.venv, tools/, ui/node_modules); nothing is installed system-wide. Without Python
# 3.11 or newer it offers a private Python 3.13 in tools/python (about 25 MB, from the python-build-standalone project
# that uv and other tools use, checked against its published checksums). Once Python is found, studio/bootstrap.py
# draws the first-run box, gets the Python packages and Bun (which runs ReelForge's window), and does the rest.
set -euo pipefail
cd "$(dirname "$0")"
chmod +x ./*.sh bin/reelforge 2>/dev/null || true
chmod +x ./*.command 2>/dev/null || true
# macOS quarantines a zip downloaded in a browser and everything unpacked from it, so each launcher in it would need
# Open Anyway. You've chosen to set this folder up, so clear that once: its .command files then open with a
# double-click.
if [ "$(uname)" = Darwin ]; then xattr -dr com.apple.quarantine . 2>/dev/null || true; fi

YES=0
for arg in "$@"; do
  case "$arg" in --yes|-y) YES=1 ;; esac
done

# A Python 3.11+ that can make ReelForge's .venv (Debian and Ubuntu leave venv's pip out of their Python until
# python3-venv is installed: that one is passed over).
usable() {
  "$1" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

find_python() {
  if [ -x tools/python/bin/python3 ] && usable tools/python/bin/python3; then
    echo "$PWD/tools/python/bin/python3"
    return 0
  fi
  [ "${STUDIO_OWN_PYTHON:-}" = 1 ] && return 1          # tests: always use the private one
  for exe in python3.13 python3.12 python3.11 python3.14 python3 python; do
    path="$(command -v "$exe" 2>/dev/null)" || continue
    # macOS's /usr/bin/python3 is 3.9, and without Apple's developer tools it opens a box offering to install them
    if [ "$(uname)" = Darwin ] && [ "$path" = /usr/bin/python3 ]; then continue; fi
    if usable "$path"; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

fetch() {   # fetch URL FILE
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 -o "$2" "$1"
  else
    wget -q -O "$2" "$1"
  fi
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

own_python() {
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) triple=aarch64-apple-darwin ;;
    Darwin-x86_64) triple=x86_64-apple-darwin ;;
    Linux-x86_64) triple=x86_64-unknown-linux-gnu ;;
    Linux-aarch64|Linux-arm64) triple=aarch64-unknown-linux-gnu ;;
    *) echo "  There's no private Python for $(uname -s) on $(uname -m)."; return 1 ;;
  esac
  mkdir -p tools/downloads
  local index="tools/downloads/python-latest.json" sums="tools/downloads/python-SHA256SUMS" prefix line want name
  echo "  Finding the newest Python 3.13..."
  fetch "https://raw.githubusercontent.com/astral-sh/python-build-standalone/latest-release/latest-release.json" \
    "$index" || return 1
  prefix="$(sed -n 's/.*"asset_url_prefix": *"\([^"]*\)".*/\1/p' "$index")"
  fetch "$prefix/SHA256SUMS" "$sums" || return 1
  line="$(grep -E "  cpython-3\.13\.[0-9]+\+[0-9]+-$triple-install_only_stripped\.tar\.gz$" "$sums" | tail -n 1 || true)"
  rm -f "$index" "$sums"
  [ -n "$line" ] || { echo "  The newest release has no Python 3.13 for $triple."; return 1; }
  want="${line%% *}"
  name="${line##* }"
  echo "  Downloading $name..."
  fetch "$prefix/${name//+/%2B}" "tools/downloads/$name" || return 1
  if [ "$(sha256 "tools/downloads/$name")" != "$want" ]; then
    rm -f "tools/downloads/$name"
    echo "  The download doesn't match its checksum (damaged on the way); run setup again."
    return 1
  fi
  rm -rf tools/python
  tar -xzf "tools/downloads/$name" -C tools        # unpacks to tools/python
  rm -f "tools/downloads/$name"
  usable tools/python/bin/python3
}

if ! PY="$(find_python)"; then
  echo
  echo "  reelforge setup"
  echo
  echo "  ReelForge runs on Python 3.11 or newer, which isn't on this computer yet."
  echo "  It can put a private Python 3.13 in this folder now (about 25 MB, for ReelForge only: nothing else changes)."
  echo
  answer=y
  if [ "$YES" = 1 ]; then
    echo "  Download Python 3.13 now? yes (--yes)"
  elif [ -t 0 ]; then
    read -r -p "  Download Python 3.13 now? [Y/n] " answer || answer=n
  else
    answer=n
  fi
  case "$answer" in
    ""|y|Y|yes|Yes|YES) own_python || true ;;
  esac
  if ! PY="$(find_python)"; then
    echo
    if [ "$(uname)" = Darwin ]; then
      echo "  Or install Python 3.13 from https://www.python.org/downloads/ (or: brew install python@3.13),"
    else
      echo "  Or install Python 3.11+ with venv from your package manager (e.g. sudo apt install python3 python3-venv),"
    fi
    echo "  then run ./setup.sh again."
    exit 1
  fi
fi

export PYTHONUTF8=1
exec "$PY" -m studio.bootstrap "$@"
