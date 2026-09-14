from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

from scipy.stats import binom

DEFAULT_SCENARIOS = (
    {"name": "small", "discordance_rate": 0.25, "treatment_win_share": 0.65},
    {"name": "moderate", "discordance_rate": 0.30, "treatment_win_share": 0.75},
    {"name": "large", "discordance_rate": 0.40, "treatment_win_share": 0.75},
)


@lru_cache(maxsize=None)
def rejection_probability(discordant_pairs: int, treatment_win_share: float, alpha: float) -> float:
    """Conditional rejection probability for a two-sided exact McNemar test."""
    if discordant_pairs == 0:
        return 0.0
    cutoff = int(binom.ppf(alpha / 2, discordant_pairs, 0.5))
    while cutoff >= 0 and 2 * float(binom.cdf(cutoff, discordant_pairs, 0.5)) > alpha:
        cutoff -= 1
    if cutoff < 0:
        return 0.0
    lower = float(binom.cdf(cutoff, discordant_pairs, treatment_win_share))
    upper = float(binom.sf(discordant_pairs - cutoff - 1, discordant_pairs, treatment_win_share))
    return lower + upper


def exact_mcnemar_power(
    n_tasks: int,
    discordance_rate: float,
    treatment_win_share: float,
    *,
    alpha: float = 0.05,
) -> float:
    if n_tasks <= 0:
        raise ValueError("n_tasks must be positive")
    if not 0 <= discordance_rate <= 1:
        raise ValueError("discordance_rate must be between zero and one")
    if not 0 <= treatment_win_share <= 1:
        raise ValueError("treatment_win_share must be between zero and one")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")

    power = 0.0
    for discordant_pairs in range(n_tasks + 1):
        pair_probability = float(binom.pmf(discordant_pairs, n_tasks, discordance_rate))
        power += pair_probability * rejection_probability(discordant_pairs, treatment_win_share, alpha)
    return power


def minimum_tasks(
    discordance_rate: float,
    treatment_win_share: float,
    *,
    alpha: float,
    target_power: float = 0.80,
    maximum: int = 500,
) -> int | None:
    for n_tasks in range(2, maximum + 1):
        if exact_mcnemar_power(n_tasks, discordance_rate, treatment_win_share, alpha=alpha) >= target_power:
            return n_tasks
    return None


def build_report(
    sample_sizes: tuple[int, ...] = (24, 50, 100, 120),
    scenarios: tuple[dict[str, float | str], ...] = DEFAULT_SCENARIOS,
) -> dict[str, object]:
    alpha_levels = {"single_primary": 0.05, "seven_outcome_bonferroni_bound": 0.05 / 7}
    results = []
    for scenario in scenarios:
        discordance = float(scenario["discordance_rate"])
        win_share = float(scenario["treatment_win_share"])
        results.append({
            **scenario,
            "implied_paired_risk_difference": discordance * (2 * win_share - 1),
            "power": {
                label: {
                    str(size): exact_mcnemar_power(size, discordance, win_share, alpha=alpha)
                    for size in sample_sizes
                }
                for label, alpha in alpha_levels.items()
            },
            "minimum_tasks_for_80_percent_power": {
                label: minimum_tasks(discordance, win_share, alpha=alpha)
                for label, alpha in alpha_levels.items()
            },
        })
    return {
        "method": "unconditional exact power for the two-sided exact McNemar test",
        "inference_unit": "task",
        "interpretation": (
            "The number of discordant pairs is Binomial(n, q); conditional treatment wins are "
            "Binomial(m, theta). This is a planning sensitivity analysis, not observed evidence."
        ),
        "alpha_levels": alpha_levels,
        "sample_sizes": list(sample_sizes),
        "scenarios": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exact paired-binary power sensitivity analysis")
    parser.add_argument("--output", type=Path, default=Path("results/power-analysis.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_report(), indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
