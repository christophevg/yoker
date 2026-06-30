"""Ollama backend adapter for streaming chat.

Implements the ModelBackend Protocol for Ollama, wrapping the ollama.AsyncClient
and translating Ollama's streaming events into ChatChunk instances with proper
block boundaries.
"""

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from ollama import AsyncClient

from yoker.backends.protocol import (
  ChatChunk,
  ChatChunkEvent,
  ModelBackend,
  ToolCallDelta,
  UsageStats,
)

if TYPE_CHECKING:
  from yoker.config import Config, OllamaConfig


class OllamaBackend(ModelBackend):
  """Ollama backend implementing ModelBackend Protocol.

  Wraps the ollama.AsyncClient and provides streaming chat via chat_stream().
  Translates Ollama's delta-style streaming into ChatChunk events with
  synthesized block boundaries.
  """

  def __init__(self, config: "Config") -> None:
    """Initialize the Ollama backend.

    Args:
      config: Yoker configuration object.
    """
    self.config = config
    # Create AsyncClient from ollama config
    # Validation happens in BackendConfig.__post_init__()
    # Type assertion: OllamaConfig is guaranteed non-None when provider='ollama'
    ollama_config = cast("OllamaConfig", config.backend.config)

    self._client = AsyncClient(
      host=ollama_config.base_url,
      timeout=ollama_config.timeout_seconds,
    )

  def create_tool_backends(self) -> dict[str, Any]:
    """Create tool backends for web tools.

    Returns:
      A dict mapping tool names to backend instances. May be empty.
    """
    from structlog import get_logger

    from yoker.tools.web import OllamaWebFetchBackend, OllamaWebSearchBackend

    logger = get_logger(__name__)
    backends: dict[str, Any] = {}

    # Get Ollama config
    ollama_config = self.config.backend.config
    if ollama_config is None:
      return backends

    # Check for API key
    if not ollama_config.api_key:
      return backends

    # Create web search backend if enabled
    if self.config.tools.websearch.enabled:
      backends["websearch"] = OllamaWebSearchBackend(
        async_client=self._client,
        timeout_seconds=self.config.tools.websearch.timeout_seconds,
      )
      logger.info("web_search_backend_populated", backend="ollama")

    # Create web fetch backend if enabled
    if self.config.tools.webfetch.enabled:
      backends["webfetch"] = OllamaWebFetchBackend(
        async_client=self._client,
        timeout_seconds=self.config.tools.webfetch.timeout_seconds,
        max_size_kb=self.config.tools.webfetch.max_size_kb,
      )
      logger.info("web_fetch_backend_populated", backend="ollama")

    return backends

  async def chat_stream(
    self,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    think: bool = False,
    **kwargs: Any,
  ) -> AsyncIterator[ChatChunk]:
    """Stream a chat completion as a sequence of ChatChunk.

    Ollama streams deltas (chunk.message.content, chunk.message.thinking,
    chunk.message.tool_calls) and a final chunk.done with stats. This method
    synthesizes block boundaries:

    - CONTENT_START → CONTENT_DELTA* → CONTENT_STOP
    - THINKING_START → THINKING_DELTA* → THINKING_STOP
    - TOOL_CALL_START → TOOL_CALL_DELTA* → TOOL_CALL_STOP
    - USAGE → DONE

    Args:
      model: Model identifier (Ollama model name).
      messages: Conversation messages (OpenAI-style format).
      tools: Tool definitions (OpenAI function schema format).
      think: Enable thinking/reasoning mode.
      **kwargs: Internal use only (ignored).

    Yields:
      ChatChunk instances representing streaming events.
    """
    # State tracking for block boundaries
    in_thinking = False
    in_content = False
    in_tool_call: dict[int, bool] = {}  # tool_index -> in_block
    tool_call_buffer: dict[int, dict[str, Any]] = {}  # tool_index -> accumulated data

    # Call ollama.AsyncClient.chat with stream=True
    stream = await self._client.chat(
      model=model,
      messages=messages,
      tools=tools,
      stream=True,
      think=think,
    )

    # Process the stream
    async for chunk in stream:
      # Handle thinking content
      if chunk.message.thinking:
        if not in_thinking:
          in_thinking = True
          yield ChatChunk(event=ChatChunkEvent.THINKING_START, index=0)

        yield ChatChunk(
          event=ChatChunkEvent.THINKING_DELTA,
          index=0,
          text=chunk.message.thinking,
        )

      # Handle regular content
      if chunk.message.content:
        # Close thinking block if we were in one
        if in_thinking:
          yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
          in_thinking = False

        if not in_content:
          in_content = True
          yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)

        yield ChatChunk(
          event=ChatChunkEvent.CONTENT_DELTA,
          index=0,
          text=chunk.message.content,
        )

      # Handle tool calls
      if chunk.message.tool_calls:
        for tool_call in chunk.message.tool_calls:
          # Ollama streams tool calls as complete objects
          # We synthesize START/DELTA/STOP boundaries
          index = len(in_tool_call)
          if index not in in_tool_call:
            in_tool_call[index] = True
            tool_call_buffer[index] = {
              "id": getattr(tool_call, "id", None),
              "name": tool_call.function.name,
              "arguments": tool_call.function.arguments,
            }
            # Emit TOOL_CALL_START
            yield ChatChunk(
              event=ChatChunkEvent.TOOL_CALL_START,
              index=index,
              tool_call=ToolCallDelta(
                index=index,
                id=getattr(tool_call, "id", None),
                name=tool_call.function.name,
                arguments_delta=None,
              ),
            )
            # Emit TOOL_CALL_DELTA with full arguments (as JSON string)
            # Ollama returns arguments as a dict, convert to JSON string
            args_json = json.dumps(tool_call.function.arguments)
            yield ChatChunk(
              event=ChatChunkEvent.TOOL_CALL_DELTA,
              index=index,
              tool_call=ToolCallDelta(
                index=index,
                id=getattr(tool_call, "id", None),
                name=tool_call.function.name,
                arguments_delta=args_json,
              ),
            )
            # Emit TOOL_CALL_STOP
            yield ChatChunk(
              event=ChatChunkEvent.TOOL_CALL_STOP,
              index=index,
              tool_call=ToolCallDelta(
                index=index,
                id=getattr(tool_call, "id", None),
                name=tool_call.function.name,
                arguments_delta=None,
              ),
            )

      # Handle final chunk with stats
      if chunk.done:
        # Close any open blocks
        if in_thinking:
          yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
          in_thinking = False
        if in_content:
          yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
          in_content = False

        # Emit USAGE with stats
        usage = UsageStats(
          prompt_eval_count=chunk.prompt_eval_count,
          eval_count=chunk.eval_count,
          total_duration_ms=(chunk.total_duration or 0) // 1_000_000,
        )
        yield ChatChunk(event=ChatChunkEvent.USAGE, usage=usage)

        # Emit DONE
        yield ChatChunk(event=ChatChunkEvent.DONE)
