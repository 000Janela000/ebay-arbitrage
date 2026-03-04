@echo off
echo Starting eBay Arbitrage...
echo.
echo Backend: http://localhost:8011
echo Frontend: http://localhost:5173
echo.
start "Backend" cmd /c "cd /d %~dp0 && python run_backend.py"
start "Frontend" cmd /c "cd /d %~dp0\frontend && npm run dev"
echo Both servers started. Close the terminal windows to stop them.
