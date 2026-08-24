@echo off
title MATRIX FUTEBOL - PONTE BF BOT
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ponte_bfbot.ps1"
pause
