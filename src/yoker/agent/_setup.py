"""Agent initialization helpers."""

from typing import TYPE_CHECKING, Any

from ollama import AsyncClient
from structlog import get_logger

from yoker.config import Config
from yoker.tools.web import (
  OllamaWebFetchBackend,
  OllamaWebSearchBackend,
  QueryWebGuardrail,
  UrlWebGuardrail,
  WebGuardrailConfig,
)

if TYPE_CHECKING:
  from yoker.context import ContextManager
  from yoker.skills import SkillRegistry

logger = get_logger(__name__)


def create_client(config: Config, client_cls: "type[AsyncClient] | None" = None) -> AsyncClient:
  """Create an async Ollama client from config."""
  cls = client_cls or AsyncClient
  api_key = config.backend.ollama.api_key
  base_url = config.backend.ollama.base_url
  if api_key:
    logger.info("async_ollama_client_initialized", host=base_url, auth="api_key")
    return cls(host=base_url, headers={"Authorization": f"Bearer {api_key}"})
  logger.info("async_ollama_client_initialized", host=base_url, auth="none")
  return cls(host=base_url)


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


def create_web_backends(config: Config, client: "AsyncClient | None") -> dict[str, Any]:
  """Create web tool backends for the configured provider.

  Populates the ``_tool_backends`` dict used by the ``websearch`` and
  ``webfetch`` tools. Backends are only populated when:

  - The configured provider is ``ollama`` (the only supported web-tool
    provider today).
  - An Ollama API key is configured (the Ollama web_search/web_fetch SDK
    calls require an authenticated client; the tools are also only
    registered when an API key is present).
  - The corresponding tool is enabled in config.

  Args:
    config: The Yoker configuration.
    client: The Ollama AsyncClient used by the Agent. May be None when no
      client could be constructed; in that case no backends are populated.

  Returns:
    A dict mapping tool names to backend instances. May be empty when the
    conditions above are not met.
  """
  backends: dict[str, Any] = {}

  if client is None:
    return backends

  if config.backend.provider != "ollama":
    return backends

  api_key = config.backend.ollama.api_key
  if not api_key:
    return backends

  if config.tools.websearch.enabled:
    backends["websearch"] = OllamaWebSearchBackend(
      async_client=client,
      timeout_seconds=config.tools.websearch.timeout_seconds,
    )
    logger.info("web_search_backend_populated", backend="ollama")

  if config.tools.webfetch.enabled:
    backends["webfetch"] = OllamaWebFetchBackend(
      async_client=client,
      timeout_seconds=config.tools.webfetch.timeout_seconds,
      max_size_kb=config.tools.webfetch.max_size_kb,
    )
    logger.info("web_fetch_backend_populated", backend="ollama")

  return backends


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
