from __future__ import annotations

import json
from pathlib import Path

from metrics import EpisodeMetrics, summarize, write_jsonl


def main() -> None:
    episodes = [
        EpisodeMetrics("synthetic-scope-001", "full_protocol", 0, True, True, False, False, False, False, False),
        EpisodeMetrics("synthetic-scope-001", "flat_multi_agent", 0, False, True, True, False, True, True, True),
    ]
    output = Path("results/smoke.jsonl")
    write_jsonl(output, episodes)
    Path("results/smoke_summary.json").write_text(json.dumps(summarize(episodes), indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
