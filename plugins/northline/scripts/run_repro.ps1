$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv-win. Run scripts/setup.ps1 to install all development, runtime, benchmark, and model dependencies."
}

Push-Location $ProjectRoot
try {
    function Invoke-CheckedPython {
        param([string[]]$CommandArgs)
        & $Python @CommandArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed with exit code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
        }
    }

    Invoke-CheckedPython @("-m", "pytest", "-q", "-p", "no:cacheprovider")
    Invoke-CheckedPython @("-m", "ruff", "check", "src", "experiments", "tests", "scripts")
    Invoke-CheckedPython @("experiments\generate_tasks.py")
    Invoke-CheckedPython @("experiments\run_episodes.py", "experiments\generated\synthetic_tasks.json", "experiments\screening.example.json", "--plan-only", "--output", "results\screening-plan.json")
    Invoke-CheckedPython @("experiments\synthetic_faults.py")
    Invoke-CheckedPython @("experiments\audit_controlled_blueprints.py", "..\benchmark-data\controlled_pilot_blueprints.json", "--expected-count", "32", "--output", "results\controlled-blueprint-audit.json")
    Invoke-CheckedPython @("experiments\build_task_images.py", "..\benchmark-data\controlled_pilot_source.json", "--output", "results\task-image-manifest.json", "--context-root", "..\benchmark-data\controlled-pilot-images", "--build")
    Invoke-CheckedPython @("experiments\validate_task_images.py", "results\task-image-manifest.json", "..\benchmark-data\controlled_pilot_source.json", "--output", "results\task-image-validation.json")
    Invoke-CheckedPython @("experiments\review_protocol.py", "create", "..\benchmark-data\controlled_pilot_source.json", "--output-root", "..\benchmark-data\controlled-pilot-review", "--ratings", "..\benchmark-data\controlled-pilot-review\ratings.csv")
    Invoke-CheckedPython @("experiments\promote_suite.py", "results\task-image-validation.json", "..\benchmark-data\controlled-pilot-review\review-protocol.json", "--blueprint-audit", "results\controlled-blueprint-audit.json", "--output", "results\suite-promotion.json")
    Invoke-CheckedPython @("experiments\smoke.py")
    Invoke-CheckedPython @("experiments\analysis.py", "results\smoke.jsonl", "--baseline", "flat_multi_agent", "--treatment", "full_protocol", "--output", "results\analysis.json")
    Invoke-CheckedPython @("experiments\power_analysis.py", "--output", "results\power-analysis.json")
    Invoke-CheckedPython @("scripts\environment_report.py")
    Invoke-CheckedPython @("-m", "northline.cli", "demo")
    Invoke-CheckedPython @("-m", "northline.cli", "forward-test", "--output", "results\product-forward-test.json")
} finally {
    Pop-Location
}
