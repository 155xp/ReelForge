#!/usr/bin/env bash
# Opens ReelForge: your stats, and the Publish tab where finished videos wait for you to post them.
# The first time, it runs first-time setup. "./reelforge.sh 4" opens tab 4; "./reelforge.sh --demo" shows
# made-up stats. Once setup has added it, "reelforge" in any terminal does the same.
exec "$(dirname "$0")/bin/reelforge" "$@"
