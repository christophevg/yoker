"""Agent definition module for Yoker.

Provides schema, loader, and validator for agent definitions.
"""

from yoker.agents.loader import (
  load_agent_definition,
  load_agent_definitions,
  parse_frontmatter,
)
from yoker.agents.registry import AgentRegistry
from yoker.agents.schema import ALL_TOOLS, AgentDefinition, AllToolsSentinel
from yoker.agents.validator import (
  validate_agent_definition,
  validate_non_empty_string,
  validate_tools,
)

__all__ = [
  # Registry
  "AgentRegistry",
  # Schema
  "AgentDefinition",
  "AllToolsSentinel",
  "ALL_TOOLS",
  # Loader
  "load_agent_definition",
  "load_agent_definitions",
  "parse_frontmatter",
  # Validator
  "validate_agent_definition",
  "validate_non_empty_string",
  "validate_tools",
]
