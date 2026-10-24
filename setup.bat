@echo off
rem ReelForge setup: double-click this file. It shows what ReelForge still needs (Python packages, Blender,
rem ffmpeg, the sound effects, the reelforge command), sets it all up in this folder once you say yes, checks
rem everything, then starts onboarding. Run it again any time to repair or update the setup.
cd /d "%~dp0"
set PYTHONUTF8=1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set code=%errorlevel%
if not "%code%"=="0" (
    echo.
    echo Setup didn't finish cleanly. Read the messages above, fix what they say, and run setup.bat again.
    pause
)
exit /b %code%
