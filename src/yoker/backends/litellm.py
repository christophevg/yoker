"""Litellm backend adapter for streaming chat.

Implements the ModelBackend Protocol for multiple providers (OpenAI, Anthropic,
and 100+ others) via the litellm library. Translates litellm's streaming events
into Yoker's ChatChunk instances with proper block boundaries.

Design:
  - Uses config.backend.params for all provider parameters (flattened dict)
  - Applies litellm-specific transforms (base_url → api_base, provider/model prefix)
  - OllamaBackend continues to read config directly (not via params)
"""

from collections.abc import AsyncIterator
from typing import Any

import litellm

from yoker.backends.protocol import (
  ChatChunk,
  ChatChunkEvent,
  ModelBackend,
  ToolCallDelta,
  UsageStats,
)
from yoker.config import Config


class LitellmBackend(ModelBackend):
  """Multi-provider backend implementing ModelBackend Protocol.

  Wraps litellm.acompletion() and provides streaming chat via chat_stream().
  Translates litellm's delta-style streaming into ChatChunk events with
  synthesized block boundaries.

  Supported providers:
    - OpenAI (GPT-4o, GPT-4o-mini, etc.)
    - Anthropic (Claude 3.5 Sonnet, Claude 3 Opus, etc.)
    - 100+ other providers via litellm

  Attributes:
    config: Yoker configuration object.
    provider: Provider identifier (e.g., "openai", "anthropic").
  """

  def __init__(self, config: Config) -> None:
    """Initialize the Litellm backend.

    Args:
      config: Yoker configuration object.
    """
    self.config = config

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

    Litellm streams deltas (delta.content, delta.reasoning_content, delta.tool_calls)
    and a final chunk with usage. This method synthesizes block boundaries:

    - CONTENT_START → CONTENT_DELTA* → CONTENT_STOP
    - THINKING_START → THINKING_DELTA* → THINKING_STOP
    - TOOL_CALL_START → TOOL_CALL_DELTA* → TOOL_CALL_STOP
    - USAGE → DONE

    Args:
      model: Model identifier (provider-specific).
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

    # Get flattened params from config
    params = self.config.backend.params

    # Build litellm model string: "provider/model"
    litellm_model = f"{self.config.backend.provider}/{model}"

    # Remove model from params (it's passed separately)
    params.pop("model", None)

    # litellm-specific transform: base_url → api_base
    if "base_url" in params:
      params["api_base"] = params.pop("base_url")

    # Remove timeout_seconds (not used by litellm in acompletion)
    params.pop("timeout_seconds", None)

    # Remove nested parameters object if present (we flatten in params)
    params.pop("parameters", None)

    # Add stream=True for streaming
    params["stream"] = True

    # Add tools if provided
    if tools:
      params["tools"] = tools

    # Handle think flag (provider-specific translation)
    # For OpenAI o-series models, reasoning_effort from config is passed through
    # For Anthropic, budget_tokens from config is passed through
    # No special handling needed - params already include these from config

    # Call litellm.acompletion
    response = await litellm.acompletion(
      model=litellm_model,
      messages=messages,
      **params,
    )

    # Process the stream
    async for chunk in response:
      # litellm chunks have choices[0].delta structure
      delta = chunk.choices[0].delta

      # Handle thinking/reasoning content (OpenAI o-series, Anthropic)
      if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        if not in_thinking:
          in_thinking = True
          yield ChatChunk(event=ChatChunkEvent.THINKING_START, index=0)

        yield ChatChunk(
          event=ChatChunkEvent.THINKING_DELTA,
          index=0,
          text=delta.reasoning_content,
        )

      # Handle regular content
      if hasattr(delta, "content") and delta.content:
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
          text=delta.content,
        )

      # Handle tool calls
      if hasattr(delta, "tool_calls") and delta.tool_calls:
        for tc in delta.tool_calls:
          # Each tool call has an index
          index = tc.index if hasattr(tc, "index") else 0

          if index not in in_tool_call:
            in_tool_call[index] = True
            # Emit TOOL_CALL_START
            yield ChatChunk(
              event=ChatChunkEvent.TOOL_CALL_START,
              index=index,
              tool_call=ToolCallDelta(
                index=index,
                id=tc.id,
                name=tc.function.name if tc.function else None,
                arguments_delta=None,
              ),
            )

          # Emit TOOL_CALL_DELTA with arguments delta
          if tc.function and tc.function.arguments:
            yield ChatChunk(
              event=ChatChunkEvent.TOOL_CALL_DELTA,
              index=index,
              tool_call=ToolCallDelta(
                index=index,
                arguments_delta=tc.function.arguments,
              ),
            )

      # Handle usage (final chunk)
      if hasattr(chunk, "usage") and chunk.usage:
        # Close any open blocks
        if in_thinking:
          yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
          in_thinking = False
        if in_content:
          yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
          in_content = False

        # Close any open tool calls
        for tool_index in list(in_tool_call.keys()):
          yield ChatChunk(
            event=ChatChunkEvent.TOOL_CALL_STOP,
            index=tool_index,
            tool_call=ToolCallDelta(index=tool_index),
          )
        in_tool_call.clear()

        # Emit USAGE with stats
        usage = UsageStats(
          input_tokens=chunk.usage.prompt_tokens,
          output_tokens=chunk.usage.completion_tokens,
        )
        yield ChatChunk(event=ChatChunkEvent.USAGE, usage=usage)

        # Emit DONE
        yield ChatChunk(event=ChatChunkEvent.DONE)
