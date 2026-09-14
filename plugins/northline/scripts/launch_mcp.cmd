@echo off
setlocal
set "PLUGIN_ROOT=%~dp0.."
set "PYTHONPATH=%PLUGIN_ROOT%\src;%PYTHONPATH%"
set "PLUGIN_PYTHON=%PLUGIN_ROOT%\.venv-plugin\Scripts\python.exe"
set "RUNTIME_PYTHON="
if exist "%PLUGIN_PYTHON%" (
  "%PLUGIN_PYTHON%" -c "import jsonschema, mcp, northline" >nul 2>nul
  if not errorlevel 1 set "RUNTIME_PYTHON=%PLUGIN_PYTHON%"
)
if not defined RUNTIME_PYTHON if defined NORTHLINE_PYTHON if exist "%NORTHLINE_PYTHON%" (
  "%NORTHLINE_PYTHON%" -c "import jsonschema, mcp, northline" >nul 2>nul
  if not errorlevel 1 set "RUNTIME_PYTHON=%NORTHLINE_PYTHON%"
)
if not defined RUNTIME_PYTHON (
  python -c "import jsonschema, mcp, northline" >nul 2>nul
  if not errorlevel 1 set "RUNTIME_PYTHON=python"
)
if not defined RUNTIME_PYTHON (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\scripts\setup_plugin.ps1" 1>&2
  if errorlevel 1 exit /b %errorlevel%
  set "RUNTIME_PYTHON=%PLUGIN_PYTHON%"
)
"%RUNTIME_PYTHON%" -m northline.mcp_server
