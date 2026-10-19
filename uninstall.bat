@echo off
setlocal
cd /d "%~dp0"
title g-script uninstaller
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo  Python 3 was not found.
  echo  Install it once with:  winget install -e --id Python.Python.3.12
  echo  or from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo  then run install.bat again.
  echo.
  pause
  exit /b 1
)
%PY% install.py --uninstall %*
echo.
pause
