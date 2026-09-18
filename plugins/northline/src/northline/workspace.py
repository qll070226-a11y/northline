from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class TestEvidence:
    command: str
    passed: bool
    returncode: int
    output: str


@dataclass(frozen=True)
class RepositoryEvidence:
    base_commit: str
    result_commit: str
    workspace_head: str
    base_exists: bool
    result_exists: bool
    result_descends_from_base: bool
    workspace_clean: bool
    workspace_status: tuple[str, ...]
    changed_files: tuple[str, ...]
    tests: tuple[TestEvidence, ...]


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

    def commit_exists(self, commit: str) -> bool:
        process = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=self.path,
            text=True,
            capture_output=True,
            check=False,
        )
        return process.returncode == 0

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        process = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=self.path,
            text=True,
            capture_output=True,
            check=False,
        )
        return process.returncode == 0

    def changed_files(self, base_commit: str) -> tuple[str, ...]:
        output = self._run("diff", "--name-only", base_commit, "HEAD")
        return tuple(line for line in output.splitlines() if line)

    def changed_files_between(self, base_commit: str, result_commit: str) -> tuple[str, ...]:
        output = self._run("diff", "--name-only", base_commit, result_commit)
        return tuple(line.replace("\\", "/") for line in output.splitlines() if line)

    def status_porcelain(self) -> tuple[str, ...]:
        output = self._run("status", "--porcelain")
        return tuple(line for line in output.splitlines() if line)

    def run_tests(self, command: str, *, timeout_seconds: float = 600) -> tuple[bool, str]:
        process = subprocess.run(
            command,
            cwd=self.path,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = (process.stdout + "\n" + process.stderr).strip()
        return process.returncode == 0, output

    def collect_evidence(
        self,
        base_commit: str,
        result_commit: str,
        required_tests: Sequence[str],
        *,
        timeout_seconds: float = 600,
    ) -> RepositoryEvidence:
        base_exists = self.commit_exists(base_commit)
        result_exists = self.commit_exists(result_commit)
        descends = base_exists and result_exists and self.is_ancestor(base_commit, result_commit)
        files = self.changed_files_between(base_commit, result_commit) if base_exists and result_exists else ()
        workspace_status = self.status_porcelain()
        tests: list[TestEvidence] = []
        for command in required_tests:
            try:
                passed, output = self.run_tests(command, timeout_seconds=timeout_seconds)
                tests.append(TestEvidence(command, passed, 0 if passed else 1, output[-12000:]))
            except subprocess.TimeoutExpired as exc:
                output = "" if exc.stdout is None else str(exc.stdout)
                tests.append(TestEvidence(command, False, 124, f"timeout after {timeout_seconds}s\n{output}"[-12000:]))
        return RepositoryEvidence(
            base_commit=base_commit,
            result_commit=result_commit,
            workspace_head=self.head(),
            base_exists=base_exists,
            result_exists=result_exists,
            result_descends_from_base=descends,
            workspace_clean=not workspace_status,
            workspace_status=workspace_status,
            changed_files=files,
            tests=tuple(tests),
        )

    def create_worktree(self, target: Path, ref: str = "HEAD") -> "GitWorkspace":
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run("worktree", "add", "--detach", str(target), ref)
        return GitWorkspace(target)

    def remove_worktree(self, target: Path) -> None:
        self._run("worktree", "remove", "--force", str(target))
