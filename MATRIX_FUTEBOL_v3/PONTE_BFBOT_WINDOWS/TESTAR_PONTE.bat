@echo off
title MATRIX FUTEBOL - TESTAR PONTE
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri 'https://matrix-bet.onrender.com/api/bfbot/bridge' -TimeoutSec 20; $r | ConvertTo-Json -Depth 5 } catch { Write-Host $_.Exception.Message -ForegroundColor Red }"
pause
