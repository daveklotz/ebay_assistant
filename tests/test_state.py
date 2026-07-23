from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ebay_assistant.state import State, StateError


def test_round_trip(tmp_path):
    state = State.load(tmp_path)
    assert not state.is_handled("1-1")
    state.mark_sent(["1-1", "1-2"], "buyer", "msg123")
    reloaded = State.load(tmp_path)
    assert reloaded.is_handled("1-1")
    assert reloaded.is_handled("1-2")
    assert reloaded.status("1-1") == "sent"
    assert reloaded.data["messaged_orders"]["1-1"]["message_id"] == "msg123"
    assert not (tmp_path / "state.json.tmp").exists()


def test_mark_never(tmp_path):
    state = State.load(tmp_path)
    state.mark_never(["2-1"], "buyer")
    assert State.load(tmp_path).status("2-1") == "never"


def test_prune_old_entries(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "messaged_orders": {
                    "old-1": {"messaged_at": old, "buyer": "a", "status": "sent"},
                    "new-1": {"messaged_at": fresh, "buyer": "b", "status": "sent"},
                },
            }
        )
    )
    state = State.load(tmp_path)
    assert not state.is_handled("old-1")
    assert state.is_handled("new-1")


def test_corrupt_state_raises(tmp_path):
    (tmp_path / "state.json").write_text("{not json")
    with pytest.raises(StateError):
        State.load(tmp_path)
