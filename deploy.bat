@echo off
REM Force UTF-8 console + bypass execution policy for this single run
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1"
pause
