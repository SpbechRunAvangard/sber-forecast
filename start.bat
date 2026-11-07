@echo off
rem Menu for the forecast service (Windows). Double-click to open the menu.
rem Automation: start.bat start ^| open ^| forecast ^| test ^| logs ^| rebuild ^| stop
rem Works both from the project root and from the start\ subfolder.
chcp 65001 >nul
set "ROOT=%~dp0"
if not exist "%ROOT%scripts\menu.ps1" set "ROOT=%~dp0..\"
if not exist "%ROOT%scripts\menu.ps1" (
  echo [X] scripts\menu.ps1 not found. Keep start.bat in the project folder or in its start\ subfolder.
  pause
  exit /b 1
)
cd /d "%ROOT%"
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%ROOT%scripts\menu.ps1" %*
if not "%errorlevel%"=="0" pause
