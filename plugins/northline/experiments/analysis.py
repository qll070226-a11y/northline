from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from statsmodels.stats.contingency_tables import mcnemar

BOOLEAN_OUTCOMES = (
    "root_goal_satisfied", "tests_passed", "scope_violation", "stale_state_accepted",
    "unsupported_completion", "conflict_missed", "regression",
)
CONTINUOUS_OUTCOMES = ("token_cost", "latency_seconds", "manual_interventions")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row.get("analysis_eligible", row.get("status", "completed") == "completed")]


def paired_values(rows: list[dict[str, object]], baseline: str, treatment: str, outcome: str) -> tuple[np.ndarray, np.ndarray]:
    keyed: dict[tuple[str, int], dict[str, float]] = {}
    for row in rows:
        key = (str(row["task_id"]), int(row["seed"]))
        keyed.setdefault(key, {})[str(row["condition"])] = float(row[outcome])
    pairs = [(values[baseline], values[treatment]) for values in keyed.values() if baseline in values and treatment in values]
    if not pairs:
        raise ValueError(f"no paired observations for {baseline} and {treatment}")
    left, right = zip(*pairs)
    return np.asarray(left), np.asarray(right)


def task_mean_differences(rows: list[dict[str, object]], baseline: str, treatment: str, outcome: str) -> np.ndarray:
    grouped: dict[str, list[float]] = {}
    keyed: dict[tuple[str, int], dict[str, float]] = {}
    for row in rows:
        key = (str(row["task_id"]), int(row["seed"]))
        keyed.setdefault(key, {})[str(row["condition"])] = float(row[outcome])
    for (task_id, _), values in keyed.items():
        if baseline in values and treatment in values:
            grouped.setdefault(task_id, []).append(values[treatment] - values[baseline])
    if not grouped:
        raise ValueError(f"no task-level pairs for {baseline} and {treatment}")
    return np.asarray([np.mean(differences) for differences in grouped.values()])


def bootstrap_mean_ci(values: np.ndarray, *, seed: int = 20260912, samples: int = 10000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(samples, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def paired_permutation_pvalue(differences: np.ndarray, *, seed: int = 20260912, samples: int = 10000) -> float:
    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        return 1.0
    observed = abs(float(nonzero.mean()))
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(samples, len(nonzero)))
    permuted = np.abs((signs * nonzero).mean(axis=1))
    return float((np.sum(permuted >= observed) + 1) / (samples + 1))


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = np.empty(len(pvalues), dtype=float)
    running = 0.0
    count = len(pvalues)
    for rank, index in enumerate(order):
        running = max(running, (count - rank) * pvalues[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def binary_comparison(rows: list[dict[str, object]], baseline: str, treatment: str, outcome: str) -> dict[str, object]:
    left, right = paired_values(rows, baseline, treatment, outcome)
    task_differences = task_mean_differences(rows, baseline, treatment, outcome)
    discordant_01 = int(np.sum((left == 0) & (right == 1)))
    discordant_10 = int(np.sum((left == 1) & (right == 0)))
    table = [[int(np.sum((left == 0) & (right == 0))), discordant_01], [discordant_10, int(np.sum((left == 1) & (right == 1)))]]
    mcnemar_p = float(mcnemar(table, exact=True).pvalue) if discordant_01 + discordant_10 else 1.0
    ci_low, ci_high = bootstrap_mean_ci(task_differences)
    return {
        "outcome": outcome, "n_tasks": len(task_differences), "n_episode_pairs": len(left), "baseline_rate": float(left.mean()),
        "treatment_rate": float(right.mean()), "paired_risk_difference": float(task_differences.mean()),
        "risk_difference_cluster_ci95": [ci_low, ci_high], "task_cluster_permutation_p": paired_permutation_pvalue(task_differences),
        "mcnemar_exact_p": mcnemar_p,
        "discordant": {"baseline_0_treatment_1": discordant_01, "baseline_1_treatment_0": discordant_10},
    }


def continuous_comparison(rows: list[dict[str, object]], baseline: str, treatment: str, outcome: str) -> dict[str, object]:
    left, right = paired_values(rows, baseline, treatment, outcome)
    task_differences = task_mean_differences(rows, baseline, treatment, outcome)
    ci_low, ci_high = bootstrap_mean_ci(task_differences)
    return {
        "outcome": outcome, "n_tasks": len(task_differences), "n_episode_pairs": len(left),
        "baseline_mean": float(left.mean()), "treatment_mean": float(right.mean()),
        "paired_mean_difference": float(task_differences.mean()), "difference_cluster_ci95": [ci_low, ci_high],
        "task_cluster_permutation_p": paired_permutation_pvalue(task_differences),
    }


def analyze(rows: list[dict[str, object]], baseline: str, treatment: str) -> dict[str, object]:
    comparisons = [binary_comparison(rows, baseline, treatment, outcome) for outcome in BOOLEAN_OUTCOMES]
    adjusted = holm_adjust([float(item["task_cluster_permutation_p"]) for item in comparisons])
    for item, value in zip(comparisons, adjusted):
        item["holm_adjusted_p"] = value
    continuous = [continuous_comparison(rows, baseline, treatment, outcome) for outcome in CONTINUOUS_OUTCOMES]
    return {"baseline": baseline, "treatment": treatment, "inference_unit": "task", "binary_comparisons": comparisons, "continuous_comparisons": continuous}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/analysis.json"))
    args = parser.parse_args()
    result = analyze(read_jsonl(args.input), args.baseline, args.treatment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
