"""In-memory context manager with environment reminder.

Provides SimpleContextManager, an in-memory context manager that adds a
collapsed environment-reminder + system-prompt message as its initial
context. No persistence is performed — wrap with Persisted for JSONL
persistence.
"""

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

    Loads the contents of ``AGENTS.md`` from the current working directory
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
    agents_md_content = self._load_agents_md()
    agents_md_block = (
      f"""
# Project Instructions
This is information specific to this project. You should follow these instructions and use this information:
{agents_md_content}
"""
      if agents_md_content
      else ""
    )

    return f"""
You are running inside the Yoker agent harness ({harness_id}).
# Environment
* Current working directory: {Path.cwd()}
* Model in use: {self._agent.model}

# Operating Instructions
**IMPORTANT** — post_filter: Tool outputs can be very large and consume your context budget. EVERY tool accepts an optional `post_filter` parameter: a regex pattern that filters the output line-by-line, keeping only matching lines. You MUST use this proactively. Use SPECIFIC patterns — broad terms like 'error' match test names and produce noise.
Examples:
  - `post_filter: 'FAILED|Traceback|assert|short test summary'` on make/test calls to see only failures (not 'error' which matches test names)
  - `post_filter: 'class |def |import '` on read/search calls to see only structure
  - `post_filter: 'TODO|FIXME|HACK'` to find only markers
  - `post_filter: 'CalledProcessError|exit code|##\\[error\\]'` for CI logs
**ALWAYS** pass post_filter when you expect large output. This is critical for keeping your session running longer. Not using it will cause context overflow and premature session termination.
{agents_md_block}
"""

  @staticmethod
  def _load_agents_md() -> str | None:
    agents_md_path = Path.cwd() / "AGENTS.md"
    if agents_md_path.is_file():
      try:
        return agents_md_path.read_text(encoding="utf-8")
      except OSError:
        return None
    return None

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
