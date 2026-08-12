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
    resource: Annotated[
      str, Text("Optional name of a bundled reference file the skill provides (e.g., references/more-info.md). Use this — not `yoker:read` — to load skill reference files, because their filesystem location varies across local checkout, installed package, and zip distribution.")
    ] = "",
  ) -> ToolResult:
    """Invoke a skill by name to get its full instructions.

    When ``resource`` is provided, returns the content of that resource
    file instead of the skill's invocation block. (e.g. ``"references/info.md"``).
    """
    resolved_name = skill_registry.resolve(skill_name)
    s = skill_registry.data.get(resolved_name) if resolved_name else None

    if s is None:
      available_skills = ", ".join(sorted(skill_registry.names))
      error_msg = f"Unknown skill: {skill_name}. Available skills: {available_skills}"
      logger.warning("skill_not_found", skill_name=skill_name, available=available_skills)
      return ToolResult(success=False, error=error_msg)

    # Resource mode: return the resource file content
    if resource:
      try:
        content = s.get_resource(resource)
      except FileNotFoundError as e:
        logger.warning(
          "skill_resource_not_found",
          skill_name=skill_name,
          resource=resource,
          error=str(e),
        )
        return ToolResult(success=False, error=str(e))
      except ValueError as e:
        logger.warning(
          "skill_resource_invalid",
          skill_name=skill_name,
          resource=resource,
          error=str(e),
        )
        return ToolResult(success=False, error=str(e))
      except Exception as e:
        logger.warning(
          "skill_resource_error",
          skill_name=skill_name,
          resource=resource,
          error=str(e),
        )
        return ToolResult(success=False, error=str(e))

      logger.info(
        "skill() resource loaded",
        skill_name=skill_name,
        skill_full_name=s.name,
        resolved_name=resolved_name,
        resource=resource,
      )
      return ToolResult(success=True, result=content)

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
