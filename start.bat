@echo off
echo Starting eBay Arbitrage...
echo.
echo Backend: http://localhost:8011
echo Frontend: http://localhost:5173
echo.
wt -w ebay-arbitrage new-tab --title "eBay Arbitrage - Backend" --suppressApplicationTitle cmd /k "cd /d %~dp0 && python run_backend.py" ; new-tab --title "eBay Arbitrage - Frontend" --suppressApplicationTitle cmd /k "cd /d %~dp0frontend && npm run dev"
echo Both servers started in Windows Terminal tabs.
