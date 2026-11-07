@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno Python. Consulta README.md para instalarlo.
  pause
  exit /b 1
)
set "CANELA_OPEN_BROWSER=1"
".venv\Scripts\python.exe" run_local.py
pause
