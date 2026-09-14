from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitWorkspace:
    path: Path

    def _run(self, *args: str) -> str:
        process = subprocess.run(["git", *args], cwd=self.path, text=True, capture_output=True, check=False)
        if process.returncode:
            raise WorkspaceError(process.stderr.strip() or "git command failed")
        return process.stdout.strip()

    def head(self) -> str:
        return self._run("rev-parse", "HEAD")

    def changed_files(self, base_commit: str) -> tuple[str, ...]:
        output = self._run("diff", "--name-only", base_commit, "HEAD")
        return tuple(line for line in output.splitlines() if line)

    def run_tests(self, command: str) -> tuple[bool, str]:
        process = subprocess.run(command, cwd=self.path, shell=True, text=True, capture_output=True)
        output = (process.stdout + "\n" + process.stderr).strip()
        return process.returncode == 0, output

    def create_worktree(self, target: Path, ref: str = "HEAD") -> "GitWorkspace":
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run("worktree", "add", "--detach", str(target), ref)
        return GitWorkspace(target)

    def remove_worktree(self, target: Path) -> None:
        self._run("worktree", "remove", "--force", str(target))
