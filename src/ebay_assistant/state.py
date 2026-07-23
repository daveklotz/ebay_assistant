"""Local record of which orders have already been messaged (dedup)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import parse_datetime, to_iso

STATE_FILE = "state.json"
PRUNE_AFTER_DAYS = 90


class StateError(Exception):
    pass


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {"version": 1, "messaged_orders": {}}

    @classmethod
    def load(cls, config_dir: Path) -> "State":
        state = cls(config_dir / STATE_FILE)
        try:
            raw = json.loads(state.path.read_text())
        except FileNotFoundError:
            return state
        except ValueError as exc:
            raise StateError(
                f"{state.path} is corrupt ({exc}) — fix or delete it "
                "(deleting forgets which buyers were already messaged)"
            ) from None
        if isinstance(raw, dict) and isinstance(raw.get("messaged_orders"), dict):
            state.data = raw
        state._prune()
        return state

    def status(self, order_id: str) -> str | None:
        entry = self.data["messaged_orders"].get(order_id)
        return entry.get("status") if entry else None

    def is_handled(self, order_id: str) -> bool:
        return order_id in self.data["messaged_orders"]

    def mark_sent(self, order_ids: list[str], message_id: str) -> None:
        self._mark(order_ids, "sent", message_id)

    def mark_never(self, order_ids: list[str]) -> None:
        self._mark(order_ids, "never", None)

    def _mark(self, order_ids: list[str], status: str, message_id: str | None) -> None:
        # Deliberately stores no buyer data — only the seller's own order IDs —
        # so the "Not persisting eBay data" exemption stays accurate.
        now = to_iso(datetime.now(timezone.utc))
        for order_id in order_ids:
            entry = {"messaged_at": now, "status": status}
            if message_id:
                entry["message_id"] = message_id
            self.data["messaged_orders"][order_id] = entry
        self.save()

    def save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2) + "\n")
        os.replace(tmp, self.path)

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=PRUNE_AFTER_DAYS)
        entries = self.data["messaged_orders"]
        for order_id in list(entries):
            try:
                handled_at = parse_datetime(entries[order_id].get("messaged_at"))
            except (ValueError, AttributeError):
                continue
            if handled_at and handled_at < cutoff:
                del entries[order_id]
