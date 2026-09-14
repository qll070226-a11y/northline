import subprocess
import tempfile
import unittest
from pathlib import Path

from northline.models import DelegationContract
from northline.scope import assess_parallel_safety
from northline.workspace import GitWorkspace


def make_contract(contract_id: str, allowed: tuple[str, ...], dependencies: tuple[str, ...] = ()) -> DelegationContract:
    return DelegationContract(
        contract_id=contract_id,
        objective="task",
        in_scope=("task",),
        out_of_scope=(),
        allowed_files=allowed,
        forbidden_files=(),
        acceptance_criteria=("pass",),
        required_tests=("test",),
        base_commit="base",
        parent_id="root",
        mission_id="mission",
        dependencies=dependencies,
    )


class ScopeWorkspaceTests(unittest.TestCase):
    def test_disjoint_scopes_can_run_in_parallel(self):
        left = make_contract("left", ("src/parser/**",))
        right = make_contract("right", ("tests/parser/**",))
        self.assertTrue(assess_parallel_safety(left, right).safe)

    def test_shared_scope_or_dependency_requires_serial_execution(self):
        left = make_contract("left", ("src/**/*.py",))
        right = make_contract("right", ("src/parser/**",), ("left",))
        result = assess_parallel_safety(left, right)
        self.assertFalse(result.safe)
        self.assertGreaterEqual(len(result.reasons), 2)

    def test_git_worktree_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "file.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            workspace = GitWorkspace(repo)
            head = workspace.head()
            worktree_path = Path(temp) / "child"
            child = workspace.create_worktree(worktree_path, head)
            self.assertEqual(child.head(), head)
            success, _ = child.run_tests("git status --short")
            self.assertTrue(success)
            workspace.remove_worktree(worktree_path)


if __name__ == "__main__":
    unittest.main()
