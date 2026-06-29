"""Litellm backend adapter for streaming chat.

Implements the ModelBackend Protocol for multiple providers (OpenAI, Anthropic,
and 100+ others) via the litellm library. Translates litellm's streaming events
into Yoker's ChatChunk instances with proper block boundaries.
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
    self._provider = config.backend.provider

  @property
  def provider(self) -> str:
    """Return the provider identifier."""
    return self._provider

  def _get_model_string(self, model: str) -> str:
    """Convert Yoker model name to litellm model string.

    Litellm uses the pattern "provider/model" to identify models:
      - "openai/gpt-4o" for OpenAI
      - "anthropic/claude-3-5-sonnet-20241022" for Anthropic
      - "ollama/llama3.2" for Ollama

    Args:
      model: Yoker model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022").

    Returns:
      Litellm model string with provider prefix.
    """
    return f"{self._provider}/{model}"

  def _get_api_key(self) -> str | None:
    """Extract API key from provider-specific config.

    Returns:
      API key for the configured provider, or None if not set.
    """
    backend_config = self.config.backend

    if self._provider == "ollama":
      return backend_config.ollama.api_key if backend_config.ollama else None
    elif self._provider == "openai":
      return backend_config.openai.api_key if backend_config.openai else None
    elif self._provider == "anthropic":
      return backend_config.anthropic.api_key if backend_config.anthropic else None
    else:
      # For unknown providers, check if there's a matching sub-config
      # This allows for future provider support without code changes
      return None

  def _get_base_url(self) -> str | None:
    """Extract base URL from provider-specific config.

    Returns:
      Base URL for the configured provider, or None if using default.
    """
    backend_config = self.config.backend

    if self._provider == "ollama" and backend_config.ollama:
      return backend_config.ollama.base_url
    elif self._provider == "openai" and backend_config.openai:
      return backend_config.openai.base_url
    elif self._provider == "anthropic" and backend_config.anthropic:
      return backend_config.anthropic.base_url

    return None

  def _build_kwargs(self, think: bool = False, **kwargs: Any) -> dict[str, Any]:
    """Build litellm kwargs from Yoker config and parameters.

    Handles provider-specific parameter mapping:
      - OpenAI o-series: reasoning_effort parameter
      - Anthropic: budget_tokens parameter
      - All providers: temperature, top_p, etc.

    Args:
      think: Enable thinking/reasoning mode.
      **kwargs: Additional parameters (for future extensibility).

    Returns:
      Dictionary of litellm kwargs.
    """
    litellm_kwargs: dict[str, Any] = {}
    backend_config = self.config.backend

    # Get provider-specific parameters
    if self._provider == "ollama" and backend_config.ollama:
      ollama_params = backend_config.ollama.parameters
      litellm_kwargs["temperature"] = ollama_params.temperature
      litellm_kwargs["top_p"] = ollama_params.top_p
      litellm_kwargs["top_k"] = ollama_params.top_k
      litellm_kwargs["num_ctx"] = ollama_params.num_ctx

    elif self._provider == "openai" and backend_config.openai:
      openai_params = backend_config.openai.parameters
      litellm_kwargs["temperature"] = openai_params.temperature
      litellm_kwargs["top_p"] = openai_params.top_p
      if openai_params.max_tokens is not None:
        litellm_kwargs["max_tokens"] = openai_params.max_tokens

      # OpenAI o-series models use reasoning_effort for thinking
      # Map think=True to reasoning_effort="high"
      if think and model_has_reasoning(self._get_model_string(backend_config.openai.model)):
        litellm_kwargs["reasoning_effort"] = "high"

    elif self._provider == "anthropic" and backend_config.anthropic:
      anthropic_params = backend_config.anthropic.parameters
      litellm_kwargs["temperature"] = anthropic_params.temperature
      litellm_kwargs["top_p"] = anthropic_params.top_p
      if anthropic_params.top_k is not None:
        litellm_kwargs["top_k"] = anthropic_params.top_k

      # Anthropic uses budget_tokens for thinking
      if think:
        litellm_kwargs["budget_tokens"] = anthropic_params.budget_tokens

      # Anthropic requires max_tokens
      litellm_kwargs["max_tokens"] = backend_config.anthropic.max_tokens

    return litellm_kwargs

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

    # Build litellm model string
    litellm_model = self._get_model_string(model)

    # Build kwargs
    litellm_kwargs = self._build_kwargs(think=think)

    # Add API key and base_url
    api_key = self._get_api_key()
    if api_key:
      litellm_kwargs["api_key"] = api_key

    base_url = self._get_base_url()
    if base_url:
      litellm_kwargs["api_base"] = base_url

    # Call litellm.acompletion
    response = await litellm.acompletion(
      model=litellm_model,
      messages=messages,
      tools=tools,
      stream=True,
      **litellm_kwargs,
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


def model_has_reasoning(model: str) -> bool:
  """Check if a litellm model supports reasoning_effort parameter.

  OpenAI o-series models (o1, o3) support reasoning_effort.

  Args:
    model: Litellm model string (e.g., "openai/o1-preview").

  Returns:
    True if the model supports reasoning_effort parameter.
  """
  # OpenAI o-series models
  if "openai/" in model:
    model_lower = model.lower()
    return any(o in model_lower for o in ["o1-", "o1_", "o3-", "o3_", "/o1", "/o3"])

  return False

