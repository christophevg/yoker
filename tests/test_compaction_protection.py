"""Tests for the cutoff protection windows and the force-stub compaction stage.

The cutoff stage drops oldest-first, but a protection set is never flagged:
framework scaffolding (system + leading user run) is always safe, and four
windows (first user, last user, last plain assistant, last tool-call unit)
protect recent context. ``force_stub_tool_results`` is the age-blind,
last content-preserving pass before cutoff. Compaction runs are recorded
for later persistence (chunk C).
"""

from typing import Any

from yoker.context import BaseContextManager
from yoker.context.manager import _pruned_metadata


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
  m: dict[str, Any] = {"role": role, "content": content}
  m.update(extra)
  return m


def _tool_call_msg(content: str = "call it") -> dict[str, Any]:
  return {
    "role": "assistant",
    "content": content,
    "tool_calls": [{"id": "call_1", "name": "read", "arguments": {}}],
  }


def _tool_result_msg(content: str = "result") -> dict[str, Any]:
  return {
    "role": "tool",
    "name": "read",
    "tool_id": "call_1",
    "content": content,
    "success": True,
  }


class TestForceStubToolResults:
  """force_stub_tool_results stubs big tool results regardless of age."""

  def test_flags_big_result_even_at_age_zero(self) -> None:
    """A large result immediately followed by its turn is still stubbed."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg("x" * 5000),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
    ]
    flagged = cm.force_stub_tool_results(min_chars=4096)
    assert flagged == 1
    flag = cm._messages[3]["pruned"]
    assert flag["kind"] == "stub"
    assert flag["stage"] == "force_stub_tool_results"
    assert flag["chars"] == 5000
    # The view renders the stub; pairing fields stay intact.
    view = cm.get_context()
    tool_view = next(m for m in view if m.get("role") == "tool")
    assert tool_view["content"].startswith("[elided: read")
    assert "force_stub_tool_results" in tool_view["content"]

  def test_skips_small_results(self) -> None:
    """Bodies at or under min_chars are never flagged."""
    cm = BaseContextManager()
    cm._messages = [_tool_result_msg("x" * 4096)]
    assert cm.force_stub_tool_results(min_chars=4096) == 0

  def test_skips_already_flagged(self) -> None:
    """An already-flagged (stubbed) result is not re-flagged by the pass."""
    cm = BaseContextManager()
    result = _tool_result_msg("x" * 5000)
    result["pruned"] = {"kind": "stub", "stage": "prune_tool_results", "at": "t"}
    cm._messages = [result]
    assert cm.force_stub_tool_results(min_chars=100) == 0
    assert cm._messages[0]["pruned"]["stage"] == "prune_tool_results"


class TestProtectionWindows:
  """The four cutoff protection windows keep their messages non-droppable."""

  def test_last_user_message_never_flagged_even_when_target_unreachable(self) -> None:
    """Draining the store never flags the last user message."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "middle turn"),
      _msg("assistant", "resp2"),
      _msg("user", "last turn"),
      _msg("assistant", "resp3"),
    ]
    # Massive drop_count: everything droppable gets flagged, yet the
    # last user message stays.
    dropped = cm.truncate_oldest_non_system(drop_count=1000)
    assert dropped > 0
    contents = [m["content"] for m in cm.get_context()]
    # "first turn" and "middle turn" sit inside the leading user run, so
    # they are scaffolding here — the last-user window protects "last turn".
    assert "last turn" in contents
    assert "scaffold" in contents
    assert "first turn" in contents
    assert "middle turn" in contents
    assert "resp1" not in contents
    assert "resp2" not in contents

  def test_last_plain_assistant_protected(self) -> None:
    """The newest plain assistant message survives; older ones are dropped."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
      _msg("user", "third turn"),
      _msg("assistant", "resp3"),
      _msg("user", "fourth turn"),
    ]
    cm.truncate_oldest_non_system(drop_count=1000)
    contents = [m["content"] for m in cm.get_context()]
    assert "resp3" in contents
    assert "fourth turn" in contents
    assert "resp2" not in contents
    assert "resp1" not in contents

  def test_last_tool_call_unit_protected_with_results(self) -> None:
    """The newest tool-call unit — frame AND all its results — survives."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg(),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
      {**_tool_call_msg(), "tool_calls": [{"id": "call_2", "name": "list"}]},
      {**_tool_result_msg(), "tool_id": "call_2"},
    ]
    cm.truncate_oldest_non_system(drop_count=1000)
    view = cm.get_context()
    # The SECOND (last) unit survives completely; the first is gone.
    tool_ids = [m["tool_id"] for m in view if m.get("role") == "tool"]
    assert tool_ids == ["call_2"]
    frames = [m for m in view if "tool_calls" in m]
    assert len(frames) == 1

  def test_first_user_window_protects_post_scaffolding_turns(self) -> None:
    """protect_first_user=2 keeps the first two real user turns."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first real"),
      _msg("assistant", "resp1"),
      _msg("user", "second real"),
      _msg("assistant", "resp2"),
      _msg("user", "third real"),
      _msg("assistant", "resp3"),
    ]
    cm.truncate_oldest_non_system(protect_first_user=2, drop_count=1000)
    contents = [m["content"] for m in cm.get_context()]
    assert "first real" in contents
    assert "second real" in contents
    assert "third real" in contents  # also protected: last-user window
    assert "resp1" not in contents
    assert "resp2" not in contents
    assert "scaffold" in contents  # scaffolding always protected

  def test_scaffolding_always_protected(self) -> None:
    """System + leading user run survive even with all windows at 0."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys1"),
      _msg("system", "sys2"),
      _msg("user", "discovery block"),
      _msg("user", "more scaffolding"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(
      protect_first_user=0,
      protect_last_user=0,
      protect_last_assistant=0,
      protect_last_tool_calls=0,
      drop_count=1000,
    )
    contents = [m["content"] for m in cm.get_context()]
    assert "sys1" in contents
    assert "sys2" in contents
    assert "discovery block" in contents
    assert "more scaffolding" in contents
    assert "resp1" not in contents


class TestPairingClosure:
  """Protection and dropping never split a tool-call unit."""

  def test_dropped_unit_leaves_no_orphans(self) -> None:
    """After cutoff, the view has no frame without its results (or vice versa)."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg(),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
      {**_tool_call_msg(), "tool_calls": [{"id": "call_2", "name": "list"}]},
      {**_tool_result_msg(), "tool_id": "call_2"},
    ]
    cm.truncate_oldest_non_system(drop_count=1000)
    view = cm.get_context()
    frames = [m for m in view if "tool_calls" in m]
    results = [m for m in view if m.get("role") == "tool"]
    # The old unit is dropped ENTIRELY (frame + result together); the last
    # unit survives ENTIRELY — no orphans on either side.
    assert [m["tool_id"] for m in results] == ["call_2"]
    assert len(frames) == 1

  def test_all_windows_zero_drops_whole_units(self) -> None:
    """With every window disabled, whole units vanish — still no orphans."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg(),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
    ]
    cm.truncate_oldest_non_system(
      protect_first_user=0,
      protect_last_user=0,
      protect_last_assistant=0,
      protect_last_tool_calls=0,
      drop_count=1000,
    )
    view = cm.get_context()
    assert not [m for m in view if "tool_calls" in m]
    assert not [m for m in view if m.get("role") == "tool"]


class TestProtectedContext:
  """protected_context returns exactly the protected set, in store order."""

  def test_returns_scaffolding_plus_windows(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first real"),
      _msg("assistant", "resp1"),
      _msg("user", "second real"),
      _msg("assistant", "resp2"),
      _msg("user", "third real"),
      _msg("assistant", "resp3"),
    ]
    protected = cm.protected_context()
    contents = [m["content"] for m in protected]
    # Scaffolding (sys + leading user run) + first-user window + last user
    # + last plain assistant. The leading user run absorbs the first real
    # turn here, so the first-user window picks the NEXT user message.
    assert contents == ["sys", "scaffold", "first real", "second real", "third real", "resp3"]
    # Copies, not store references.
    protected[0]["content"] = "mutated"
    assert cm._messages[0]["content"] == "sys"

  def test_matches_truncate_protection(self) -> None:
    """What protected_context returns is exactly what cutoff never flags."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first"),
      _tool_call_msg(),
      _tool_result_msg(),
      _msg("assistant", "resp1"),
      _msg("user", "second"),
      _msg("assistant", "resp2"),
    ]
    protected_contents = [m["content"] for m in cm.protected_context()]
    cm.truncate_oldest_non_system(drop_count=1000)
    surviving = [m["content"] for m in cm.get_context()]
    assert set(protected_contents) == set(surviving)


class TestCompactionRuns:
  """record_compaction stores run reports; compaction_runs returns copies."""

  def test_round_trip(self) -> None:
    cm = BaseContextManager()
    assert cm.compaction_runs == []
    run = {"stages": [{"name": "cutoff", "messages": 3, "tokens": 1200}]}
    cm.record_compaction(run)
    cm.record_compaction({"stages": []})
    runs = cm.compaction_runs
    assert runs == [run, {"stages": []}]
    # Copies: mutating the returned list/dicts does not touch the store.
    runs[0]["stages"].append({"name": "injected"})
    assert cm.compaction_runs[0]["stages"] == [{"name": "cutoff", "messages": 3, "tokens": 1200}]


class TestPrunedMetadataRunField:
  """_pruned_metadata stores the optional ``run`` key in the flag dict."""

  def test_run_field_present_when_provided(self) -> None:
    flag = _pruned_metadata("dropped", "cutoff", run="run-42")
    assert flag["run"] == "run-42"
    assert flag["kind"] == "dropped"
    assert flag["stage"] == "cutoff"
    assert "at" in flag

  def test_run_field_absent_when_omitted(self) -> None:
    flag = _pruned_metadata("dropped", "cutoff")
    assert "run" not in flag
