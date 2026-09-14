import copy
import json
import unittest

from experiments.freeze_controlled_tasks import SEALED_KEYS, freeze


def task(index):
    return {
        "source_id": f"source-{index:03d}",
        "task_family_id": f"family-{index:03d}",
        "repository": f"repo-{index % 8}",
        "base_commit": f"{index:040x}"[-40:],
        "container_image": f"registry/repo-{index % 8}@sha256:" + f"{index + 1:064x}"[-64:],
        "container_image_kind": "task_image",
        "objective": f"Fix controlled behavior {index}",
        "task_type": "bug_fix",
        "public_constraints": ["preserve API"],
        "allowed_files": ["src/**/*.py"],
        "forbidden_files": ["pyproject.toml"],
        "required_tests": ["pytest -q tests/test_visible.py"],
        "hidden_tests": ["pytest -q tests/test_hidden.py"],
        "setup_command": "python -m pip install -e .",
        "injected_fault": "scope_conflict",
    }


class ControlledTaskFreezeTests(unittest.TestCase):
    def source(self):
        return {"version": "1.0", "tasks": [task(index) for index in range(120)]}

    def test_freeze_separates_agent_and_oracle_fields(self):
        manifest, oracle, report = freeze(self.source())
        for key in SEALED_KEYS:
            self.assertNotIn(f'"{key}"', json.dumps(manifest["tasks"][0]["agent_context"]))
        self.assertNotIn("hidden_tests", json.dumps(manifest["tasks"]))
        self.assertIn("hidden_tests", json.dumps(oracle))
        self.assertEqual(report["task_count"], 120)
        self.assertEqual(report["task_family_count"], 120)

    def test_freeze_rejects_unpinned_image(self):
        source = self.source()
        source["tasks"][0]["container_image"] = "registry/latest"
        with self.assertRaisesRegex(ValueError, "image digest"):
            freeze(source)

    def test_confirmatory_freeze_rejects_base_image_only(self):
        source = self.source()
        source["tasks"][0]["container_image_kind"] = "base_image"
        with self.assertRaisesRegex(ValueError, "task-level"):
            freeze(source)

    def test_freeze_rejects_insufficient_independent_families(self):
        source = copy.deepcopy(self.source())
        for item in source["tasks"]:
            item["task_family_id"] = "one-family"
        with self.assertRaisesRegex(ValueError, "distinct independent"):
            freeze(source)


if __name__ == "__main__":
    unittest.main()
