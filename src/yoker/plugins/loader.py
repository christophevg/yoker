"""Plugin loader for Yoker.

Discovers and loads plugins from Python packages. The modern pattern is to
expose a `__YOKER_MANIFEST__` object in the package's top-level `__init__.py`.
For backwards compatibility, the loader also falls back to importing a
`{package}.yoker` submodule and reading `TOOLS`, `SKILLS`, and `AGENTS` lists.
New plugins should always use `__YOKER_MANIFEST__`.
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

  Supports two patterns:
    1. Preferred: package exposes `__YOKER_MANIFEST__` directly
       (e.g., `yoker_plugin_demo.__YOKER_MANIFEST__`).
    2. Legacy: package provides a `{package}.yoker` submodule with
       `TOOLS`, `SKILLS`, and `AGENTS` lists.

  Args:
    package_name: Python package name (e.g., "pkgq", "c3", "yoker_plugin_demo").

  Returns:
    PluginComponents if plugin exists, None if not found.

  Raises:
    PluginError: If plugin module exists but fails to load.

  Example:
    plugin = load_plugin("yoker_plugin_demo")
    if plugin:
        register_tools(plugin.tools, registry, namespace=plugin.source)
  """
  # First check if the package itself exists
  try:
    package = importlib.import_module(package_name)
  except ImportError:
    # Package doesn't exist - this is an error
    print(
      f"Error: Plugin package '{package_name}' not found. Install it with: pip install {package_name}"
    )
    return None

  # Try loading from package directly (new pattern: yoker_plugin_demo)
  if hasattr(package, "__YOKER_MANIFEST__"):
    log.info("plugin_manifest_found_in_package", package=package_name)
    return _load_from_module(package, package_name)

  # Try loading from {package}.yoker submodule (legacy pattern)
  module_name = f"{package_name}.yoker"
  try:
    module = importlib.import_module(module_name)
    log.info("plugin_module_imported", package=package_name, module=module_name)
    return _load_from_module(module, package_name)
  except ImportError as e:
    # Package exists but no yoker submodule and no manifest - not a plugin
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


def _load_from_module(module: object, package_name: str) -> PluginComponents:
  """Load plugin components from a module.

  Args:
    module: Imported module object.
    package_name: Package name for namespacing.

  Returns:
    PluginComponents with loaded tools, skills, and agents.
  """
  # Extract component lists from explicit attributes.
  tools = _extract_list(module, "TOOLS")
  skills = _extract_list(module, "SKILLS")
  agents = _extract_list(module, "AGENTS")

  log.info(
    "plugin_components_extracted_initial",
    package=package_name,
    tools_count=len(tools),
    skills_count=len(skills),
    agents_count=len(agents),
  )

  # Check for manifest to discover skills/agents from directories
  manifest = getattr(module, "__YOKER_MANIFEST__", None)
  if manifest is not None:
    log.info(
      "plugin_manifest_found",
      package=package_name,
      has_manifest=True,
      skills_dir=manifest.skills_dir if hasattr(manifest, "skills_dir") else None,
      agents_dir=manifest.agents_dir if hasattr(manifest, "agents_dir") else None,
      has_tools=len(manifest.tools) if hasattr(manifest, "tools") and manifest.tools else 0,
    )

    # Load skills from skills_dir if declared
    if manifest.skills_dir:
      log.info(
        "loading_skills_from_dir",
        package=package_name,
        skills_dir=manifest.skills_dir,
      )
      discovered_skills = load_skills_from_package(package_name, manifest.skills_dir)
      log.info(
        "skills_discovered_from_dir",
        package=package_name,
        skills_dir=manifest.skills_dir,
        count=len(discovered_skills),
        skill_names=[s.name for s in discovered_skills],
      )
      if discovered_skills:
        skills = list(skills) + discovered_skills  # Merge with explicit skills
        log.info(
          "plugin_skills_merged",
          package=package_name,
          explicit_count=len(tools),
          discovered_count=len(discovered_skills),
          total_count=len(skills),
        )

    # Load agents from agents_dir if declared
    if manifest.agents_dir:
      log.info(
        "loading_agents_from_dir",
        package=package_name,
        agents_dir=manifest.agents_dir,
      )
      discovered_agents = load_agents_from_package(package_name, manifest.agents_dir)
      log.info(
        "agents_discovered_from_dir",
        package=package_name,
        agents_dir=manifest.agents_dir,
        count=len(discovered_agents),
        agent_names=[a.name for a in discovered_agents],
      )
      if discovered_agents:
        agents = list(agents) + discovered_agents  # Merge with explicit agents
        log.info(
          "plugin_agents_merged",
          package=package_name,
          explicit_count=len(agents) - len(discovered_agents),
          discovered_count=len(discovered_agents),
          total_count=len(agents),
        )

    # Merge tools from manifest if not already in TOOLS list
    if manifest.tools:
      existing_names = {t.name for t in tools}
      for tool in manifest.tools:
        if tool.name not in existing_names:
          tools.append(tool)
  else:
    log.info("plugin_manifest_not_found", package=package_name)

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

  Supports two patterns:
    1. Preferred: skills live directly inside the package (e.g.,
       `yoker_plugin_demo/skills/`).
    2. Legacy: skills live inside the `{package}.yoker` submodule
       (e.g., `pkgq.yoker/skills/`).

  Args:
    package: Package name (e.g., "pkgq", "yoker_plugin_demo").
    skills_dir: Directory name within package (default: "skills").

  Returns:
    List of Skill objects loaded from package.
  """
  if TYPE_CHECKING:
    pass
  from yoker.skills import Skill as SkillClass
  from yoker.skills import load_skill

  skills: list[SkillClass] = []

  log.info("load_skills_from_package_started", package=package, skills_dir=skills_dir)

  try:
    # Use importlib.resources to access package resources
    import importlib.resources as resources

    # Try package directly first (new pattern: yoker_plugin_demo)
    try:
      package_module = package
      log.info("trying_package_directly", package=package, module=package_module)

      if hasattr(resources, "files"):
        package_files = resources.files(package_module)
        skills_path = package_files / skills_dir

        if skills_path.is_dir():
          log.info("skills_directory_found_in_package", package=package, skills_dir=skills_dir)
          skills = _load_skills_from_directory(skills_path, package, package_module, skills_dir)
    except Exception as e:
      log.debug("package_direct_failed", package=package, error=str(e))

    # If no skills found, try legacy {package}.yoker submodule
    if not skills:
      yoker_module = f"{package}.yoker"
      log.info("trying_yoker_submodule", package=package, yoker_module=yoker_module)

      # Try to access the skills directory
      try:
        # Python 3.9+ API
        if hasattr(resources, "files"):
          # Use yoker submodule to access skills directory
          yoker_files = resources.files(yoker_module)
          log.info("yoker_files_accessed", package=package, yoker_module=yoker_module)

          skills_path = yoker_files / skills_dir
          log.info(
            "skills_path_constructed",
            package=package,
            skills_dir=skills_dir,
            is_dir=skills_path.is_dir() if hasattr(skills_path, "is_dir") else "unknown",
          )

          if skills_path.is_dir():
            log.info("skills_directory_found", package=package, skills_dir=skills_dir)
            entries = list(skills_path.iterdir())
            log.info(
              "skills_directory_entries",
              package=package,
              skills_dir=skills_dir,
              count=len(entries),
              entries=[str(e) for e in entries[:10]],  # Show first 10
            )

            skills = _load_skills_from_directory(skills_path, package, yoker_module, skills_dir)
        else:
          # Python 3.8 fallback (deprecated but still works)
          log.info("using_python38_fallback", package=package, skills_dir=skills_dir)
          with resources.path(yoker_module, skills_dir) as skills_path:
            if skills_path.is_dir():
              for skill_file in skills_path.glob("*.md"):
                if skill_file.name != "SKILL.md":
                  try:
                    skill = load_skill(skill_file, namespace=package)
                    skills.append(skill)
                    log.info(
                      "skill_loaded_python38",
                      package=package,
                      name=skill.name,
                      file=skill_file.name,
                    )
                  except Exception as e:
                    log.warning(
                      "plugin_skill_load_failed",
                      package=package,
                      file=str(skill_file),
                      error=str(e),
                    )
            else:
              log.warning(
                "skills_dir_not_directory_python38",
                package=package,
                skills_dir=skills_dir,
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

  log.info(
    "load_skills_from_package_completed",
    package=package,
    skills_dir=skills_dir,
    count=len(skills),
    names=[s.name for s in skills],
  )

  return skills


def _load_skills_from_directory(
  skills_path: Any,
  package: str,
  module_name: str,
  skills_dir: str,
) -> list["Skill"]:
  """Load skills from a skills directory.

  Args:
    skills_path: Path to skills directory (from resources.files).
    package: Package name for namespacing.
    module_name: Module name for source path.
    skills_dir: Directory name within package.

  Returns:
    List of Skill objects loaded from directory.
  """
  from yoker.skills import parse_skill_frontmatter
  from yoker.skills.schema import Skill

  skills: list[Skill] = []

  entries = list(skills_path.iterdir())
  log.info(
    "skills_directory_entries",
    package=package,
    skills_dir=skills_dir,
    count=len(entries),
    entries=[str(e) for e in entries[:10]],  # Show first 10
  )

  for entry in skills_path.iterdir():
    # Handle both flat (.md files) and nested (subdir/SKILL.md) structures
    if hasattr(entry, "is_file") and entry.is_file():
      # Flat structure: skill.md directly in skills/
      if hasattr(entry, "suffix") and entry.suffix == ".md" and entry.name != "SKILL.md":
        log.info(
          "flat_skill_file_found",
          package=package,
          file=entry.name,
        )
        try:
          content = entry.read_text()
          frontmatter, body = parse_skill_frontmatter(content)

          # Extract required fields
          name = frontmatter.get("name")
          description = frontmatter.get("description", "")

          if name:
            skill = Skill(
              name=str(name),
              description=str(description),
              content=body.strip(),
              namespace=package,
              source_path=f"{module_name}/{skills_dir}/{entry.name}",
            )
            skills.append(skill)
            log.info(
              "flat_skill_loaded",
              package=package,
              name=skill.name,
              full_name=skill.full_name,
            )
          else:
            log.warning(
              "flat_skill_missing_name",
              package=package,
              file=entry.name,
            )
        except Exception as e:
          log.warning(
            "plugin_skill_load_failed",
            package=package,
            file=str(entry),
            error=str(e),
          )
    elif hasattr(entry, "is_dir") and entry.is_dir():
      # Nested structure: skill-name/SKILL.md
      log.info(
        "nested_skill_directory_found",
        package=package,
        directory=entry.name,
      )
      skill_file = entry / "SKILL.md"
      if hasattr(skill_file, "is_file") and skill_file.is_file():
        log.info(
          "nested_skill_file_found",
          package=package,
          directory=entry.name,
          file="SKILL.md",
        )
        try:
          content = skill_file.read_text()
          frontmatter, body = parse_skill_frontmatter(content)

          # Extract required fields
          name = frontmatter.get("name")
          description = frontmatter.get("description", "")

          if name:
            skill = Skill(
              name=str(name),
              description=str(description),
              content=body.strip(),
              namespace=package,
              source_path=f"{module_name}/{skills_dir}/{entry.name}/SKILL.md",
            )
            skills.append(skill)
            log.info(
              "nested_skill_loaded",
              package=package,
              name=skill.name,
              full_name=skill.full_name,
            )
          else:
            log.warning(
              "nested_skill_missing_name",
              package=package,
              directory=entry.name,
            )
        except Exception as e:
          log.warning(
            "plugin_skill_load_failed",
            package=package,
            file=str(skill_file),
            error=str(e),
          )
      else:
        log.debug(
          "nested_skill_file_not_found",
          package=package,
          directory=entry.name,
        )

  return skills


def load_agents_from_package(
  package: str,
  agents_dir: str = "agents",
) -> list["AgentDefinition"]:
  """Load agents from package's agents/ folder.

  Supports two patterns:
    1. Preferred: agent definitions live directly inside the package
       (e.g., `yoker_plugin_demo/agents/`).
    2. Legacy: agent definitions live inside the `{package}.yoker`
       submodule (e.g., `pkgq.yoker/agents/`).

  Args:
    package: Package name (e.g., "pkgq", "yoker_plugin_demo").
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

    # Try package directly first (new pattern: yoker_plugin_demo)
    try:
      package_module = package
      log.info("trying_package_directly_for_agents", package=package, module=package_module)

      if hasattr(resources, "files"):
        package_files = resources.files(package_module)
        agents_path = package_files / agents_dir

        if agents_path.is_dir():
          log.info("agents_directory_found_in_package", package=package, agents_dir=agents_dir)
          agents = _load_agents_from_directory(agents_path, package, package_module, agents_dir)
    except Exception as e:
      log.debug("package_direct_failed_for_agents", package=package, error=str(e))

    # If no agents found, try legacy {package}.yoker submodule
    if not agents:
      yoker_module = f"{package}.yoker"
      log.info("trying_yoker_submodule_for_agents", package=package, yoker_module=yoker_module)

      # Try to access the agents directory
      try:
        if hasattr(resources, "files"):
          yoker_files = resources.files(yoker_module)
          agents_path = yoker_files / agents_dir
          if agents_path.is_dir():
            agents = _load_agents_from_directory(agents_path, package, yoker_module, agents_dir)
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


def _load_agents_from_directory(
  agents_path: Any,
  package: str,
  module_name: str,
  agents_dir: str,
) -> list["AgentDefinition"]:
  """Load agents from an agents directory.

  Args:
    agents_path: Path to agents directory (from resources.files).
    package: Package name for namespacing.
    module_name: Module name for source path.
    agents_dir: Directory name within package.

  Returns:
    List of AgentDefinition objects loaded from directory.
  """
  from yoker.agents import AgentDefinition

  agents: list[AgentDefinition] = []

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
          log.info(
            "agent_loaded_from_package",
            package=package,
            name=agent_def.name,
          )
      except Exception as e:
        log.warning(
          "plugin_agent_load_failed",
          package=package,
          file=str(agent_file),
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

    # Namespace tool names if namespace is provided
    # Tool names from plugin agents should use the plugin's namespace
    # Rules:
    # 1. yoker: namespace → built-in, keep as-is
    # 2. Short name (e.g., "demo:echo") → expand to full namespace
    # 3. Other namespaces → keep as-is (different plugin)
    # 4. No namespace → apply plugin's namespace
    if namespace:
      # Extract the plugin's short name from the full namespace
      # e.g., "examples.plugins.demo" → "demo"
      namespace_parts = namespace.split(".")
      short_name = namespace_parts[-1] if namespace_parts else namespace

      namespaced_tools = []
      for tool_name in tools_value:
        tool_str = str(tool_name)

        if tool_str.startswith("yoker:"):
          # Built-in yoker namespace - keep as-is
          namespaced_tools.append(tool_str)
        elif ":" in tool_str:
          # Check if it's the short form of the current plugin
          tool_namespace, tool_name_part = tool_str.split(":", 1)
          if tool_namespace == short_name:
            # Expand short namespace to full namespace
            namespaced_tools.append(f"{namespace}:{tool_name_part}")
          else:
            # Different plugin namespace - keep as-is
            namespaced_tools.append(tool_str)
        else:
          # No namespace - apply plugin's full namespace
          namespaced_tools.append(f"{namespace}:{tool_str}")
      tools_value = namespaced_tools

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
