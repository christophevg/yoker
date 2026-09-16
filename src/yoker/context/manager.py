"""Base context manager implementation.

Provides BaseContextManager, the in-memory base for conversation history.
Subclasses (SimpleContextManager) can override setup_initial_context to
add richer initial context. Wrappers (ContextManagerWrapper, Persisted)
forward to a wrapped instance instead.
"""

from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from yoker.context.interface import ContextStatistics

if TYPE_CHECKING:
  from yoker.core import Agent

logger = get_logger(__name__)


class BaseContextManager:
  """In-memory base context manager.

  Stores messages in an internal list. The list surface (UserList, append,
  data, __getitem__, __len__, __iter__) is removed — callers use
  get_messages() / get_context() / the adder methods.
  """

  def __init__(self, initial: list[dict[str, Any]] | None = None) -> None:
    """Initialize the context manager.

    Args:
      initial: Optional initial list of context items.
    """
    self._agent: Agent | None = None
    self._messages: list[dict[str, Any]] = list(initial) if initial else []
    self._compaction_runs: list[dict[str, Any]] = []
    # Projection-level thinking strip (see get_context). Wired by the
    # Agent from the backend's supports_context_management; True by
    # default so plain/stub managers behave like today's always-on strip.
    self.strip_thinking_in_view: bool = True

  @property
  def agent(self) -> "Agent | None":
    return self._agent

  @agent.setter
  def agent(self, new_agent: "Agent") -> None:
    self._agent = new_agent
    self.clear()
    self.setup_initial_context()
    self.add_skill_discovery_block()

  def setup_initial_context(self) -> None:
    """Add the system prompt (base behavior)."""
    if self._agent:
      self.add_message("system", self._agent.definition.system_prompt)

  def add_skill_discovery_block(self) -> None:
    """Add skill discovery user message if enabled and skills exist."""
    if not self._agent:
      return
    if len(self._agent.skills) > 0 and self._agent.config.skills.discovery:
      from yoker.skills import format_discovery_block

      skill_list = self._agent.skills.skills
      self.add_message("user", format_discovery_block(skill_list))
      logger.info("skill_discovery_added", skill_count=len(skill_list))

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    """Add a message to the context.

    Args:
      role: Message role ("user", "assistant", "system").
      content: Message content.
      metadata: Optional metadata (e.g., images, files).
      thinking: Optional thinking/reasoning content (for assistant messages).
    """
    if not content:
      return
    message: dict[str, Any] = {
      "role": role,
      "content": content,
      # Framework-internal append timestamp. Never submitted to the
      # backend (stripped by the projection) — persistence uses it as
      # the record's true append time across bulk rewrites.
      "_appended_at": datetime.now().isoformat(),
    }
    if metadata:
      message["metadata"] = metadata
    if thinking:
      message["thinking"] = thinking
    self._messages.append(message)

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
    images: list[str] | None = None,
  ) -> None:
    """Add a tool execution result to the context.

    ``images`` holds image file paths (references, not base64) for the
    model to see; the ollama backend serializes them at submission time.
    """
    message = {
      "role": "tool",
      "name": tool_name,
      "tool_id": tool_id,
      "content": result,
      "success": success,
      # Framework-internal append timestamp (see add_message).
      "_appended_at": datetime.now().isoformat(),
    }
    if images:
      message["images"] = images
    self._messages.append(message)

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
    content: str = "",
  ) -> None:
    """Add an assistant message with tool calls to the context.

    This must be called BEFORE add_tool_result() for each tool call.

    Args:
      tool_calls: List of tool call dictionaries with 'name' and 'arguments'.
      thinking: Optional thinking/reasoning content from the assistant.
      content: Optional assistant narration text produced alongside the
        tool calls (when the LLM emits both text and tool calls in one
        response). Stored so the LLM can see its own prior reasoning on
        subsequent iterations.
    """
    assistant_msg: dict[str, Any] = {
      "role": "assistant",
      "tool_calls": tool_calls,
      "content": content,
      # Framework-internal append timestamp (see add_message).
      "_appended_at": datetime.now().isoformat(),
    }
    if thinking:
      assistant_msg["thinking"] = thinking
    self._messages.append(assistant_msg)

  def get_context(self) -> list[dict[str, Any]]:
    """Get the full context for backend submission — the dynamic projection.

    Stored messages are TRUTH and are never body-mutated or removed;
    compaction only FLAGS them (``pruned`` metadata). This method builds
    a deterministic view over the stored list — same stored state must
    produce a byte-identical view (prefix-cache stability):

      1. messages flagged ``pruned.kind == "dropped"`` are excluded;
      2. tool messages flagged ``pruned.kind == "stub"`` keep role/name/
         tool_id (pairing intact) but their body becomes a deterministic
         stub built from the flag metadata;
      3. ``thinking`` keys are dropped for ALL messages flagged as pruned,
         for messages flagged ``pruned.kind == "thinking"`` (prune_thinking
         stage), and for every message when ``strip_thinking_in_view`` is
         set (backends without provider-side context management) — stored
         thinking itself is retained, so persistence keeps the history;
      4. image refs follow the existing send-once contract
         (:func:`_strip_stale_images`), unchanged.
    """
    return _strip_stale_images(self._project_view(self._messages))

  def _project_view(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Render stored items exactly as :meth:`get_context` projects them.

    The per-item projection shared by :meth:`get_context` (the whole
    store) and :meth:`protected_view` (the cutoff-protected subset), so
    the two can never diverge:

      1. messages flagged ``pruned.kind == "dropped"`` are excluded;
      2. tool messages flagged ``pruned.kind == "stub"`` keep role/name/
         tool_id (pairing intact) but their body becomes a deterministic
         stub built from the flag metadata;
      3. ``thinking`` keys are dropped for ALL messages flagged as pruned,
         for messages flagged ``pruned.kind == "thinking"`` (prune_thinking
         stage), and for every message when ``strip_thinking_in_view`` is
         set (backends without provider-side context management) — stored
         thinking itself is retained, so persistence keeps the history;
      4. the framework-internal ``pruned`` flag never leaks into the
         backend payload;
      5. the framework-internal ``_appended_at`` append timestamp never
         leaks into the backend payload either (persistence metadata —
         see :func:`_strip_pruned_metadata`, which strips both keys).

    The ``images`` send-once contract (:func:`_strip_stale_images`) is
    applied by the callers over their own item list.
    """
    view: list[dict[str, Any]] = []
    for item in items:
      pruned = item.get("pruned")
      if isinstance(pruned, dict) and pruned.get("kind") == "dropped":
        continue
      if isinstance(pruned, dict) and pruned.get("kind") == "stub" and item.get("role") == "tool":
        item = {**item, "content": _prune_stub_text(item)}
      view.append(item)

    # Flagged thinking must go for every backend: the flag says the
    # history was pruned, so no view may still submit it. Backends
    # without provider-side context management additionally lose ALL
    # thinking in the view (stored thinking is retained).
    view = (
      _strip_flagged_thinking(view)
      if not self.strip_thinking_in_view
      else _strip_thinking_keys(view)
    )
    view = _strip_kind_thinking(view)
    # The framework-internal flag never leaks into the backend payload —
    # strip it only after the thinking passes above consumed it.
    return _strip_pruned_metadata(view)

  def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages (excludes tool results).

    Returns:
      List of message dictionaries.
    """
    return [item for item in self._messages if item.get("role") != "tool"]

  def get_stored_messages(self) -> list[dict[str, Any]]:
    """Get the stored messages — the TRUTH the projection views.

    Includes tool results and everything the projection might hide or
    stub out: this is the list persistence must save (flags, thinking and
    original bodies survive compaction) and the only read that reflects
    physical reality. Callers wanting the submitted view use
    :meth:`get_context`.
    """
    return [dict(item) for item in self._messages]

  def truncate_oldest_non_system(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
    drop_count: int = 1,
    run: str | None = None,
  ) -> int:
    """Flag the oldest non-protected messages as dropped (stored=truth).

    Compaction does NOT physically remove messages: selected messages are
    marked with ``pruned.kind == "dropped"`` metadata and are excluded
    from the submitted view (``get_context``) while the stored list — and
    the persisted history — keeps everything. The protected set (see
    :meth:`_protected_indices`) is never flagged; the droppable complement
    is grouped into atomic tool-call units, already-flagged units are
    skipped without consuming ``drop_count``, and the oldest units are
    flagged first.

    Args:
      protect_first_user: Protect the first N real user messages after
        the scaffolding prefix.
      protect_last_user: Protect the last N user messages.
      protect_last_assistant: Protect the last N plain assistant messages
        (without ``tool_calls``).
      protect_last_tool_calls: Protect the last N tool-call units
        (assistant ``tool_calls`` frame + all its tool results).
      drop_count: Number of atomic units to drop (flag).
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of messages newly flagged as dropped.
    """
    if drop_count <= 0 or not self._messages:
      return 0

    protected = self._protected_indices(
      protect_first_user, protect_last_user, protect_last_assistant, protect_last_tool_calls
    )
    # Atomic units over the whole store, filtered to the droppable
    # complement of the protected set — a unit is droppable only when ALL
    # its messages are (the tool-call window protects whole units and the
    # other windows never hit a frame's members, so pairing never splits).
    units = []
    for unit in self._atomic_units(0):
      if all(idx not in protected for idx in range(unit[0], unit[1] + 1)):
        units.append(unit)
    if not units:
      return 0

    to_drop = min(drop_count, len(units))
    dropped_indices: set[int] = set()
    taken = 0
    while units and taken < to_drop:
      start, end = units.pop(0)
      unit_indices = set(range(start, end + 1))
      # Flag semantics keep dropped messages in the store, so units here
      # may already be fully dropped from an earlier call — skip them
      # without consuming drop_count.
      if all("pruned" in self._messages[idx] for idx in unit_indices):
        continue
      dropped_indices.update(unit_indices)
      taken += 1

    if not dropped_indices:
      return 0

    # Flag in place — stored messages are never removed. Each message
    # carries its own flag dict (no shared mutable state).
    for idx in dropped_indices:
      self._messages[idx]["pruned"] = _pruned_metadata("dropped", "cutoff", run=run)
    return len(dropped_indices)

  def prune_tool_results(self, min_age_turns: int, min_chars: int, run: str | None = None) -> int:
    """Flag old, large tool results as stubs (stored=truth, view=projection).

    Pipeline stage 1 of the framework-default compaction: a tool result's
    information value decays fast, but its body is often the single largest
    view item (a 10K-char read). Stubbing shrinks it to ~50 tokens while
    keeping role/name/tool_id — pairing stays intact and the projection
    (``get_context``) renders the deterministic stub.

    Selection rule — a ``role=tool`` message is stubbed when ALL hold:
      - its body is strictly longer than ``min_chars`` characters;
      - at least ``min_age_turns`` completed turns follow it. Age is
        position-derived (see :meth:`_ages_after_completed_turns`), never
        wall-clock — deterministic for the same stored state.
    User, assistant, system and already-flagged messages are never touched.

    Args:
      min_age_turns: Minimum number of completed turns after the result.
      min_chars: Minimum body length (chars) for a result to be stubbed.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of tool results newly flagged as stubs.
    """
    ages = self._ages_after_completed_turns()
    flagged = 0
    for index, message in enumerate(self._messages):
      if message.get("role") != "tool" or "pruned" in message:
        continue
      content = message.get("content")
      if not isinstance(content, str) or len(content) <= min_chars:
        continue
      if ages[index] < min_age_turns:
        continue
      message["pruned"] = _pruned_metadata(
        "stub", "prune_tool_results", chars=len(content), run=run
      )
      flagged += 1
    return flagged

  def force_stub_tool_results(self, min_chars: int, run: str | None = None) -> int:
    """Flag every large tool result as a stub, regardless of age.

    Pipeline stage 3 — the age-blind, last content-preserving pass: runs
    after the age-gated prunes when the view is still over target, and
    stubs EVERY tool result whose body exceeds ``min_chars`` — its age no
    longer matters, only the destructive cutoff stage may follow.
    Already-flagged, non-tool and short-body messages are never touched.

    Args:
      min_chars: Minimum body length (chars) for a result to be stubbed.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of tool results newly flagged as stubs.
    """
    flagged = 0
    for message in self._messages:
      if message.get("role") != "tool" or "pruned" in message:
        continue
      content = message.get("content")
      if not isinstance(content, str) or len(content) <= min_chars:
        continue
      message["pruned"] = _pruned_metadata(
        "stub", "force_stub_tool_results", chars=len(content), run=run
      )
      flagged += 1
    return flagged

  def prune_thinking(self, min_age_turns: int, run: str | None = None) -> int:
    """Flag old ``thinking`` payloads as pruned (stored=truth, view=projection).

    Pipeline stage 2: old reasoning data is rarely needed once its turn
    completed. The flag uses ``kind="thinking"`` — NOT ``kind="dropped"`` —
    because the projection excludes dropped messages from the view entirely,
    which would erase the assistant's actual response; a thinking-flagged
    message stays in the view with only its ``thinking`` key stripped
    (the projection drops flagged thinking for every backend). On backends
    that already strip all thinking in the view (``strip_thinking_in_view``)
    the measured token impact is therefore ~0 — the stage still flags, so
    stored history is marked and the report is honest about the ~0 effect.

    Age rule: same as :meth:`prune_tool_results` — completed turns strictly
    after the message, ``age >= min_age_turns`` to flag. Only assistant
    messages carry ``thinking`` in this codebase; system/user are skipped.

    Args:
      min_age_turns: Minimum number of completed turns after the message.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of messages newly flagged.
    """
    ages = self._ages_after_completed_turns()
    flagged = 0
    for index, message in enumerate(self._messages):
      if message.get("role") != "assistant" or "pruned" in message:
        continue
      if "thinking" not in message:
        continue
      if ages[index] < min_age_turns:
        continue
      message["pruned"] = _pruned_metadata("thinking", "prune_thinking", run=run)
      flagged += 1
    return flagged

  def _ages_after_completed_turns(self) -> list[int]:
    """Age of every stored message in completed turns, oldest position first.

    A COMPLETED TURN is an assistant message without ``tool_calls`` (the
    turn's final prose — ``add_tool_calls`` responses are mid-turn, so they
    do not count). A message's age is the number of completed turns strictly
    AFTER it: the newest turn's messages have age 0. Position-derived, so
    the same stored state always yields the same ages.

    Returns:
      One age per stored message, same order/length as the store.
    """
    n = len(self._messages)
    suffix = [0] * (n + 1)
    for index in range(n - 1, -1, -1):
      msg = self._messages[index]
      is_completed = msg.get("role") == "assistant" and "tool_calls" not in msg
      suffix[index] = suffix[index + 1] + (1 if is_completed else 0)
    # suffix[i+1] = completed turns at indices > i — exactly message i's age.
    return suffix[1:]

  def replace_messages(self, messages: list[dict[str, Any]]) -> None:
    """Replace the entire internal message list atomically.

    See ``ContextManager.replace_messages`` in the Protocol for the full
    contract. Used by the overflow hook (validated replacement list) and
    the thinking-block stripping fallback.

    Incoming items without the internal ``_appended_at`` stamp (hook
    replacements derive from the projected view, which strips it) are
    stamped ONCE here — replacement time IS their append time. Without
    this, the persist-side fallback would re-stamp those records with a
    fresh time on every later bulk rewrite (timestamp drift).
    """
    now = datetime.now().isoformat()
    self._messages = [dict(item) for item in messages]
    for item in self._messages:
      item.setdefault("_appended_at", now)

  def _protected_indices(
    self,
    protect_first_user: int,
    protect_last_user: int,
    protect_last_assistant: int,
    protect_last_tool_calls: int,
  ) -> set[int]:
    """Return the full protected index set for the cutoff stage.

    Protection layers, always applied:
      - Framework scaffolding (ALWAYS protected): all leading
        ``role=system`` messages plus the entire contiguous leading run
        of ``role=user`` messages (the skill-discovery/scaffolding
        prefix). Everything after that run is droppable territory.
      - Real user windows: the first ``protect_first_user`` user
        messages AFTER the scaffolding run, and the last
        ``protect_last_user`` user messages in the whole store
        (scaffolding users are already safe).
      - Plain assistant window: the last ``protect_last_assistant``
        messages with ``role=assistant`` and no ``tool_calls``.
      - Tool-call unit window: the last ``protect_last_tool_calls``
        tool-call units — an assistant ``tool_calls`` frame plus ALL its
        trailing contiguous ``role=tool`` results, protected together.

    Shared by :meth:`truncate_oldest_non_system` and
    :meth:`protected_context` so the two can never diverge.
    """
    n = len(self._messages)
    i = 0
    # Framework scaffolding: system messages, then the contiguous
    # leading user run (skill discovery etc.) — always protected.
    while i < n and self._messages[i].get("role") == "system":
      i += 1
    while i < n and self._messages[i].get("role") == "user":
      i += 1
    protected: set[int] = set(range(i))

    # First real user turns: the first N user messages after the
    # scaffolding run.
    first_user: list[int] = []
    while i < n and len(first_user) < protect_first_user:
      if self._messages[i].get("role") == "user":
        first_user.append(i)
      i += 1
    protected.update(first_user)

    # Last N user messages in the whole store (scaffolding already safe).
    if protect_last_user > 0:
      user_indices = [idx for idx, msg in enumerate(self._messages) if msg.get("role") == "user"]
      protected.update(user_indices[-protect_last_user:])

    # Last N plain assistant messages (no tool_calls).
    if protect_last_assistant > 0:
      plain = [
        idx
        for idx, msg in enumerate(self._messages)
        if msg.get("role") == "assistant" and "tool_calls" not in msg
      ]
      protected.update(plain[-protect_last_assistant:])

    # Last N tool-call units: frame + all its trailing tool results.
    if protect_last_tool_calls > 0:
      units = [unit for unit in self._atomic_units(0) if unit[1] > unit[0]]
      for start, end in units[-protect_last_tool_calls:]:
        protected.update(range(start, end + 1))
    return protected

  def protected_context(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
  ) -> list[dict[str, Any]]:
    """Return copies of the messages the cutoff protection makes non-droppable.

    The protected set (framework scaffolding + the four protection
    windows — see :meth:`_protected_indices`) rendered in store order as
    fresh copies. Chunk B of the compaction redesign uses this to compute
    the protection-floor estimate before running the cutoff stage.
    """
    protected = self._protected_indices(
      protect_first_user, protect_last_user, protect_last_assistant, protect_last_tool_calls
    )
    return [dict(self._messages[idx]) for idx in sorted(protected)]

  def protected_view(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
  ) -> list[dict[str, Any]]:
    """The cutoff-protected subset rendered exactly as :meth:`get_context` would.

    Same protected set as :meth:`protected_context` (:meth:`_protected_indices`,
    store order), but passed through the shared projection
    (:meth:`_project_view` + the ``images`` send-once contract) — the
    protection floor the cutoff stage can never go below, in the same
    shape the backend would receive it. Stub/dropped/thinking flags on
    protected items are applied exactly as for the full view.
    """
    protected = self._protected_indices(
      protect_first_user, protect_last_user, protect_last_assistant, protect_last_tool_calls
    )
    items = [dict(self._messages[idx]) for idx in sorted(protected)]
    return _strip_stale_images(self._project_view(items))

  def record_compaction(self, run: dict[str, Any]) -> None:
    """Record a compaction run report for later persistence (chunk C)."""
    self._compaction_runs.append(run)

  @property
  def compaction_runs(self) -> list[dict[str, Any]]:
    """Copies of the recorded compaction run reports, oldest first.

    Deep copies: run reports carry nested stage lists — a shallow copy
    would let callers mutate the recorded history through the accessor.
    """
    return [deepcopy(run) for run in self._compaction_runs]

  def _atomic_units(self, start: int) -> list[tuple[int, int]]:
    """Group droppable messages (indices >= start) into atomic units.

    An atomic unit is either:
      - a single message without ``tool_calls``, or
      - an assistant message with ``tool_calls`` followed by all its
        trailing contiguous ``role=tool`` result messages (dropped
        together so tool-call/tool-result pairing is never split).

    Returns:
      A list of (start_index, end_index) inclusive tuples, in order.
    """
    units: list[tuple[int, int]] = []
    i = start
    n = len(self._messages)
    while i < n:
      msg = self._messages[i]
      if msg.get("role") == "assistant" and "tool_calls" in msg:
        unit_start = i
        i += 1
        # Consume trailing tool result messages.
        while i < n and self._messages[i].get("role") == "tool":
          i += 1
        units.append((unit_start, i - 1))
      else:
        units.append((i, i))
        i += 1
    return units

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""
    self.add_message("user", user_message)

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    """End the current conversation turn.

    Args:
      assistant_message: The assistant's response content.
      thinking: Optional thinking/reasoning content from the assistant.
    """
    self.add_message("assistant", assistant_message, thinking=thinking)

  def clear(self) -> None:
    """Clear in-memory context (does not delete persisted state)."""
    self._messages.clear()

  def save(self) -> None:
    """Persist context to storage. No-op in the base implementation."""

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      False — the base implementation has no storage.
    """
    return False

  def delete(self) -> None:
    """Delete stored context from disk.

    Raises:
      NotImplementedError: The base implementation has no storage.
    """
    raise NotImplementedError("delete() not supported by this context manager")

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage."""
    message_count = sum(1 for item in self._messages if item.get("role") != "tool")
    turn_count = sum(1 for item in self._messages if item.get("role") == "user")

    return ContextStatistics(
      message_count=message_count,
      turn_count=turn_count,
      tool_call_count=0,
    )

  def close(self) -> None:
    """Release resources and flush any pending writes. No-op in the base."""

  def get_session_id(self) -> str:
    """Get the unique session identifier.

    Returns:
      "in-memory" for the base implementation.
    """
    return "in-memory"


def _pruned_metadata(
  kind: str,
  stage: str,
  *,
  chars: int | None = None,
  hint: str | None = None,
  run: str | None = None,
) -> dict[str, Any]:
  """Build a ``pruned`` flag for a stored message (stored=truth, view=projection).

  Compaction never removes or rewrites message bodies: it attaches this
  metadata flag, and the projection (get_context) interprets it. Keeping
  one schema for all flag kinds (stub / dropped) lets later pipeline
  stages, persistence, and UI all speak the same structure.
  """
  flag: dict[str, Any] = {
    "kind": kind,
    "stage": stage,
    "at": datetime.now().isoformat(),
  }
  if chars is not None:
    flag["chars"] = chars
  if hint is not None:
    flag["hint"] = hint
  if run is not None:
    flag["run"] = run
  return flag


def _prune_stub_text(message: dict[str, Any]) -> str:
  """Build the deterministic stub body for a flagged tool result.

  The text derives ONLY from the flag metadata plus stable message fields
  (name/tool_id) — never from timestamps rendered at view time — so the
  same stored state always produces a byte-identical view (prefix-cache
  stability).
  """
  flag = message.get("pruned", {})
  name = message.get("name", "tool")
  chars = flag.get("chars", len(str(message.get("content", ""))))
  hint = flag.get("hint")
  stage = flag.get("stage", "prune")
  desc = f" {hint}" if hint else ""
  return f"[elided: {name}{desc} — {chars:,} chars pruned by {stage}; re-run the tool if needed]"


def _strip_pruned_metadata(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop the framework-internal ``pruned`` key from outgoing view dicts.

  The flag drives the projection but must not leak into the backend
  payload. View dicts are already fresh copies, so the key is removed in
  place on the view only. The internal ``_appended_at`` append timestamp
  is stripped in the same pass — persistence metadata, never submitted.
  """
  for index, message in enumerate(messages):
    if "pruned" in message or "_appended_at" in message:
      messages[index] = {
        key: value for key, value in message.items() if key not in ("pruned", "_appended_at")
      }
  return messages


def _strip_flagged_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop ``thinking`` from every message carrying a ``pruned`` flag.

  Used for backends that keep thinking in the view (provider-side
  context management): a pruned message's thinking must still never be
  submitted — the flag marks the history as pruned.
  """
  for index, message in enumerate(messages):
    if "pruned" in message and "thinking" in message:
      messages[index] = {key: value for key, value in message.items() if key != "thinking"}
  return messages


def _strip_kind_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop ``thinking`` from messages flagged ``pruned.kind == "thinking"``.

  The prune_thinking pipeline stage uses this dedicated flag kind (NOT
  "dropped", which would exclude the whole message): only the reasoning
  payload leaves the view — for every backend, supporting or not — while
  the message itself and its stored thinking stay.
  """
  for index, message in enumerate(messages):
    pruned = message.get("pruned")
    if isinstance(pruned, dict) and pruned.get("kind") == "thinking" and "thinking" in message:
      messages[index] = {key: value for key, value in message.items() if key != "thinking"}
  return messages


def _strip_thinking_keys(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop the ``thinking`` key from every message in the outgoing view.

  Projection-level replacement for the former physical strip
  (``_maybe_strip_thinking``): stored thinking is retained (history
  survives in persistence), only the view loses it.
  """
  for index, message in enumerate(messages):
    if "thinking" in message:
      messages[index] = {key: value for key, value in message.items() if key != "thinking"}
  return messages


def _strip_stale_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Drop ``images`` refs from tool messages older than the last assistant turn.

  The submission contract for image reads is send-once: a freshly read image
  is included in the request immediately following the read, and removed from
  every subsequent request. The model must preserve what it needs by
  describing the image in its response text.

  A tool message keeps its images only when it appears after the most recent
  assistant message. This rule is stateless (no consumed-flags to bookkeep),
  retry-safe (a failed stream leaves the messages unchanged, so the image is
  still attached on retry) and resume-safe (on --resume every image predates
  the last assistant message and is stripped automatically).

  Args:
    messages: Outgoing message list (shallow copy; inner dicts are shared
      with the store per issue #38 and must never be mutated here).

  Returns:
    The same list; messages needing the strip are replaced with new dicts
    lacking the ``images`` key.
  """
  last_assistant = -1
  for index, message in enumerate(messages):
    if message.get("role") == "assistant":
      last_assistant = index

  stripped = False
  for index, message in enumerate(messages):
    if index <= last_assistant and "images" in message:
      messages[index] = {key: value for key, value in message.items() if key != "images"}
      stripped = True

  if stripped:
    logger.debug("stale_image_refs_stripped", count=last_assistant + 1)
  return messages


__all__ = ["BaseContextManager"]
