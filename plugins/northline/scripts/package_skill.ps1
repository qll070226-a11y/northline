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
$Source = Join-Path $ProjectRoot "skills\northline"
$Archive = Join-Path $OutputDirectory "northline-skill-0.2.0.zip"
$Checksum = Join-Path $OutputDirectory "northline-skill-0.2.0.sha256.txt"
Compress-Archive -LiteralPath $Source -DestinationPath $Archive -CompressionLevel Optimal -Force
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $Checksum -Value "$Hash  northline-skill-0.2.0.zip" -Encoding ascii
Write-Output $Archive
Write-Output $Checksum
