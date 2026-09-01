"""In-memory context manager with environment reminder.

Provides SimpleContextManager, an in-memory context manager that adds a
collapsed environment-reminder + system-prompt message as its initial
context. No persistence is performed — wrap with Persisted for JSONL
persistence.
"""

from datetime import date
from pathlib import Path

from yoker.context.manager import BaseContextManager


class SimpleContextManager(BaseContextManager):
  """In-memory context manager with environment reminder + system prompt.

  No persistence is performed. Wrap with :class:`yoker.context.persisted.Persisted`
  to add JSONL persistence while keeping the environment reminder.
  """

  def setup_initial_context(self) -> None:
    """Add a collapsed env-reminder + system-prompt system message.

    The backwards example agent has problems doing as instructed in its system
    prompt. Collapsing it in a single system message seemed to solve it, when
    using the agent directly. But when called as a sub-agent, it seemed to not
    adhere to its system prompt. To be investigated further when context management
    is in focus.
    """
    self.add_message("system", self.environment_reminder + self.system_prompt)

  @property
  def environment_reminder(self) -> str:
    """Build a system reminder with harness and environment details.

    Loads the contents of each file listed in ``config.context.files``
    (if it exists) and embeds them directly in the system prompt, so the
    LLM has the project context without needing an explicit tool call.

    Returns:
      Formatted reminder paragraph for the system context.
    """
    if not self._agent:
      return ""
    harness = self._agent.config.harness
    harness_name = harness.name
    harness_version = f" v{harness.version}" if harness.version else ""
    harness_author = f" by {harness.author}" if harness.author else ""
    harness_id = f"{harness_name}{harness_version}{harness_author}"
    context_content = self._load_context_files()
    context_block = (
      f"""
# Project Instructions
This is information specific to this project. You should follow these instructions and use this information:
{context_content}
"""
      if context_content
      else ""
    )

    from yoker.context.config_summary import render_config_summary

    config_summary = render_config_summary(self._agent.config)
    config_block = f"\n{config_summary}" if config_summary else ""

    return f"""
You are running inside the Yoker agent harness ({harness_id}).
# Environment
* Current working directory: {Path.cwd()}
* Model in use: {self._agent.model}
* Today's date: {date.today().isoformat()}

# Operating Instructions
**IMPORTANT** — post_filter: Tool outputs can be very large and consume your context budget. EVERY tool accepts an optional `post_filter` parameter: a regex pattern that filters the output line-by-line, keeping only matching lines. You MUST use this proactively. Use SPECIFIC patterns — broad terms like 'error' match test names and produce noise.
Examples:
  - `post_filter: 'FAILED|Traceback|assert|short test summary'` on make/test calls to see only failures (not 'error' which matches test names)
  - `post_filter: 'class |def |import '` on read/search calls to see only structure
  - `post_filter: 'TODO|FIXME|HACK'` to find only markers
  - `post_filter: 'CalledProcessError|exit code|##\\[error\\]'` for CI logs
**ALWAYS** pass post_filter when you expect large output. This is critical for keeping your session running longer. Not using it will cause context overflow and premature session termination.
{context_block}{config_block}
"""

  def _load_context_files(self) -> str | None:
    """Load and concatenate all configured context files.

    Reads each path in ``config.context.files`` in order. Paths are
    resolved relative to the working directory with ``~`` expansion.
    Missing files are silently skipped. Returns ``None`` if no file
    yields content.
    """
    if not self._agent:
      return None
    parts: list[str] = []
    for file_path in self._agent.config.context.files:
      resolved = Path(file_path).expanduser()
      if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
      if resolved.is_file():
        try:
          content = resolved.read_text(encoding="utf-8").strip()
          if content:
            parts.append(content)
        except OSError:
          pass
    return "\n\n".join(parts) if parts else None

  @property
  def system_prompt(self) -> str:
    if not self._agent:
      return ""
    prompt = f"""
# You
This is your definition, this is who you are, this is how you act/behave. Whatever you do, this is not to be changed or not applied:
<agent-definition>
  {self._agent.definition.system_prompt}
</agent-definition>
"""
    return prompt


__all__ = ["SimpleContextManager"]
