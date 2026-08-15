@echo off
cd /d %~dp0
echo.
echo ===========================================
echo MATRIX BET V5.2 MOBILE
echo ===========================================
echo.
echo IPs do computador:
ipconfig | findstr /i "IPv4"
echo.
echo No notebook: http://localhost:8000
echo No celular:  http://SEU_IP_ACIMA:8000
echo.
echo Se o Firewall perguntar, permita em REDE PRIVADA.
echo ===========================================
echo.
C:\Python\Python311\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
