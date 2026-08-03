"""Skill tool implementation for Yoker.

Provides the ``make_skill_tool`` factory that returns a callable for
invoking skills dynamically by name.
"""

from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.skills import format_invocation_block
from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.skills import SkillRegistry

logger = get_logger(__name__)


def make_skill_tool(skill_registry: "SkillRegistry") -> Any:
  """Create the skill tool callable."""

  async def skill(
    skill_name: Annotated[str, Text("Name of the skill to invoke")],
    args: Annotated[str, Text("Optional arguments")] = "",
  ) -> ToolResult:
    """Invoke a skill by name to get its full instructions."""
    resolved_name = skill_registry.resolve(skill_name)
    s = skill_registry.data.get(resolved_name) if resolved_name else None

    if s is None:
      available_skills = ", ".join(sorted(skill_registry.names))
      error_msg = f"Unknown skill: {skill_name}. Available skills: {available_skills}"
      logger.warning("skill_not_found", skill_name=skill_name, available=available_skills)
      return ToolResult(success=False, error=error_msg)

    invocation = format_invocation_block(s, args)

    logger.info(
      "skill() invoked",
      skill_name=skill_name,
      skill_full_name=s.name,
      resolved_name=resolved_name,
      has_args=bool(args),
    )

    return ToolResult(success=True, result=invocation)

  return skill


__all__ = ["make_skill_tool"]
