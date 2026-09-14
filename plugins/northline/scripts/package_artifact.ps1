param(
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepositoryRoot = (Resolve-Path (Join-Path $ProjectRoot "..\..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path (Split-Path $ProjectRoot -Parent) -Parent) "outputs"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ("northline-artifact-" + [guid]::NewGuid().ToString("N"))
$StageRoot = Join-Path $Stage "northline"
$Archive = Join-Path $OutputDirectory "northline-stage2.zip"
$Checksum = Join-Path $OutputDirectory "northline-stage2.sha256.txt"

try {
    New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null
    $Directories = @(".codex-plugin", "assets", "docs", "experiments", "scripts", "skills", "src", "tests")
    $Files = @(".mcp.json", "LICENSE", "pyproject.toml", "README.md")
    foreach ($Directory in $Directories) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $Directory) -Destination $StageRoot -Recurse
    }
    foreach ($File in $Files) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $StageRoot
    }
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot ".github") -Destination $StageRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot ".gitignore") -Destination $StageRoot
    $ResultsDestination = Join-Path $StageRoot "results"
    New-Item -ItemType Directory -Path $ResultsDestination -Force | Out-Null
    $PublishableResults = @(
        "analysis.json",
        "controlled-evaluator-validation.json",
        "controlled-blueprint-audit.json",
        "controlled-pilot-build.json",
        "controlled-pilot-episode-summary.json",
        "environment.json",
        "power-analysis.json",
        "review-adjudication.json",
        "screening-plan.json",
        "smoke_summary.json",
        "synthetic_faults.json",
        "task-image-manifest.json",
        "task-image-validation.json",
        "suite-promotion.json"
    )
    foreach ($Result in $PublishableResults) {
        $Source = Join-Path (Join-Path $ProjectRoot "results") $Result
        if (Test-Path -LiteralPath $Source) {
            Copy-Item -LiteralPath $Source -Destination $ResultsDestination
        }
    }
    Get-ChildItem -LiteralPath $StageRoot -Directory -Recurse -Force |
        Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
        Remove-Item -Recurse -Force
    $ForbiddenArtifacts = Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | Where-Object {
        $_.Name -match "oracle|gold\.patch|episodes\.jsonl" -or $_.Extension -eq ".parquet"
    }
    if ($ForbiddenArtifacts) {
        throw "Refusing to package sealed or raw episode artifacts: $($ForbiddenArtifacts.FullName -join ', ')"
    }
    Compress-Archive -LiteralPath $StageRoot -DestinationPath $Archive -CompressionLevel Optimal -Force
    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $Checksum -Value "$Hash  northline-stage2.zip" -Encoding ascii
    Write-Output $Archive
    Write-Output $Checksum
} finally {
    $ResolvedStage = [System.IO.Path]::GetFullPath($Stage)
    $TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($ResolvedStage.StartsWith($TempRoot) -and (Split-Path $ResolvedStage -Leaf).StartsWith("northline-artifact-")) {
        Remove-Item -LiteralPath $ResolvedStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}
