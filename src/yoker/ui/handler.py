"""UIHandler protocol definition.

This module defines the protocol that all UI handlers must implement.
The protocol ensures consistent interface across different UI implementations
(interactive, batch, API, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from yoker.ui.agent_display import AgentDisplay

if TYPE_CHECKING:
  from yoker.core import Agent


class UIHandler(Protocol):
  """Abstract interface for all UI operations.

  All methods receive raw, unformatted data.
  Implementations are responsible for formatting and output.

  Input methods return None for no input (end of session).
  Output methods should handle ANSI codes appropriately for their context.

  Streaming:
    Agent always streams by default.
    UI implementations can buffer if needed.
  """

  # === Lifecycle ===

  async def start(self, agent: Agent) -> None:
    """Start UI session. Called once at beginning.

    Args:
      agent: The Agent instance this UI session is serving.
    """
    ...

  async def shutdown(self, reason: str) -> None:
    """End UI session. Called once at end.

    Args:
      reason: Reason for ending ("quit", "error", "interrupt").
    """
    ...

  # === Input ===

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF).
    """
    ...

  async def get_secret_input(self, prompt: str = "> ") -> str | None:
    """Get secret user input (masked, not echoed).

    Used for credentials such as API keys. Implementations should mask the
    typed characters (e.g. prompt_toolkit ``is_password=True``). The value
    must never be echoed or logged by the handler.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF).
    """
    ...

  def output_info(self, text: str) -> None:
    """Output an informational text block.

    Used by the bootstrap wizard (and similar pre-session flows) to display
    multi-line informational text outside the streaming agent turn flow.
    Unlike :meth:`output_content`, this does not start a live/streaming
    display; it prints the text as a discrete block.

    Args:
      text: Informational text (may contain newlines).
    """
    ...

  async def output_step_title(self, step: int, total: int, title: str) -> None:
    """Output a wizard step title with a progress indicator.

    Used by the bootstrap wizard to render the "Step N of M: Title" line that
    precedes a step's body content. Interactive implementations may render it
    with visual emphasis (bold/underline); batch implementations render it as
    plain text. Implementations should emit a leading blank line before the
    title for steps after the first (``step > 1``) so consecutive steps are
    visually separated.

    Args:
      step: The 1-based step index.
      total: The total number of steps in the wizard flow.
      title: The human-readable step title.
    """
    ...

  # === Content Output (stdout in batch) ===

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Output content text.

    Args:
      content: Content text (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    ...

  def output_command_result(self, result: str) -> None:
    """Output command result.

    Args:
      result: Command output text.
    """
    ...

  # === Diagnostic Output (stderr in batch) ===

  def output_thinking(self, text: str) -> None:
    """Output thinking/trace text.

    Args:
      text: Thinking text (may contain ANSI from LLM).
    """
    ...

  def output_tool_call(
    self, tool_name: str, args: dict[str, object], agent: AgentDisplay | None = None
  ) -> None:
    """Output tool call information.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
      agent: The agent making this tool call, or None for the primary
        agent. Used for display in multi-agent sessions.
    """
    ...

  def output_tool_result(
    self, tool_name: str, success: bool, result: str, *, has_content: bool = False
  ) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
      has_content: Whether a rich ToolContentEvent follows for the same
        call — handlers rendering a plain result preview suppress it
        then to avoid rendering the call twice.
    """
    ...

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, object],
  ) -> None:
    """Output tool content (file contents, diff, etc.).

    Args:
      tool_name: Name of tool.
      operation: Operation type (read, write, update, etc.).
      path: File path.
      content: Content text (may be None for summary).
      content_type: MIME type of content.
      metadata: Additional metadata (lines, bytes, etc.).
    """
    ...

  def output_stats(
    self,
    duration_ms: int,
    prompt_tokens: int,
    eval_tokens: int,
    usage_limits: dict[str, object] | None = None,
    agent: AgentDisplay | None = None,
    context_estimate: int | None = None,
    context_max_tokens: int | None = None,
    context_target_tokens: int | None = None,
  ) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
      usage_limits: Optional backend API usage limits (e.g. Ollama cloud
        session/weekly usage percentages). None when unavailable.
      agent: The agent that produced this turn, or None for the primary
        agent. Used for display in multi-agent sessions.
      context_estimate: Calibrated estimate of the next backend call's
        pre-compaction context size (tokens), or None when unavailable.
      context_max_tokens: The context soft cap (``context.max_tokens``),
        or None when context management is off.
      context_target_tokens: The trim target (cap × compact_ratio), or
        None when context management is off.
    """
    ...

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    """Output error message.

    Args:
      error: Exception that occurred.
    """
    ...

  # === Streaming ===

  def start_content_stream(self, agent: AgentDisplay | None = None) -> None:
    """Start streaming content.

    Args:
      agent: The agent producing this content, or None for the primary
        agent. Used for display in multi-agent sessions.
    """
    ...

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream content chunk.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    ...

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    ...

  def start_thinking_stream(self, agent: AgentDisplay | None = None) -> None:
    """Start streaming thinking.

    Args:
      agent: The agent producing this thinking, or None for the primary
        agent. Used for display in multi-agent sessions.
    """
    ...

  def stream_thinking(self, chunk: str) -> None:
    """Stream thinking chunk.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    ...

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    ...

  # === Multi-agent (optional) ===
  #
  # ``agent_spawned(name: str) -> None`` and
  # ``agent_finished(name: str) -> None`` are **optional** protocol
  # methods, documented here but not defined as Protocol members. The
  # :class:`yoker.ui.bridge.UIBridge` guards calls with
  # ``getattr(handler, method, None)`` so handlers that do not implement
  # them (e.g. :class:`yoker.ui.batch.BatchUIHandler`) are not broken.
  # :class:`yoker.ui.interactive.InteractiveUIHandler` implements them to
  # surface sub-agent lifecycle to the user. No ``BaseUIHandler`` mixin
  # is recreated.
  #
  # When implemented:
  #   agent_spawned(agent: AgentDisplay)  - called when a sub-agent is spawned
  #     into the session; ``agent`` carries the spawned agent's id, name,
  #     color, model, and description.
  #   agent_finished(agent: AgentDisplay) - called when a sub-agent finishes
  #     and is removed from the active list; ``agent`` carries the finished
  #     agent's display info.

  # === Processing feedback (optional) ===
  #
  # ``start_processing() -> None`` and ``stop_processing() -> None`` are
  # **optional** protocol methods. The :class:`yoker.ui.bridge.UIBridge`
  # calls ``start_processing`` on ``TURN_START`` and after each
  # ``TOOL_RESULT`` to (re)start a visual "Processing..." indicator while
  # the model is working. The bridge calls ``stop_processing`` before any
  # output is rendered (content, thinking, tool call, etc.) so the
  # indicator does not interfere with output. Handlers that do not
  # implement them (e.g. :class:`yoker.ui.batch.BatchUIHandler`) are not
  # affected — the calls are guarded with ``hasattr`` in the bridge.
  # :class:`yoker.ui.interactive.InteractiveUIHandler` implements them
  # to manage a Rich status spinner.

  # === Protected-file / git-operation approval (MBI-009 T12, optional) ===
  #
  # ``confirm_approval(label: str, preview: str, kind: str = "file") -> bool``
  # is an **optional** protocol method, documented here but not defined as a
  # Protocol member. Unlike ``agent_spawned``/``agent_finished`` (which are
  # dispatched via :class:`yoker.ui.bridge.UIBridge`), ``confirm_approval`` is
  # wired directly onto ``Agent._approval_handler`` by
  # ``yoker.cli.chat._wire_approval_handler`` and awaited from
  # ``yoker.core._processing._maybe_approve_protected`` (with ``kind="file"``)
  # and from ``yoker.builtin.git._check_approval`` (with ``kind="git"``) —
  # :class:`UIBridge` is not involved. The wiring is gated by ``hasattr(ui,
  # "confirm_approval")`` so handlers that do not opt in are not wired;
  # for those handlers the :class:`yoker.tools.guardrails.path.WritePathGuardrail`
  # blocks write-protected files (no interactive prompt).
  #
  # :class:`yoker.ui.batch.BatchUIHandler` does **not** implement it
  # (non-interactive: protected writes are blocked by the guardrail).
  # :class:`yoker.ui.interactive.InteractiveUIHandler` implements it to
  # render the unified diff / command preview and prompt y/N (empty/EOF/
  # Ctrl+C = deny, fail-safe).
  #
  # When implemented:
  #   confirm_approval(label, preview, kind) - awaitable; returns True to
  #     proceed with the operation, False to block it. For ``kind="file"``,
  #     ``label`` is the resolved absolute path and ``preview`` is a unified
  #     diff between current and proposed content (for a new-file write,
  #     every line is an addition). For ``kind="git"``, ``label`` is
  #     ``"git <operation>"`` (e.g. ``"git commit"``) and ``preview`` is a
  #     command preview (staged diff for commit, unpushed commits for push,
  #     working-tree status for checkout).

  # === Context compaction notice (optional) ===
  #
  # ``output_context_overflow(dropped_count: int, estimated_tokens: int,
  # max_tokens: int, message_count: int, first_remaining: str | None = None,
  # target_tokens: int | None = None, stages: list[dict] | None = None,
  # sent_count: int | None = None, remaining_estimated_tokens: int | None = None,
  # run_id: str | None = None, floor_tokens: int | None = None,
  # target_clamped: bool = False) -> None`` is an **optional** protocol
  # method, dispatched via :class:`yoker.ui.bridge.UIBridge` on
  # :class:`yoker.events.ContextOverflowEvent` (guarded by ``getattr``).
  # The framework-default context management emits this event when the
  # estimated context size exceeded ``context.max_tokens`` and the
  # compaction pipeline pruned/flagged older non-setup messages to bring
  # the submitted view back under the trim target.
  #
  # :class:`yoker.ui.batch.BatchUIHandler` implements it as a stderr
  # diagnostic line; :class:`yoker.ui.interactive.InteractiveUIHandler`
  # renders it as a blue-bordered panel. Handlers that do not implement
  # it silently ignore compaction (previous behavior).
  #
  # When implemented:
  #   output_context_overflow(dropped_count, estimated_tokens, max_tokens,
  #     message_count, first_remaining, target_tokens, stages, sent_count,
  #     remaining_estimated_tokens, run_id, floor_tokens, target_clamped)
  #     - called once per compaction (suppressed when the pipeline flagged
  #     nothing and dropped nothing).
  #     ``dropped_count`` is the number of messages newly flagged by this
  #     run (stored-based; legacy meaning "permanently removed"),
  #     ``estimated_tokens`` the estimate that triggered the overflow,
  #     ``max_tokens`` the configured soft cap, and ``message_count`` the
  #     number of STORED messages after the pipeline.
  #     ``first_remaining`` is a one-line summary of the first
  #     non-protected message after compaction (where retained history
  #     starts), or None when only the protected prefix remains.
  #     ``target_tokens`` is the trim TARGET (``max_tokens *
  #     context.compact_ratio``) — None for events without hysteresis
  #     (pre-hysteresis records); only meaningful when it is below
  #     ``max_tokens``. ``stages`` lists the pipeline stages with non-zero
  #     impact ({"name", "messages", "tokens"} — tokens is the
  #     view-estimate reduction attributable to the stage), empty/None for
  #     old events. ``sent_count`` is the number of messages in the
  #     submitted view after the pipeline (what the model sees), and
  #     ``remaining_estimated_tokens`` the ACHIEVED post-pipeline view
  #     estimate — the truthful landing point — both None for old events.
  #     ``run_id`` is this compaction run's id (flags carry it in their
  #     ``pruned.run`` metadata), ``floor_tokens`` the calibrated estimate
  #     of the PROTECTED VIEW, and ``target_clamped`` True when the
  #     effective cutoff target was raised to that floor — all None/False
  #     for old events.
