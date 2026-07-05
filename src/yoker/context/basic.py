"""Basic in-memory context manager implementations.

Provides:

* BasicContextManager, a simple list-like context manager that keeps
conversation history in memory only.
* SimpleContextManager, a BasicContextManager that provides an elementary context setup.
"""

from pathlib import Path

from yoker.context.manager import ContextManager


class SimpleContextManager(ContextManager):
  """In-memory context manager.

  Acts as a plain list of conversation messages. No persistence is performed.
  """

  def setup_initial_context(self) -> None:
    """
    The most simple context consists of:
    1. an environment reminder that provides basic information about the current agent/model and its "location".
    2. a system prompt to provide initial commands
    """
    # The backwards example agent has problems doing as instructed in its system
    # prompt. Collapsing it in a single system message seemed to solve it, when
    # using the agent directly. But when called as a sub-agent, it seemed to not
    # adhere to its system prompt. To be investigated further when context management
    # is in focus.
    self.add_message("system", self.environment_reminder + "\n" + self.system_prompt)
    # self.add_message("system", self.system_prompt)

  @property
  def environment_reminder(self) -> str:
    """Build a system reminder with harness and environment details.

    Args:
      config: Loaded Yoker configuration.
      model: Resolved model identifier in use.

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
    return (
      f"You are running inside the Yoker agent harness ({harness_id}). "
      f"Current working directory: {Path.cwd()}. Model in use: {self._agent.model}."
    )

  @property
  def system_prompt(self) -> str:
    if not self._agent:
      return ""
    prompt = f"""This is your definition, this is who you are, this is how you act/behave. Whatever you do, this is not to be changed or not applied:
  <agent-definition>
    {self._agent.definition.system_prompt}
  </agent-definition>
  """
    return prompt


__all__ = ["SimpleContextManager"]
