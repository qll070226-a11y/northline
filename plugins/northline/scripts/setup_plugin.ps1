$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VirtualEnvironment = Join-Path $ProjectRoot ".venv-plugin"

$Candidates = @()
if ($env:NORTHLINE_PYTHON) {
    $Candidates += ,@($env:NORTHLINE_PYTHON)
}
$PreferredPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (Test-Path -LiteralPath $PreferredPython) {
    $Candidates += ,@($PreferredPython)
}
$Candidates += ,@("python")
$Candidates += ,@("py", "-3.12")
$Candidates += ,@("py", "-3")

$BootstrapCommand = $null
$BootstrapPrefix = @()
foreach ($Candidate in $Candidates) {
    $Command = Get-Command $Candidate[0] -ErrorAction SilentlyContinue
    if (-not $Command) { continue }
    $Prefix = @($Candidate | Select-Object -Skip 1)
    $ProbeSucceeded = $false
    try {
        $PreviousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & $Command.Source @Prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        $ProbeSucceeded = $LASTEXITCODE -eq 0
    } catch {
        $ProbeSucceeded = $false
    } finally {
        $ErrorActionPreference = $PreviousErrorAction
    }
    if ($ProbeSucceeded) {
        $BootstrapCommand = $Command.Source
        $BootstrapPrefix = $Prefix
        break
    }
}
if (-not $BootstrapCommand) {
    throw "Python 3.10 or newer is required. Set NORTHLINE_PYTHON to an interpreter path if it is not on PATH."
}

if (-not (Test-Path -LiteralPath (Join-Path $VirtualEnvironment "Scripts\python.exe"))) {
    & $BootstrapCommand @BootstrapPrefix -m venv $VirtualEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the plugin virtual environment." }
}

$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check --timeout 30 --retries 2 setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to install packaging tools." }
& $Python -m pip install --disable-pip-version-check --timeout 30 --retries 2 --no-build-isolation -e "${ProjectRoot}[mcp]"
if ($LASTEXITCODE -ne 0) { throw "Failed to install the plugin runtime." }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Plugin dependency consistency check failed." }
& $Python -m northline.cli demo | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Plugin smoke test failed." }
Write-Output "Plugin runtime ready: $VirtualEnvironment"
