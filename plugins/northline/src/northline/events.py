from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Event:
    event_type: str
    mission_id: str
    actor_id: str
    contract_id: str | None
    payload: dict[str, Any]
    timestamp: str


class EventLog:
    """Append-only JSONL log for reconstructing delegation trees and experiments."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[Event] = []

    def append(self, event_type: str, mission_id: str, actor_id: str, *, contract_id: str | None = None, payload: dict[str, Any] | None = None) -> Event:
        event = Event(event_type, mission_id, actor_id, contract_id, payload or {}, datetime.now(timezone.utc).isoformat())
        self.events.append(event)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        return event

    @classmethod
    def load(cls, path: Path) -> "EventLog":
        log = cls(path)
        if not path.exists():
            return log
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            log.events.append(Event(**data))
        return log
