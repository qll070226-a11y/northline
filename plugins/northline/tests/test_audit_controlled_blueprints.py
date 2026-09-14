from experiments.audit_controlled_blueprints import audit


def _task(index: int, task_type: str = "bug_fix"):
    return {
        "source_id": f"task-{index}",
        "task_family_id": f"family-{index}",
        "repository": f"repo-{index % 8}",
        "task_type": task_type,
        "objective": "change behavior",
        "base_files": {"app.py": "base"},
        "gold_files": {"app.py": "gold"},
        "hidden_test_files": {"test_hidden.py": "test"},
    }


def test_audit_requires_balanced_32_task_design():
    tasks = [_task(index, ("bug_fix", "api_change", "test_completion", "refactor")[index // 8]) for index in range(32)]
    report = audit({"tasks": tasks})
    assert report["status"] == "ready_for_controlled_build"
    assert report["task_type_counts"] == {"api_change": 8, "bug_fix": 8, "refactor": 8, "test_completion": 8}


def test_audit_blocks_current_eight_task_pilot_shape():
    report = audit({"tasks": [_task(index) for index in range(8)]})
    assert report["status"] == "blocked_blueprint_audit"
    assert any("expected exactly 32" in error for error in report["errors"])
    assert any("task type counts" in error for error in report["errors"])


def test_audit_rejects_sealed_fields_and_paths():
    task = _task(1)
    task["gold_patch"] = "secret"
    task["base_files"] = {"hidden_tests/leak.py": "secret"}
    report = audit({"tasks": [task]}, expected_count=1, per_type=1, min_repositories=1)
    assert report["status"] == "blocked_blueprint_audit"
    assert any("sealed/evaluator fields" in error for error in report["errors"])
    assert any("sealed path" in error for error in report["errors"])
