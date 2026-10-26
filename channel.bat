@echo off
rem ReelForge: your channel's questions from first-time setup, to change your answers. It rewrites CLAUDE.md /
rem AGENTS.md when you finish. In any terminal, "reelforge channel" does the same.
call "%~dp0bin\reelforge.cmd" channel %*
set code=%errorlevel%
if not "%code%"=="0" pause
exit /b %code%
