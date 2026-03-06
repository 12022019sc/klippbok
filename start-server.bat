@echo off
title Klippbok Server
echo Starting Klippbok server on http://localhost:9000 ...
echo Press Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m klippbok.api --port 9000
pause
