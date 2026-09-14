import tempfile
import unittest
from pathlib import Path

from northline.events import EventLog


class EventLogTests(unittest.TestCase):
    def test_append_only_log_can_be_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            log = EventLog(path)
            log.append("delegated", "m1", "root", contract_id="c1", payload={"agent_id": "worker_001"})
            log.append("state_transition", "m1", "runtime", contract_id="c1", payload={"status": "claimed"})
            replayed = EventLog.load(path)
            self.assertEqual([event.event_type for event in replayed.events], ["delegated", "state_transition"])
            self.assertEqual(replayed.events[0].payload["agent_id"], "worker_001")
