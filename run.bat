@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   ArgM&ArgG Evaluation System - Agricultural Mechanization-
echo   Greening Coupling Coordination Assessment and Forecasting
echo   Open in your browser: http://127.0.0.1:8000
echo   Close this window to stop the service
echo ============================================================
python app.py
pause
