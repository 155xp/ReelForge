@echo off
rem ReelForge onboarding: the interview that sets up your channel and writes CLAUDE.md / AGENTS.md.
rem Run it again any time to change your answers. In any terminal, "reelforge onboard" does the same.
call "%~dp0bin\reelforge.cmd" onboard %*
set code=%errorlevel%
if not "%code%"=="0" pause
exit /b %code%
