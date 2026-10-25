@echo off
setlocal
set ROOT=%~dp0

echo [QUADRANT] Starting READ ONLY RSS backend...
start "QUADRANT BACKEND - RSS READ ONLY" cmd /k "pushd ""%ROOT%backend"" && set QUADRANT_DATA_SOURCE=rss && call .venv\Scripts\activate.bat && python -m uvicorn app:app --host 0.0.0.0 --port 8765"

timeout /t 2 /nobreak >nul

echo [QUADRANT] Starting frontend...
start "QUADRANT FRONTEND" cmd /k "cd /d "%ROOT%frontend" && npm run dev -- --host 0.0.0.0"

echo.
echo QUADRANT started in READ ONLY mode.
echo Local: http://localhost:1420/
echo LAN/Tailscale: use this PC's IP with port 1420.
echo.
pause
