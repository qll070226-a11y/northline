from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(path: Path) -> dict[str, object]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    statuses = Counter(str(row.get("status")) for row in rows)
    return {
        "purpose": "plumbing validation with sealed gold patches; not a model result",
        "raw_record_location": "sealed_external_storage",
        "raw_record_sha256": sha256(path),
        "episode_count": len(rows),
        "status_counts": dict(sorted(statuses.items())),
        "root_goal_satisfied_count": sum(bool(row.get("root_goal_satisfied")) for row in rows),
        "tests_passed_count": sum(bool(row.get("tests_passed")) for row in rows),
        "scope_violation_count": sum(bool(row.get("scope_violation")) for row in rows),
        "unsupported_completion_count": sum(bool(row.get("unsupported_completion")) for row in rows),
        "run_fingerprints": sorted({str(row.get("run_fingerprint")) for row in rows}),
        "contains_patch_data": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a non-sensitive summary of sealed validation episodes")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/controlled-pilot-episode-summary.json"))
    args = parser.parse_args()
    report = summarize(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
