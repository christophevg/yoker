"""Litellm backend adapter for streaming chat.

Implements the ModelBackend Protocol for multiple providers (OpenAI, Anthropic,
and 100+ others) via the litellm library. Translates litellm's streaming events
into Yoker's ChatChunk instances with proper block boundaries.

Design:
  - Reads config.backend.config directly for provider parameters
  - Applies litellm-specific transforms (base_url → api_base, provider/model prefix)
  - Flattens parameters dict into litellm kwargs
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
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

# Disable litellm's verbose logging
litellm.set_verbose = False

# Suppress INFO logging from litellm (try multiple logger names)
# litellm uses different logger names in different contexts
for logger_name in ["litellm", "LiteLLM", "LITELLM"]:
  logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


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
    # Convert tool call arguments from dict to JSON string for LiteLLM
    # Context stores arguments as dict (generic format)
    # LiteLLM expects arguments as JSON string (OpenAI format)
    for message in messages:
      if "tool_calls" in message:
        for tc in message["tool_calls"]:
          if "function" in tc and isinstance(tc["function"].get("arguments"), dict):
            tc["function"]["arguments"] = json.dumps(tc["function"]["arguments"])

    # State tracking for block boundaries
    in_thinking = False
    in_content = False
    in_tool_call: dict[int, bool] = {}  # tool_index -> in_block
    finish_reason: str | None = None

    # Get provider config
    sub_config = self.config.backend.config

    # Build litellm model string: "provider/model"
    litellm_model = f"{self.config.backend.provider}/{model}"

    # Flatten config into litellm kwargs
    flattened: dict[str, Any] = {}

    # Add api_key if present
    if sub_config.api_key:
      flattened["api_key"] = sub_config.api_key

    # Add base_url if present (litellm uses 'api_base')
    if sub_config.base_url:
      flattened["api_base"] = sub_config.base_url

    # Add timeout (litellm uses 'timeout')
    flattened["timeout"] = sub_config.timeout_seconds

    # Flatten parameters dataclass into top-level kwargs, filtering None values
    if sub_config.parameters:
      params_dict = asdict(sub_config.parameters)
      # Filter None values and add to flattened
      for key, value in params_dict.items():
        if value is not None:
          flattened[key] = value

    # Add stream=True for streaming
    flattened["stream"] = True

    # Add tools if provided
    if tools:
      flattened["tools"] = tools
      logger.debug("Tools being passed to LiteLLM: %s", tools)

    # Log flattened parameters
    logger.debug("Flattened parameters for LiteLLM: %s", flattened)

    # Call litellm.acompletion
    response = await litellm.acompletion(
      model=litellm_model,
      messages=messages,
      **flattened,
    )

    # Process the stream
    logger.info("=== Entering stream processing loop ===")
    chunk_count = 0
    async for chunk in response:
      chunk_count += 1
      # Log raw chunk for debugging
      logger.debug("Raw chunk #%d from LiteLLM: %s", chunk_count, chunk)
      logger.debug("  Chunk type: %s", type(chunk).__name__)

      # Log chunk attributes (usage vs usageMetadata)
      if hasattr(chunk, "usage"):
        logger.debug("  Chunk has 'usage' attribute: %s", chunk.usage)
      if hasattr(chunk, "usageMetadata"):
        logger.debug("  Chunk has 'usageMetadata' attribute: %s", chunk.usageMetadata)

      # Track finish_reason for cleanup at end of stream
      if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
        finish_reason = chunk.choices[0].finish_reason
        logger.debug("  Finish reason: %s", finish_reason)

      # litellm chunks have choices[0].delta structure
      delta = chunk.choices[0].delta

      # Handle thinking/reasoning content (OpenAI o-series, Anthropic)
      if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        if not in_thinking:
          in_thinking = True
          logger.debug(">>> Yielding ChatChunk: THINKING_START")
          yield ChatChunk(event=ChatChunkEvent.THINKING_START, index=0)

        logger.debug(
          ">>> Yielding ChatChunk: THINKING_DELTA (len=%d)", len(delta.reasoning_content)
        )
        yield ChatChunk(
          event=ChatChunkEvent.THINKING_DELTA,
          index=0,
          text=delta.reasoning_content,
        )

      # Handle regular content
      if hasattr(delta, "content") and delta.content:
        # Close thinking block if we were in one
        if in_thinking:
          logger.debug(">>> Yielding ChatChunk: THINKING_STOP")
          yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
          in_thinking = False

        if not in_content:
          in_content = True
          logger.debug(">>> Yielding ChatChunk: CONTENT_START")
          yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)

        logger.debug(">>> Yielding ChatChunk: CONTENT_DELTA (len=%d)", len(delta.content))
        yield ChatChunk(
          event=ChatChunkEvent.CONTENT_DELTA,
          index=0,
          text=delta.content,
        )

      # Handle tool calls
      if hasattr(delta, "tool_calls") and delta.tool_calls:
        logger.debug(">>> Delta has tool_calls: %d calls", len(delta.tool_calls))
        for tc in delta.tool_calls:
          # Each tool call has an index
          index = tc.index if hasattr(tc, "index") else 0
          logger.debug(
            "  Tool call index=%d, id=%s, name=%s",
            index,
            tc.id if hasattr(tc, "id") else None,
            tc.function.name if tc.function and hasattr(tc.function, "name") else None,
          )

          if index not in in_tool_call:
            in_tool_call[index] = True
            # Emit TOOL_CALL_START
            logger.info(
              ">>> Yielding ChatChunk: TOOL_CALL_START (index=%d, id=%s, name=%s)",
              index,
              tc.id,
              tc.function.name if tc.function else None,
            )
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
            logger.info(
              ">>> Yielding ChatChunk: TOOL_CALL_DELTA (index=%d, args_len=%d)",
              index,
              len(tc.function.arguments),
            )
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
        logger.debug(">>> Processing usage chunk")
        # Close any open blocks
        if in_thinking:
          logger.debug(">>> Yielding ChatChunk: THINKING_STOP")
          yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
          in_thinking = False
        if in_content:
          logger.debug(">>> Yielding ChatChunk: CONTENT_STOP")
          yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
          in_content = False

        # Close any open tool calls
        for tool_index in list(in_tool_call.keys()):
          logger.debug(">>> Yielding ChatChunk: TOOL_CALL_STOP (index=%d)", tool_index)
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
        logger.info(
          ">>> Yielding ChatChunk: USAGE (input=%d, output=%d)",
          usage.input_tokens,
          usage.output_tokens,
        )
        yield ChatChunk(event=ChatChunkEvent.USAGE, usage=usage)

        # Emit DONE
        logger.info(">>> Yielding ChatChunk: DONE")
        yield ChatChunk(event=ChatChunkEvent.DONE)

    # Cleanup: Close any open blocks if stream ended without usage chunk
    # (e.g., Gemini ends with finish_reason='tool_calls' but no usage)
    if in_tool_call or in_content or in_thinking:
      logger.info(
        "Stream ended without usage chunk, closing open blocks (finish_reason=%s)", finish_reason
      )

      # Close thinking block if open
      if in_thinking:
        logger.debug(">>> Yielding ChatChunk: THINKING_STOP (cleanup)")
        yield ChatChunk(event=ChatChunkEvent.THINKING_STOP, index=0)
        in_thinking = False

      # Close content block if open
      if in_content:
        logger.debug(">>> Yielding ChatChunk: CONTENT_STOP (cleanup)")
        yield ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0)
        in_content = False

      # Close any open tool calls
      for tool_index in list(in_tool_call.keys()):
        logger.info(">>> Yielding ChatChunk: TOOL_CALL_STOP (cleanup, index=%d)", tool_index)
        yield ChatChunk(
          event=ChatChunkEvent.TOOL_CALL_STOP,
          index=tool_index,
          tool_call=ToolCallDelta(index=tool_index),
        )
      in_tool_call.clear()

      # Emit DONE after cleanup
      logger.info(">>> Yielding ChatChunk: DONE (cleanup)")
      yield ChatChunk(event=ChatChunkEvent.DONE)

    logger.info("=== Exited stream processing loop (processed %d chunks) ===", chunk_count)
