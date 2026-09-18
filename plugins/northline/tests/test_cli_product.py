import json
import subprocess
import sys
from pathlib import Path


def run_cli(*arguments: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "northline.cli", *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_cli_initializes_contract_and_resumes_status(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, check=True)
    workspace = str(tmp_path)
    initialized = run_cli(
        "init",
        "--workspace",
        workspace,
        "--mission-id",
        "mission_cli",
        "--objective",
        "preserve root goal",
        "--constraint",
        "preserve API",
        "--criterion",
        "tests pass",
    )
    assert initialized["initialized"] is True
    saved = run_cli(
        "contract",
        "--workspace",
        workspace,
        "--contract-id",
        "contract_cli",
        "--objective",
        "implement parser",
        "--in-scope",
        "parser",
        "--allowed-file",
        "src/**/*.py",
        "--criterion",
        "parser tests pass",
        "--test",
        "pytest tests/test_parser.py",
    )
    resumed = run_cli("status", "--workspace", workspace)
    assert saved["contract_id"] == "contract_cli"
    assert saved["status"] == "planned"
    assert resumed["mission"]["mission_id"] == "mission_cli"
    assert resumed["contract_count"] == 1
    assert resumed["execution_count"] == 1
