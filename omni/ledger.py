"""Day-scoped JSONL evidence ledger.

Every run appends one JSON object per line. Records never contain credentials.
The ledger is the source of the paper-trading log required by the Agentic
Trading track, and it is designed to be machine-audited.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Ledger:
    def __init__(self, log_dir: Path, run_id: str | None = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        self.path = self.log_dir / f"paper-log-{stamp}.jsonl"

    def record(self, kind: str, payload: dict) -> dict:
        entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "kind": kind,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")
        return entry

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def counts_by_kind(self) -> dict:
        counts: dict = {}
        for entry in self.read_all():
            counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
        return counts

    @staticmethod
    def all_logs(log_dir: Path) -> list[Path]:
        return sorted(Path(log_dir).glob("paper-log-*.jsonl"))
