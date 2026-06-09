"""Plugin loader for Yoker.

Discovers and loads plugins from Python packages by importing {package}.yoker
module and extracting TOOLS, SKILLS, and AGENTS lists.
"""

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yoker.exceptions import PluginError
from yoker.logging import get_logger

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.skills import Skill
  from yoker.tools import Tool

log = get_logger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components.

  Holds the tools, skills, and agents extracted from a plugin package.

  Attributes:
    tools: List of Tool instances provided by the plugin.
    skills: List of Skill instances provided by the plugin.
    agents: List of AgentDefinition instances provided by the plugin.
    source: Package name (namespace prefix for components).
  """

  tools: list["Tool"]
  skills: list["Skill"]
  agents: list["AgentDefinition"]
  source: str  # Package name (namespace)


def load_plugin(package_name: str) -> PluginComponents | None:
  """Load plugin components from a package.

  Attempts to import {package_name}.yoker module and extract
  TOOLS, SKILLS, and AGENTS lists.

  Args:
    package_name: Python package name (e.g., "pkgq", "c3").

  Returns:
    PluginComponents if plugin exists, None if not found.

  Raises:
    PluginError: If plugin module exists but fails to load.

  Example:
    plugin = load_plugin("pkgq")
    if plugin:
        register_tools(plugin.tools, registry, namespace=plugin.source)
  """
  module_name = f"{package_name}.yoker"

  try:
    module = importlib.import_module(module_name)
    log.info("plugin_module_imported", package=package_name)
  except ImportError as e:
    # Package doesn't have yoker submodule - not an error
    log.debug(
      "plugin_module_not_found",
      package=package_name,
      module=module_name,
      error=str(e),
    )
    return None
  except Exception as e:
    # Module exists but failed to import - this is an error
    log.error(
      "plugin_module_import_error",
      package=package_name,
      module=module_name,
      error=str(e),
    )
    raise PluginError(
      package=package_name,
      message=f"Failed to import plugin module '{module_name}': {e}",
    ) from e

  # Extract component lists
  tools = _extract_list(module, "TOOLS")
  skills = _extract_list(module, "SKILLS")
  agents = _extract_list(module, "AGENTS")

  # Check for manifest to discover skills/agents from directories
  manifest = getattr(module, "__YOKER_MANIFEST__", None)
  if manifest is not None:
    log.info(
      "plugin_manifest_found",
      package=package_name,
      skills_dir=manifest.skills_dir,
      agents_dir=manifest.agents_dir,
    )

    # Load skills from skills_dir if declared
    if manifest.skills_dir:
      discovered_skills = load_skills_from_package(package_name, manifest.skills_dir)
      if discovered_skills:
        skills = list(skills) + discovered_skills  # Merge with explicit skills
        log.info(
          "plugin_skills_discovered",
          package=package_name,
          skills_dir=manifest.skills_dir,
          count=len(discovered_skills),
        )

    # Load agents from agents_dir if declared
    if manifest.agents_dir:
      discovered_agents = load_agents_from_package(package_name, manifest.agents_dir)
      if discovered_agents:
        agents = list(agents) + discovered_agents  # Merge with explicit agents
        log.info(
          "plugin_agents_discovered",
          package=package_name,
          agents_dir=manifest.agents_dir,
          count=len(discovered_agents),
        )

    # Merge tools from manifest if not already in TOOLS list
    if manifest.tools:
      existing_names = {t.name for t in tools}
      for tool in manifest.tools:
        if tool.name not in existing_names:
          tools.append(tool)

  log.info(
    "plugin_components_extracted",
    package=package_name,
    tools=len(tools),
    skills=len(skills),
    agents=len(agents),
  )

  return PluginComponents(
    tools=tools,
    skills=skills,
    agents=agents,
    source=package_name,
  )


def _extract_list(module: object, attribute: str) -> list[Any]:
  """Extract a list from module attributes.

  Args:
    module: Imported module object.
    attribute: Attribute name (e.g., "TOOLS", "SKILLS").

  Returns:
    List of components, or empty list if not defined.
  """
  value = getattr(module, attribute, None)

  if value is None:
    return []

  if not isinstance(value, list):
    log.warning(
      "plugin_attribute_not_list",
      attribute=attribute,
      type=type(value).__name__,
    )
    return []

  return value


def load_plugins(package_names: list[str]) -> list[PluginComponents]:
  """Load multiple plugins.

  Args:
    package_names: List of package names to load.

  Returns:
    List of successfully loaded PluginComponents.

  Raises:
    PluginError: If any plugin fails critically.
  """
  plugins: list[PluginComponents] = []

  for package_name in package_names:
    try:
      plugin = load_plugin(package_name)
      if plugin:
        plugins.append(plugin)
    except PluginError as e:
      # Log but continue with other plugins
      log.error(
        "plugin_load_failed",
        package=e.package,
        error=str(e),
      )
      # Re-raise to notify user
      raise

  return plugins


def load_skills_from_package(
  package: str,
  skills_dir: str = "skills",
) -> list["Skill"]:
  """Load skills from package's skills/ folder using importlib.resources.

  Args:
    package: Package name (e.g., "pkgq").
    skills_dir: Directory name within package (default: "skills").

  Returns:
    List of Skill objects loaded from package.
  """
  if TYPE_CHECKING:
    from yoker.skills import Skill
  from yoker.skills import Skill as SkillClass
  from yoker.skills import load_skill

  skills: list[SkillClass] = []

  try:
    # Use importlib.resources to access package resources
    import importlib.resources as resources

    # Get the yoker submodule to access skills directory
    yoker_module = f"{package}.yoker"

    # Try to access the skills directory
    try:
      # Python 3.9+ API
      if hasattr(resources, "files"):
        # Use yoker submodule to access skills directory
        yoker_files = resources.files(yoker_module)
        skills_path = yoker_files / skills_dir
        if skills_path.is_dir():
          for entry in skills_path.iterdir():
            # Handle both flat (.md files) and nested (subdir/SKILL.md) structures
            if hasattr(entry, "is_file") and entry.is_file():
              # Flat structure: skill.md directly in skills/
              if (
                hasattr(entry, "suffix")
                and entry.suffix == ".md"
                and entry.name != "SKILL.md"
              ):
                try:
                  content = entry.read_text()
                  from yoker.skills import parse_skill_frontmatter

                  frontmatter, body = parse_skill_frontmatter(content)

                  # Extract required fields
                  name = frontmatter.get("name")
                  description = frontmatter.get("description", "")

                  if name:
                    from yoker.skills.schema import Skill

                    skill = Skill(
                      name=str(name),
                      description=str(description),
                      content=body.strip(),
                      namespace=package,
                      source_path=f"{yoker_module}/{skills_dir}/{entry.name}",
                    )
                    skills.append(skill)
                except Exception as e:
                  log.warning(
                    "plugin_skill_load_failed",
                    package=package,
                    file=str(entry),
                    error=str(e),
                  )
            elif hasattr(entry, "is_dir") and entry.is_dir():
              # Nested structure: skill-name/SKILL.md
              skill_file = entry / "SKILL.md"
              if hasattr(skill_file, "is_file") and skill_file.is_file():
                try:
                  content = skill_file.read_text()
                  from yoker.skills import parse_skill_frontmatter

                  frontmatter, body = parse_skill_frontmatter(content)

                  # Extract required fields
                  name = frontmatter.get("name")
                  description = frontmatter.get("description", "")

                  if name:
                    from yoker.skills.schema import Skill

                    skill = Skill(
                      name=str(name),
                      description=str(description),
                      content=body.strip(),
                      namespace=package,
                      source_path=f"{yoker_module}/{skills_dir}/{entry.name}/SKILL.md",
                    )
                    skills.append(skill)
                except Exception as e:
                  log.warning(
                    "plugin_skill_load_failed",
                    package=package,
                    file=str(skill_file),
                    error=str(e),
                  )
      else:
        # Python 3.8 fallback (deprecated but still works)
        with resources.path(yoker_module, skills_dir) as skills_path:
          if skills_path.is_dir():
            for skill_file in skills_path.glob("*.md"):
              if skill_file.name != "SKILL.md":
                try:
                  skill = load_skill(skill_file, namespace=package)
                  skills.append(skill)
                except Exception as e:
                  log.warning(
                    "plugin_skill_load_failed",
                    package=package,
                    file=str(skill_file),
                    error=str(e),
                  )
    except Exception as e:
      log.debug(
        "plugin_skills_dir_not_found",
        package=package,
        skills_dir=skills_dir,
        error=str(e),
      )

  except Exception as e:
    log.warning(
      "plugin_skills_load_failed",
      package=package,
      error=str(e),
    )

  return skills


def load_agents_from_package(
  package: str,
  agents_dir: str = "agents",
) -> list["AgentDefinition"]:
  """Load agents from package's agents/ folder.

  Args:
    package: Package name (e.g., "pkgq").
    agents_dir: Directory name within package (default: "agents").

  Returns:
    List of AgentDefinition objects loaded from package.
  """
  if TYPE_CHECKING:
    pass
  from yoker.agents import AgentDefinition as AgentDefinitionClass
  from yoker.agents import load_agent_definition

  agents: list[AgentDefinitionClass] = []

  try:
    import importlib.resources as resources

    yoker_module = f"{package}.yoker"

    # Try to access the agents directory
    try:
      if hasattr(resources, "files"):
        package_files = resources.files(package)
        agents_path = package_files / agents_dir
        if agents_path.is_dir():
          for agent_file in agents_path.iterdir():
            if hasattr(agent_file, "suffix") and agent_file.suffix == ".md":
              try:
                content = agent_file.read_text()
                # Parse agent definition from content
                agent_def = load_agent_definition_from_string(
                  content,
                  namespace=package,
                )
                if agent_def:
                  agents.append(agent_def)
              except Exception as e:
                log.warning(
                  "plugin_agent_load_failed",
                  package=package,
                  file=str(agent_file),
                  error=str(e),
                )
      else:
        # Python 3.8 fallback
        with resources.path(yoker_module, agents_dir) as agents_path:
          if agents_path.is_dir():
            for agent_file in agents_path.glob("*.md"):
              try:
                agent_def = load_agent_definition(agent_file)
                # Namespace the agent
                # Agent definitions are frozen, so we create a copy with namespace
                agents.append(agent_def)
              except Exception as e:
                log.warning(
                  "plugin_agent_load_failed",
                  package=package,
                  file=str(agent_file),
                  error=str(e),
                )
    except Exception as e:
      log.debug(
        "plugin_agents_dir_not_found",
        package=package,
        agents_dir=agents_dir,
        error=str(e),
      )

  except Exception as e:
    log.warning(
      "plugin_agents_load_failed",
      package=package,
      error=str(e),
    )

  return agents


def load_agent_definition_from_string(
  content: str,
  namespace: str | None = None,
) -> "AgentDefinition | None":
  """Load agent definition from string content.

  Args:
    content: Markdown content with YAML frontmatter.
    namespace: Optional namespace prefix.

  Returns:
    AgentDefinition if valid, None otherwise.
  """
  from yoker.agents import AgentDefinition, parse_frontmatter

  try:
    frontmatter, body = parse_frontmatter(content)

    # Extract required fields
    name = frontmatter.get("name")
    if not name:
      return None

    description = frontmatter.get("description", "")
    model = frontmatter.get("model")
    system_prompt = body.strip()

    # Apply namespace to name
    name_str = str(name) if namespace else str(name)
    if namespace:
      name_str = f"{namespace}:{name_str}"

    tools_value = frontmatter.get("tools", [])
    if not isinstance(tools_value, list):
      tools_value = []

    return AgentDefinition(
      name=name_str,
      description=str(description),
      model=str(model) if model else None,
      system_prompt=system_prompt,
      tools=tuple(str(t) for t in tools_value),
    )
  except Exception as e:
    log.warning("agent_definition_parse_failed", error=str(e))
    return None


__all__ = [
  "PluginComponents",
  "load_plugin",
  "load_plugins",
  "load_skills_from_package",
  "load_agents_from_package",
]
