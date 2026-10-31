@echo off
rem Menu for the forecast service (Windows). Double-click to open the menu.
rem Automation: start.bat start ^| open ^| forecast ^| test ^| logs ^| rebuild ^| stop
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\menu.ps1" %*
if errorlevel 1 pause
