"""Tool registry building for the async Agent.

This module provides the tool registry construction logic used by AgentCore.
"""

import os
from typing import TYPE_CHECKING

from yoker.logging import get_logger
from yoker.tools import Tool, ToolRegistry
from yoker.tools.existence import ExistenceTool
from yoker.tools.git import GitTool
from yoker.tools.list import ListTool
from yoker.tools.mkdir import MkdirTool
from yoker.tools.read import ReadTool
from yoker.tools.search import SearchTool
from yoker.tools.update import UpdateTool
from yoker.tools.web_backend import OllamaWebFetchBackend, OllamaWebSearchBackend
from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.webfetch import WebFetchTool
from yoker.tools.websearch import WebSearchTool
from yoker.tools.write import WriteTool

if TYPE_CHECKING:
  from ollama import AsyncClient

  from yoker.agents import AgentDefinition
  from yoker.config import Config
  from yoker.tools.path_guardrail import PathGuardrail

log = get_logger(__name__)


def build_tool_registry(
  config: "Config",
  guardrail: "PathGuardrail",
  agent_definition: "AgentDefinition | None" = None,
  client: "AsyncClient | None" = None,
) -> ToolRegistry:
  """Build a tool registry filtered by agent definition.

  If an agent definition is loaded, only registers tools listed in
  the agent's tools field. Otherwise, registers all default tools.

  All filesystem tools are created with the agent's guardrail injected
  for defense-in-depth validation.

  Tools are only registered if their enabled flag is True in config.

  Args:
    config: Configuration object.
    guardrail: Path guardrail for filesystem tool validation.
    agent_definition: Loaded agent definition, if any.
    client: Optional AsyncClient for tools that need it (e.g., WebSearch).

  Returns:
    ToolRegistry with available tools for this agent.
  """
  registry = ToolRegistry()

  # Create tools with guardrail injected for defense-in-depth
  # Only add tools that are enabled in config
  tools: list[Tool] = []

  if config.tools.read.enabled:
    tools.append(ReadTool(guardrail=guardrail))

  if config.tools.list.enabled:
    tools.append(ListTool(guardrail=guardrail))

  if config.tools.write.enabled:
    tools.append(WriteTool(guardrail=guardrail))

  if config.tools.update.enabled:
    tools.append(UpdateTool(guardrail=guardrail))

  if config.tools.search.enabled:
    tools.append(SearchTool(guardrail=guardrail))

  if config.tools.existence.enabled:
    tools.append(ExistenceTool(guardrail=guardrail))

  if config.tools.mkdir.enabled:
    tools.append(MkdirTool(guardrail=guardrail))

  if config.tools.git.enabled:
    tools.append(
      GitTool(
        config=config.tools.git,
        guardrail=guardrail,
        permission_handlers=config.permissions.handlers,
      )
    )

  # Add WebSearchTool only if API key is available and client is provided
  if config.tools.websearch.enabled and os.environ.get("OLLAMA_API_KEY") and client is not None:
    websearch_config = WebGuardrailConfig(
      max_query_length=config.tools.websearch.max_query_length,
      domain_allowlist=config.tools.websearch.domain_allowlist,
      domain_blocklist=config.tools.websearch.domain_blocklist,
      requests_per_minute=config.tools.websearch.requests_per_minute,
      requests_per_hour=config.tools.websearch.requests_per_hour,
      block_private_cidrs=config.tools.websearch.block_private_cidrs,
      timeout_seconds=config.tools.websearch.timeout_seconds,
    )
    tools.append(
      WebSearchTool(
        backend=OllamaWebSearchBackend(async_client=client),
        guardrail=WebGuardrail(config=websearch_config),
      )
    )

  if config.tools.webfetch.enabled and os.environ.get("OLLAMA_API_KEY") and client is not None:
    webfetch_config = WebGuardrailConfig(
      domain_allowlist=config.tools.webfetch.domain_allowlist,
      domain_blocklist=config.tools.webfetch.domain_blocklist,
      block_private_cidrs=config.tools.webfetch.block_private_cidrs,
      require_https=config.tools.webfetch.require_https,
      timeout_seconds=config.tools.webfetch.timeout_seconds,
    )
    tools.append(
      WebFetchTool(
        backend=OllamaWebFetchBackend(async_client=client),
        guardrail=WebGuardrail(config=webfetch_config),
      )
    )

  # Log if web tools are unavailable
  if not os.environ.get("OLLAMA_API_KEY"):
    log.warning("web_search_unavailable", reason="OLLAMA_API_KEY not set")
    log.warning("web_fetch_unavailable", reason="OLLAMA_API_KEY not set")

  # Filter by agent definition if present
  if agent_definition is not None:
    allowed_tools = {t.lower() for t in agent_definition.tools}

    for tool in tools:
      tool_name_lower = tool.name.lower()
      yoker_tool_name = f"yoker:{tool_name_lower}"

      if tool_name_lower in allowed_tools or yoker_tool_name in allowed_tools:
        registry.register(tool)
  else:
    for tool in tools:
      registry.register(tool)

  return registry
