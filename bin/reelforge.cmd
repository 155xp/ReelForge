@echo off
rem "reelforge" in any terminal opens ReelForge. Try: reelforge 4, reelforge videos, reelforge help.
rem Setup (or the installer) puts this folder on your PATH. It runs with ReelForge's own Python (.venv).
rem An update can rewrite this file while it runs, and cmd reads a running script by position, so each run, its
rem checks and the exit sit on one line: exit code 75 means "updated, start again"; 3, 101 and 103 mean the Python
rem environment needs repairing (packages missing, or the Python it was made with is gone).
setlocal EnableDelayedExpansion
set "RF=%~dp0.."
set PYTHONUTF8=1
if not exist "%RF%\.venv\Scripts\python.exe" (echo ReelForge isn't set up yet. Starting setup... & call "%RF%\setup.bat" & exit /b !errorlevel!)
:again
"%RF%\.venv\Scripts\python.exe" "%RF%\bin\reelforge.py" %* & (if errorlevel 75 if not errorlevel 76 goto :again) & (if errorlevel 3 if not errorlevel 4 goto :repair) & (if errorlevel 101 if not errorlevel 102 goto :repair) & (if errorlevel 103 if not errorlevel 104 goto :repair) & exit /b !errorlevel!
:repair
echo ReelForge's Python environment needs repairing. Starting setup... & call "%RF%\setup.bat" & exit /b !errorlevel!
