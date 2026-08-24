@echo off
cd /d %~dp0
C:\Python\Python311\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
