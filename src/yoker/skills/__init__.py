"""Skill system for Yoker.

Skills are reusable prompts that guide agent behavior for specific tasks.
They can be invoked via slash commands (e.g., /commit) or natural language.

Key Components:
  - Skill: Frozen dataclass representing a skill definition
  - SkillRegistry: Name-based registry for skill lookup
  - load_skill(): Load a skill from a Markdown file
  - load_skills(): Load all skills from a directory
  - format_discovery_block(): Format skill list for LLM context
  - format_invocation_block(): Format full skill content for LLM context

Security:
  - SEC-1: Uses yaml.safe_load() for all YAML parsing
  - SEC-2: Validates skill directories against allowed paths
  - SEC-3: Enforces 100KB content size limit
  - SEC-4: Resolves symlinks before validation
  - SEC-5: Namespaces package skills with 'pkg:skill' format
"""

from yoker.skills.injection import (
  build_skill_context_message,
  format_discovery_block,
  format_invocation_block,
  match_skill_by_trigger,
)
from yoker.skills.loader import (
  MAX_SKILL_SIZE_KB,
  load_skill,
  load_skills,
  parse_skill_frontmatter,
)
from yoker.skills.registry import (
  SkillRegistry,
  create_default_skill_registry,
)
from yoker.skills.schema import Skill

__all__ = [
  # Schema
  "Skill",
  # Registry
  "SkillRegistry",
  "create_default_skill_registry",
  # Loader
  "load_skill",
  "load_skills",
  "parse_skill_frontmatter",
  "MAX_SKILL_SIZE_KB",
  # Injection
  "format_discovery_block",
  "format_invocation_block",
  "build_skill_context_message",
  "match_skill_by_trigger",
]
