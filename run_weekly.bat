@echo off
REM Double-click launcher for run_weekly.ps1
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_weekly.ps1"
pause
