"""Skill tool implementation for Yoker.

Provides the SkillTool for invoking skills dynamically by name.
"""

from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.skills import format_invocation_block
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.skills import SkillRegistry

log = get_logger(__name__)


class SkillTool(Tool):
  """Tool to invoke skills by name.

  Allows the agent to load full skill content and execute it.
  The skill content is returned for the agent to follow.

  Skills are discovered through the discovery block in the system prompt,
  and this tool enables the agent to invoke them dynamically.

  Attributes:
    skill_registry: Registry of available skills for lookup.
  """

  def __init__(
    self,
    skill_registry: "SkillRegistry",
    guardrail: None = None,  # SkillTool doesn't need guardrail
  ) -> None:
    """Initialize SkillTool with skill registry.

    Args:
      skill_registry: Registry of available skills.
      guardrail: Not used for SkillTool (skills don't access filesystem).
    """
    super().__init__(guardrail=None)
    self._skill_registry = skill_registry

  @property
  def name(self) -> str:
    return "skill"

  @property
  def description(self) -> str:
    return (
      "Invoke a skill by name to get its full instructions. "
      "Use this tool when you want to execute a skill. "
      "The skill content will be loaded and you should follow its instructions."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the skill tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "skill_name": {
              "type": "string",
              "description": (
                "Name of the skill to invoke. "
                "Use the full skill name as shown in the discovery block "
                "(e.g., 'example', 'commit', 'pkgq:create')."
              ),
            },
            "args": {
              "type": "string",
              "description": (
                "Optional arguments to pass to the skill. "
                "The skill can use these arguments in its execution."
              ),
            },
          },
          "required": ["skill_name"],
        },
      },
    }

  async def execute(self, **kwargs: Any) -> ToolResult:
    """Execute the skill tool.

    Looks up the skill in the registry and returns its full content
    formatted as an invocation block for the agent to follow.

    Args:
      **kwargs: Parameters from the LLM tool call.
        - skill_name: Name of the skill to invoke (required).
        - args: Optional arguments for the skill.

    Returns:
      ToolResult with the skill invocation block or error message.
    """
    # Extract parameters
    skill_name = kwargs.get("skill_name", "")
    args = kwargs.get("args", "")

    # Look up skill in registry
    skill = self._skill_registry.get(skill_name)

    if skill is None:
      available_skills = ", ".join(sorted(self._skill_registry.names))
      error_msg = f"Unknown skill: {skill_name}. Available skills: {available_skills}"
      log.warning("skill_not_found", skill_name=skill_name, available=available_skills)
      return ToolResult(
        success=False,
        result=error_msg,
        error=error_msg,
      )

    # Format invocation block
    invocation = format_invocation_block(skill, args)

    log.info(
      "skill_invoked",
      skill_name=skill_name,
      skill_full_name=skill.full_name,
      has_args=bool(args),
    )

    return ToolResult(
      success=True,
      result=invocation,
    )

