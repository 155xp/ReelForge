#!/usr/bin/env bash
# ReelForge's one-line install for macOS and Linux. Paste this into Terminal:
#   curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | bash
# It downloads the newest ReelForge-<version>-macOS.zip (or -Linux.tar.gz) from GitHub, checks it against the
# release's SHA256SUMS.txt, unpacks it into your home folder (~/ReelForge) and runs ./setup.sh there, the first-run
# screens. Nothing goes through the browser, so macOS has nothing to quarantine and Gatekeeper doesn't stop it. It
# never touches a ReelForge folder that's already there: update that one from its Updates tab. To change what it does,
# put these before bash:
#   ... | REELFORGE_DIR=~/Apps/ReelForge bash     install somewhere else
#   ... | REELFORGE_NO_SETUP=1 bash               only download and unpack; run ./setup.sh yourself later
#   ... | bash -s -- --yes                        set up without questions (for an AI, with your OK)
#   REELFORGE_RELEASE=<url>                       take the downloads from somewhere else (the test workflow)
# The release workflow attaches this file to every release. macOS runs it with its bash 3.2, so it stays plain.

main() {
  set -eu
  local release="${REELFORGE_RELEASE:-https://github.com/dan2756/ReelForge/releases/latest/download}"
  local kind ext
  case "$(uname -s)" in
    Darwin) kind=macOS; ext='zip' ;;
    Linux) kind=Linux; ext='tar\.gz' ;;
    *)
      echo "This installs ReelForge on macOS or Linux. On Windows, paste this into PowerShell instead:"
      echo "  irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 | iex"
      return 1 ;;
  esac

  local dir="${REELFORGE_DIR:-$HOME/ReelForge}"
  case "$dir" in /*) ;; *) dir="$PWD/$dir" ;; esac
  if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
    echo "There's already a ReelForge folder at $dir, so nothing was changed."
    echo "To update it, open ReelForge and go to Updates (type reelforge updates). To put another copy somewhere else:"
    echo "  curl -fsSL $release/install.sh | REELFORGE_DIR=~/ReelForge2 bash"
    return 0
  fi
  # A ReelForge kept somewhere else has its reelforge command linked in ~/.local/bin. That one moves into its own
  # folder from its Settings tab, rather than a second copy being made here.
  if [ -z "${REELFORGE_DIR:-}" ] && [ -L "$HOME/.local/bin/reelforge" ]; then
    local there
    there="$(dirname "$(dirname "$(readlink "$HOME/.local/bin/reelforge")")")"
    if [ -f "$there/studio/__init__.py" ] && [ ! -f "$there/TEST-COPY.txt" ]; then
      echo "ReelForge is already on this computer, in $there, so nothing was changed."
      echo "To put it in its own folder ($dir), open ReelForge and click Move next to ReelForge's folder on its"
      echo "Settings tab (if there's no Move yet, update it on its Updates tab first). To install a second copy anyway:"
      echo "  curl -fsSL $release/install.sh | REELFORGE_DIR=~/ReelForge2 bash"
      return 0
    fi
  fi
  local unpacker=tar
  [ "$kind" = Linux ] || unpacker=unzip
  if ! command -v "$unpacker" >/dev/null 2>&1; then
    echo "ReelForge wasn't installed: $unpacker is missing."
    return 1
  fi

  local work
  work="$(mktemp -d "${TMPDIR:-/tmp}/reelforge-install.XXXXXX")"
  if ! fetch_release "$release" "$kind" "$ext" "$work" "$dir"; then
    rm -rf "$work"
    return 1
  fi
  rm -rf "$work"

  echo "ReelForge is in $dir"
  if [ -n "${REELFORGE_NO_SETUP:-}" ]; then
    echo "Run ./setup.sh in that folder when you're ready to set it up."
    return 0
  fi
  echo "Starting setup..."
  cd "$dir"
  # The install line hands bash this script on its keyboard input, so setup reads the keyboard from the terminal
  if (exec </dev/tty) 2>/dev/null; then
    ./setup.sh "$@" </dev/tty
  else
    ./setup.sh "$@"
  fi
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

fetch_release() {   # fetch_release RELEASE KIND EXT WORK DIR: download, check and unpack the newest package into DIR
  local release="$1" kind="$2" ext="$3" work="$4" dir="$5" line want name top
  echo "Finding the newest ReelForge..."
  fetch "$release/SHA256SUMS.txt" "$work/SHA256SUMS.txt" || { echo "ReelForge wasn't installed: GitHub couldn't be reached."; return 1; }
  line="$(grep -E "^[0-9a-fA-F]{64} +\*?ReelForge-[0-9A-Za-z.-]+-$kind\.$ext\$" "$work/SHA256SUMS.txt" | head -n 1 || true)"
  if [ -z "$line" ]; then
    echo "ReelForge wasn't installed: the newest release lists no $kind download in SHA256SUMS.txt."
    return 1
  fi
  want="$(printf '%s' "${line%% *}" | tr 'A-F' 'a-f')"
  name="${line##* }"
  name="${name#\*}"
  echo "Downloading $name..."
  fetch "$release/$name" "$work/$name" || { echo "ReelForge wasn't installed: the download stopped."; return 1; }
  if [ "$(sha256 "$work/$name")" != "$want" ]; then
    echo "ReelForge wasn't installed: $name doesn't match its checksum in SHA256SUMS.txt (the download broke or was changed)."
    return 1
  fi
  echo "Unpacking it into $dir..."
  mkdir -p "$work/unpack" "$(dirname "$dir")"
  if [ "$kind" = macOS ]; then
    unzip -q "$work/$name" -d "$work/unpack"       # keeps the scripts runnable
  else
    tar -xzf "$work/$name" -C "$work/unpack"
  fi
  top="$(ls -A "$work/unpack")"
  if [ "$(printf '%s\n' "$top" | wc -l | tr -d ' ')" != 1 ] || [ ! -d "$work/unpack/$top" ]; then
    echo "ReelForge wasn't installed: $name isn't laid out the way ReelForge's are."
    return 1
  fi
  [ -d "$dir" ] && rmdir "$dir"                    # the empty folder found earlier
  mv "$work/unpack/$top" "$dir"
}

main "$@"
