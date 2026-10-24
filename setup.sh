#!/usr/bin/env bash
# ReelForge setup for macOS and Linux (experimental: ReelForge is built and tested on Windows).
#   ./setup.sh          one list of what's missing, one yes, then onboarding
#   ./setup.sh --yes    the same without questions
# Once Python is found, studio/bootstrap.py draws the first-run box and does the rest.
set -euo pipefail
cd "$(dirname "$0")"
chmod +x ./*.sh bin/reelforge 2>/dev/null || true

find_python() {
  for exe in python3.13 python3.12 python3.11 python3.14 python3 python; do
    if command -v "$exe" >/dev/null 2>&1 && "$exe" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      command -v "$exe"
      return 0
    fi
  done
  return 1
}

if ! PY="$(find_python)"; then
  echo
  echo "  reelforge setup"
  echo
  echo "  ReelForge runs on Python 3.11 or newer, which wasn't found."
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "  Install it with Homebrew (brew install python@3.13 ffmpeg) or from https://www.python.org/downloads/,"
  else
    echo "  Install it with your package manager (e.g. sudo apt install python3.12 python3.12-venv ffmpeg),"
  fi
  echo "  then run ./setup.sh again."
  exit 1
fi

export PYTHONUTF8=1
exec "$PY" -m studio.bootstrap "$@"
