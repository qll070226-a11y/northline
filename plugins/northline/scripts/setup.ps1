$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PreferredPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"

if (-not (Test-Path -LiteralPath $PreferredPython)) {
    throw "Official Windows CPython 3.12 was not found at $PreferredPython. Install Python.Python.3.12 with winget first."
}

$VirtualEnvironment = Join-Path $ProjectRoot ".venv-win"
if (-not (Test-Path -LiteralPath (Join-Path $VirtualEnvironment "Scripts\python.exe"))) {
    & $PreferredPython -m venv $VirtualEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment." }
}

$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"
& $Python -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to install packaging tools." }
& $Python -m pip install --no-build-isolation -e "${ProjectRoot}[dev,mcp,research,langgraph,benchmark,openai]"
if ($LASTEXITCODE -ne 0) { throw "Failed to install project dependencies." }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency consistency check failed." }
