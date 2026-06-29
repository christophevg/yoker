"""Agent initialization helpers."""

from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.config import Config
from yoker.tools.web import (
  QueryWebGuardrail,
  UrlWebGuardrail,
  WebGuardrailConfig,
)

if TYPE_CHECKING:
  from yoker.context import ContextManager
  from yoker.skills import SkillRegistry

logger = get_logger(__name__)


def create_web_guardrails(
  config: Config,
) -> tuple[QueryWebGuardrail | None, UrlWebGuardrail | None]:
  """Create web query and URL guardrails from config.

  Returns a tuple of (query_guardrail, url_guardrail). Either entry may
  be None if the corresponding tool is disabled or no Ollama API key is
  configured.
  """
  api_key = config.backend.ollama.api_key

  if not api_key:
    return (None, None)

  query_guardrail: QueryWebGuardrail | None = None
  url_guardrail: UrlWebGuardrail | None = None

  if config.tools.websearch.enabled:
    query_config = WebGuardrailConfig(
      max_query_length=config.tools.websearch.max_query_length,
      domain_allowlist=config.tools.websearch.domain_allowlist,
      domain_blocklist=config.tools.websearch.domain_blocklist,
      requests_per_minute=config.tools.websearch.requests_per_minute,
      requests_per_hour=config.tools.websearch.requests_per_hour,
      block_private_cidrs=config.tools.websearch.block_private_cidrs,
      timeout_seconds=config.tools.websearch.timeout_seconds,
    )
    query_guardrail = QueryWebGuardrail(config=query_config)

  if config.tools.webfetch.enabled:
    url_config = WebGuardrailConfig(
      domain_allowlist=config.tools.webfetch.domain_allowlist,
      domain_blocklist=config.tools.webfetch.domain_blocklist,
      block_private_cidrs=config.tools.webfetch.block_private_cidrs,
      require_https=config.tools.webfetch.require_https,
      timeout_seconds=config.tools.webfetch.timeout_seconds,
    )
    url_guardrail = UrlWebGuardrail(config=url_config)

  return (query_guardrail, url_guardrail)


def validate_recursion_depth(config: Config, depth: int) -> int:
  """Validate recursion depth and return it."""
  max_depth = config.tools.agent.max_recursion_depth
  if depth < 0:
    raise ValueError(f"_recursion_depth must be non-negative, got {depth}")
  if depth > max_depth:
    raise ValueError(f"_recursion_depth ({depth}) exceeds max_recursion_depth ({max_depth})")
  return depth


def add_skill_discovery_block(
  config: Config, skill_registry: "SkillRegistry", context: "ContextManager"
) -> None:
  """Add skill discovery user message if enabled and skills exist."""
  if len(skill_registry) > 0 and config.skills.discovery:
    from yoker.skills import format_discovery_block

    skill_list = skill_registry.skills
    context.add_message("user", format_discovery_block(skill_list))
    logger.info("skill_discovery_added", skill_count=len(skill_list))
