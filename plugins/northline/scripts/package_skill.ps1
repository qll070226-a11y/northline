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
$Version = (Get-Content -LiteralPath (Join-Path $ProjectRoot ".codex-plugin\plugin.json") -Raw | ConvertFrom-Json).version
$ArchiveName = "northline-skill-$Version.zip"
$Archive = Join-Path $OutputDirectory $ArchiveName
$Checksum = Join-Path $OutputDirectory "northline-skill-$Version.sha256.txt"
Compress-Archive -LiteralPath $Source -DestinationPath $Archive -CompressionLevel Optimal -Force
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $Checksum -Value "$Hash  $ArchiveName" -Encoding ascii
Write-Output $Archive
Write-Output $Checksum
