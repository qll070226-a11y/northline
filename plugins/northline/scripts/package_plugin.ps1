param(
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path (Split-Path $ProjectRoot -Parent) -Parent) "outputs"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ("northline-plugin-" + [guid]::NewGuid().ToString("N"))
$StageRoot = Join-Path $Stage "northline"
$Archive = Join-Path $OutputDirectory "northline-plugin-0.2.0.zip"
$Checksum = Join-Path $OutputDirectory "northline-plugin-0.2.0.sha256.txt"

try {
    New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null
    foreach ($Directory in @(".codex-plugin", "assets", "skills", "src")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $Directory) -Destination $StageRoot -Recurse
    }
    foreach ($File in @(".mcp.json", "LICENSE", "pyproject.toml", "README.md")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $StageRoot
    }
    $Scripts = Join-Path $StageRoot "scripts"
    New-Item -ItemType Directory -Path $Scripts -Force | Out-Null
    foreach ($File in @("launch_mcp.cmd", "setup_plugin.ps1")) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $ProjectRoot "scripts") $File) -Destination $Scripts
    }
    Get-ChildItem -LiteralPath $StageRoot -Directory -Recurse -Force |
        Where-Object { $_.Name -eq "__pycache__" } |
        Remove-Item -Recurse -Force
    $Forbidden = Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | Where-Object {
        $_.Name -match "oracle|gold\.patch|episodes\.jsonl" -or $_.Extension -in @(".parquet", ".pyc")
    }
    if ($Forbidden) {
        throw "Refusing to package sensitive or generated files: $($Forbidden.FullName -join ', ')"
    }
    Compress-Archive -LiteralPath $StageRoot -DestinationPath $Archive -CompressionLevel Optimal -Force
    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $Checksum -Value "$Hash  northline-plugin-0.2.0.zip" -Encoding ascii
    Write-Output $Archive
    Write-Output $Checksum
} finally {
    $ResolvedStage = [System.IO.Path]::GetFullPath($Stage)
    $TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($ResolvedStage.StartsWith($TempRoot) -and (Split-Path $ResolvedStage -Leaf).StartsWith("northline-plugin-")) {
        Remove-Item -LiteralPath $ResolvedStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}
