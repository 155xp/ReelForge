@echo off
rem Opens ReelForge: your stats, and the Publish tab where finished videos wait for you to post them.
rem The first time, it runs setup and onboarding. "ReelForge.bat 4" opens tab 4; "ReelForge.bat --demo" shows
rem made-up stats. In any terminal, "reelforge" does the same. (One line on purpose: an update can rewrite this
rem file while ReelForge runs.)
title ReelForge
setlocal EnableDelayedExpansion
call "%~dp0bin\reelforge.cmd" %* & (if errorlevel 1 (echo. & echo ReelForge stopped with an error, see above. & pause)) & exit /b !errorlevel!
