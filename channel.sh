#!/usr/bin/env bash
# ReelForge: your channel's questions from first-time setup, to change your answers. It rewrites CLAUDE.md /
# AGENTS.md when you finish. "reelforge channel" does the same.
exec "$(dirname "$0")/bin/reelforge" channel "$@"
