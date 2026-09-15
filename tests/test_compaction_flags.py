"""Tests for the compaction flag infrastructure and dynamic projection.

Stored messages are TRUTH: compaction only FLAGS them (``pruned``
metadata); ``get_context()`` builds the submitted view dynamically —
skipping dropped messages, stubbing flagged tool bodies, and handling
thinking at projection level. Persistence round-trips the flags so the
projection survives a resume.
"""

import json
from pathlib import Path
from typing import Any

from yoker.context import BaseContextManager, Persisted


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
  m: dict[str, Any] = {"role": role, "content": content}
  m.update(extra)
  return m


def _stub_flag(stage: str = "prune_tool_results", chars: int | None = None) -> dict[str, Any]:
  flag: dict[str, Any] = {"kind": "stub", "stage": stage, "at": "2026-09-14T00:00:00"}
  if chars is not None:
    flag["chars"] = chars
  return flag


def _dropped_flag(stage: str = "cutoff") -> dict[str, Any]:
  return {"kind": "dropped", "stage": stage, "at": "2026-09-14T00:00:00"}


class TestStubProjection:
  """Flagged tool results become stubs in the view; bodies stay stored."""

  def test_stub_replaces_body_in_view_only(self) -> None:
    """A kind=stub tool result shows the stub; the stored body is intact."""
    cm = BaseContextManager()
    tool = _msg("tool", "x" * 10_000, name="read", tool_id="call_1", success=True)
    tool["pruned"] = _stub_flag(chars=10_000)
    cm._messages = [_msg("system", "sys"), tool]

    view = cm.get_context()
    assert view[1]["content"].startswith("[elided: read")
    assert "10,000 chars pruned" in view[1]["content"]
    assert "prune_tool_results" in view[1]["content"]
    # Stored body untouched.
    assert cm._messages[1]["content"] == "x" * 10_000

  def test_stub_keeps_pairing_fields(self) -> None:
    """Role/name/tool_id are unchanged so tool-call pairing stays intact."""
    cm = BaseContextManager()
    tool = _msg("tool", "body", name="read", tool_id="call_1", success=True)
    tool["pruned"] = _stub_flag(chars=4)
    cm._messages = [tool]

    view = cm.get_context()
    assert view[0]["role"] == "tool"
    assert view[0]["name"] == "read"
    assert view[0]["tool_id"] == "call_1"
    assert view[0]["success"] is True

  def test_stub_text_is_deterministic(self) -> None:
    """Same stored state → byte-identical stub text (prefix-cache stability)."""
    cm = BaseContextManager()
    tool = _msg("tool", "body", name="grep", tool_id="t1")
    tool["pruned"] = {
      "kind": "stub",
      "stage": "prune_tool_results",
      "at": "2026-09-14T00:00:00",
      "chars": 14203,
      "hint": "src/yoker/core/_processing.py",
    }
    cm._messages = [tool]

    first = cm.get_context()[0]["content"]
    second = cm.get_context()[0]["content"]
    assert first == second
    assert "grep src/yoker/core/_processing.py" in first
    assert "14,203 chars" in first
    assert "prune_tool_results" in first

  def test_view_never_leaks_pruned_key(self) -> None:
    """The framework-internal flag is absent from every view message."""
    cm = BaseContextManager()
    tool = _msg("tool", "body", name="read", tool_id="t1")
    tool["pruned"] = _stub_flag(chars=4)
    dropped = _msg("assistant", "old")
    dropped["pruned"] = _dropped_flag()
    cm._messages = [tool, dropped]

    view = cm.get_context()
    assert not any("pruned" in m for m in view)


class TestDroppedProjection:
  """Flagged messages are excluded from the view but kept in the store."""

  def test_dropped_excluded_from_view_kept_in_store(self) -> None:
    """kind=dropped messages vanish from the view, not from the store."""
    cm = BaseContextManager()
    dropped = _msg("assistant", "old response")
    dropped["pruned"] = _dropped_flag()
    cm._messages = [_msg("system", "sys"), dropped, _msg("user", "new")]

    view = cm.get_context()
    contents = [m["content"] for m in view]
    assert "old response" not in contents
    # Stored truth keeps it, and get_messages (stored reality) too.
    assert any(m["content"] == "old response" for m in cm.get_stored_messages())
    assert any(m["content"] == "old response" for m in cm.get_messages())

  def test_projection_is_deterministic(self) -> None:
    """Same stored state produces a byte-identical view on every call."""
    cm = BaseContextManager()
    stubbed = _msg("tool", "x" * 5000, name="read", tool_id="t1")
    stubbed["pruned"] = _stub_flag(chars=5000)
    dropped = _msg("assistant", "old")
    dropped["pruned"] = _dropped_flag()
    dropped2 = _msg("assistant", "older", thinking="deep thought")
    dropped2["pruned"] = _dropped_flag()
    cm._messages = [
      _msg("system", "sys"),
      stubbed,
      dropped,
      dropped2,
      _msg("user", "live"),
    ]

    first = cm.get_context()
    second = cm.get_context()
    assert first == second
    assert len(first) == 3  # sys, stubbed tool, live user


class TestThinkingProjection:
  """Thinking handling moved to the projection (stored=truth)."""

  def test_strip_in_view_drops_thinking_but_keeps_stored(self) -> None:
    """strip_thinking_in_view=True: view has no thinking, store keeps it."""
    cm = BaseContextManager()
    cm.strip_thinking_in_view = True
    cm._messages = [
      _msg("assistant", "resp", thinking="secret"),
      _msg("user", "hi"),
    ]

    view = cm.get_context()
    assert all("thinking" not in m for m in view)
    assert cm._messages[0]["thinking"] == "secret"

  def test_supporting_backend_keeps_unflagged_thinking(self) -> None:
    """strip_thinking_in_view=False: unflagged thinking survives the view."""
    cm = BaseContextManager()
    cm.strip_thinking_in_view = False
    cm._messages = [
      _msg("assistant", "resp", thinking="secret"),
    ]

    view = cm.get_context()
    assert view[0]["thinking"] == "secret"

  def test_flagged_thinking_dropped_even_for_supporting_backend(self) -> None:
    """Flagged thinking never reaches the view, regardless of the switch."""
    cm = BaseContextManager()
    cm.strip_thinking_in_view = False
    flagged = _msg("assistant", "old", thinking="pruned thought")
    flagged["pruned"] = _dropped_flag()
    stubbed = _msg("assistant", "older", thinking="also gone")
    stubbed["pruned"] = _stub_flag(chars=6)
    cm._messages = [flagged, stubbed, _msg("assistant", "new", thinking="kept")]

    view = cm.get_context()
    # The dropped message is excluded entirely; the stubbed one stays
    # (sans thinking). Only "new" keeps its thinking.
    assert [m["content"] for m in view] == ["older", "new"]
    assert view[1]["thinking"] == "kept"
    assert all("thinking" not in m for m in view[:1])


class TestTruncateFlags:
  """truncate_oldest_non_system flags instead of removing."""

  def test_truncate_flags_without_removing(self) -> None:
    """Stored count is unchanged; the view shrinks by the flagged count."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=1)
    assert dropped == 1
    # Stored truth unchanged.
    assert len(cm._messages) == 5
    # The view shrank by exactly the flagged message.
    assert len(cm.get_context()) == 4
    assert cm._messages[2]["pruned"]["kind"] == "dropped"
    assert cm._messages[2]["pruned"]["stage"] == "cutoff"

  def test_first_user_protection_intact_in_flag_mode(self) -> None:
    """The first real user turn is never flagged."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(drop_count=10)
    contents = [m["content"] for m in cm.get_context()]
    assert "first turn" in contents
    assert "sys" in contents
    # Only the first plain assistant was droppable: the users are
    # scaffolding + first-user/last-user windows, resp2 is the last
    # plain assistant.
    assert "resp1" not in contents
    assert len(contents) == 4

  def test_pairing_intact_in_view(self) -> None:
    """Flagged units keep tool-call pairing: assistant+results hidden together."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "call it", tool_calls=[{"id": "call_1", "name": "read"}]),
      _msg("tool", "result", name="read", tool_id="call_1"),
      _msg("assistant", "resp2"),
      _msg("user", "second turn"),
      _msg("assistant", "call again", tool_calls=[{"id": "call_2", "name": "list"}]),
      _msg("tool", "result 2", name="list", tool_id="call_2"),
    ]
    cm.truncate_oldest_non_system(drop_count=1)
    view = cm.get_context()
    # The oldest atomic unit (assistant with tool_calls + its result) left
    # the view together — no orphan tool result, no orphan tool_calls. The
    # last tool-call unit is protected, so its result is still in the view.
    tool_ids = [m["tool_id"] for m in view if m.get("role") == "tool"]
    assert tool_ids == ["call_2"]
    assert not any("call it" == m.get("content") for m in view)
    # Stored truth keeps all eight messages.
    assert len(cm._messages) == 8

  def test_repeated_truncate_skips_already_flagged_units(self) -> None:
    """A second call flags the NEXT unit — flagged ones are not re-counted."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
      _msg("user", "third turn"),
      _msg("assistant", "resp3"),
      _msg("user", "fourth turn"),
      _msg("assistant", "resp4"),
    ]
    assert cm.truncate_oldest_non_system(drop_count=1) == 1
    assert cm.truncate_oldest_non_system(drop_count=1) == 1
    flagged = [m["content"] for m in cm._messages if "pruned" in m]
    # Oldest-first: resp1, then resp2. "second turn" is the FIRST real user
    # (first-user window); the last-user/assistant windows keep resp3/resp4
    # and third/fourth turns out of reach.
    assert flagged == ["resp1", "resp2"]


class TestPersistedFlagRoundTrip:
  """Flags survive save/load; old files without flags load unchanged."""

  def test_flags_round_trip_through_save_load(self, tmp_path: Path) -> None:
    """A stubbed tool result and a dropped message survive the rewrite."""
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="flags-rt")
    cm._wrapped._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "call it", tool_calls=[{"id": "c1", "name": "read"}]),
      {**_msg("tool", "big body", name="read", tool_id="c1"), "pruned": _stub_flag(chars=8)},
      {**_msg("assistant", "old"), "pruned": _dropped_flag()},
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.save()

    reloaded = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="flags-rt")
    assert reloaded.load() is True

    stored = reloaded.get_stored_messages()
    tool = next(m for m in stored if m.get("role") == "tool")
    assert tool["content"] == "big body"  # original body persisted
    assert tool["pruned"]["kind"] == "stub"
    dropped = next(m for m in stored if m["content"] == "old")
    assert dropped["pruned"]["kind"] == "dropped"

    # The reloaded projection hides the flagged message and stubs the tool.
    view = reloaded.get_context()
    contents = [m["content"] for m in view]
    assert "old" not in contents
    assert "[elided: read" in next(m for m in view if m.get("role") == "tool")["content"]
    cm.delete()

  def test_old_format_without_flags_loads_unchanged(self, tmp_path: Path) -> None:
    """A legacy JSONL (no pruned keys anywhere) replays exactly as before."""
    file_path = tmp_path / "legacy-0001.jsonl"
    records = [
      {
        "type": "session_start",
        "timestamp": "2026-09-01T00:00:00",
        "data": {"session_id": "legacy"},
      },
      {
        "type": "message",
        "timestamp": "2026-09-01T00:00:01",
        "data": {"role": "user", "content": "hi"},
      },
      {
        "type": "tool_result",
        "timestamp": "2026-09-01T00:00:02",
        "data": {"tool_name": "read", "tool_id": "t1", "result": "body", "success": True},
      },
      {
        "type": "tool_call_message",
        "timestamp": "2026-09-01T00:00:03",
        "data": {"tool_calls": [{"id": "t1", "name": "read"}], "thinking": None, "content": ""},
      },
    ]
    file_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="legacy-0001")
    assert cm.load() is True
    stored = cm.get_stored_messages()
    assert [m["role"] for m in stored] == ["user", "tool", "assistant"]
    assert not any("pruned" in m for m in stored)
    cm.delete()

  def test_thinking_survives_persistence(self, tmp_path: Path) -> None:
    """Stored thinking is written to and restored from JSONL (truth, not view)."""
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="think-rt")
    cm._wrapped._messages = [
      _msg("assistant", "resp", thinking="deep thought"),
    ]
    cm.save()

    reloaded = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="think-rt")
    assert reloaded.load() is True
    assert reloaded.get_stored_messages()[0]["thinking"] == "deep thought"
    # The default projection still strips it from the view.
    assert all("thinking" not in m for m in reloaded.get_context())
    cm.delete()
