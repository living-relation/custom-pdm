@echo off
rem Double-click: starts the PDM UI (simulator bridge + app) if needed and opens http://localhost:5000/pdm
rem Options are passed on to Start-PdmUi.ps1, e.g.  "Start PDM UI.cmd" -Stop
title Start PDM UI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-PdmUi.ps1" %*
if errorlevel 1 (
  echo.
  pause
)
