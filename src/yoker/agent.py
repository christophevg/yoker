"""Minimal Agent implementation for Yoker prototype."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ollama import Client

from yoker.config import Config
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)
from yoker.tools import AVAILABLE_TOOLS

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.context import ContextManager

logger = logging.getLogger(__name__)

# Type alias for event callbacks
EventCallback = Callable[[Event], None]

# Default system prompt
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class Agent:
  """Minimal agent that chats with Ollama and uses tools.

  Attributes:
    client: Ollama client for API communication.
    model: Model to use for chat.
    config: Configuration object (or defaults if not provided).
    context: ContextManager for conversation history.
    thinking_enabled: Whether thinking mode is enabled.
    agent_definition: Loaded agent definition (if provided).
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    thinking_enabled: bool = True,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
  ) -> None:
    """Initialize the agent.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      thinking_enabled: Whether to enable thinking mode (default: True).
      command_registry: Optional command registry for slash-commands.
      agent_definition: Pre-loaded AgentDefinition to use for system prompt.
      agent_path: Path to agent definition file (Markdown with frontmatter).
      context_manager: Optional ContextManager for conversation persistence.
    """
    # Load configuration
    if config is not None:
      self.config = config
    elif config_path is not None:
      from yoker.config import load_config

      self.config = load_config(config_path)
    else:
      self.config = Config()

    # Initialize client
    self.client = Client(host=self.config.backend.ollama.base_url)

    # Use provided model or config model
    self.model = model if model is not None else self.config.backend.ollama.model

    # Use available tools (TODO: filter by config.tools)
    self.tools = AVAILABLE_TOOLS

    # Thinking mode state
    self.thinking_enabled = thinking_enabled

    # Command registry for slash-commands
    self.command_registry = command_registry

    # Load agent definition if path provided
    self.agent_definition: AgentDefinition | None = None
    system_prompt = DEFAULT_SYSTEM_PROMPT

    if agent_definition is not None:
      self.agent_definition = agent_definition
      system_prompt = agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT
    elif agent_path is not None:
      from yoker.agents import load_agent_definition

      self.agent_definition = load_agent_definition(agent_path)
      system_prompt = self.agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT

    # Initialize context manager
    if context_manager is not None:
      self.context = context_manager
    else:
      # Create default in-memory context manager
      from yoker.context import BasicPersistenceContextManager

      self.context = BasicPersistenceContextManager(
        storage_path=Path(self.config.context.storage_path),
        session_id=self.config.context.session_id,
      )

    # Add system prompt to context (skip if already exists, e.g., on resume)
    messages = self.context.get_messages()
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
      self.context.add_message("system", system_prompt)

    # Event handlers storage
    self._event_handlers: list[EventCallback] = []

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.

    Args:
      handler: Callable that receives Event objects.

    Example:
      def my_handler(event: Event):
        if isinstance(event, ContentChunkEvent):
          print(event.text, end='', flush=True)

      agent.add_event_handler(my_handler)
    """
    self._event_handlers.append(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler.

    Args:
      handler: The handler to remove.
    """
    self._event_handlers.remove(handler)

  def _emit(self, event: Event) -> None:
    """Emit an event to all registered handlers.

    Args:
      event: The event to emit.
    """
    for handler in self._event_handlers:
      handler(event)

  def process(self, message: str) -> str:
    """Process a single message and return the response.

    Handles tool calls internally until a final response is ready.
    Uses streaming when thinking is enabled.

    Emits events during processing:
    - TURN_START
    - THINKING_START/CHUNK/END (if enabled)
    - CONTENT_START/CHUNK/END
    - TOOL_CALL/RESULT (if tools called)
    - TURN_END

    Args:
      message: User message to process.

    Returns:
      Assistant's response text.
    """
    self._emit(TurnStartEvent(type=EventType.TURN_START, message=message))
    self.context.start_turn(message)

    # Process with model, handling tool calls in a loop
    while True:
      # Use streaming for better UX
      stream = self.client.chat(
        model=self.model,
        messages=self.context.get_context(),
        tools=list(self.tools.values()),
        think=self.thinking_enabled,
        stream=True,
      )

      # Accumulate partial fields
      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False
      in_content = False

      for chunk in stream:
        # Handle thinking output
        if chunk.message.thinking:
          if not in_thinking and self.thinking_enabled:
            in_thinking = True
            self._emit(ThinkingStartEvent(type=EventType.THINKING_START))
          thinking += chunk.message.thinking
          if self.thinking_enabled:
            self._emit(
              ThinkingChunkEvent(
                type=EventType.THINKING_CHUNK,
                text=chunk.message.thinking,
              )
            )

        # Handle content output
        if chunk.message.content:
          if in_thinking and self.thinking_enabled:
            in_thinking = False
            self._emit(
              ThinkingEndEvent(
                type=EventType.THINKING_END,
                total_length=len(thinking),
              )
            )
          if not in_content:
            in_content = True
            self._emit(ContentStartEvent(type=EventType.CONTENT_START))
          content += chunk.message.content
          self._emit(
            ContentChunkEvent(
              type=EventType.CONTENT_CHUNK,
              text=chunk.message.content,
            )
          )

        # Handle tool calls
        if chunk.message.tool_calls:
          tool_calls.extend(chunk.message.tool_calls)

      # End content if we were streaming
      if in_content:
        self._emit(
          ContentEndEvent(
            type=EventType.CONTENT_END,
            total_length=len(content),
          )
        )
      elif in_thinking and self.thinking_enabled:
        # No content, but thinking ended
        self._emit(
          ThinkingEndEvent(
            type=EventType.THINKING_END,
            total_length=len(thinking),
          )
        )

      # If no tool calls, we're done with this turn
      if not tool_calls:
        self.context.end_turn(content)
        self._emit(
          TurnEndEvent(
            type=EventType.TURN_END,
            response=content,
            tool_calls_count=len(tool_calls),
          )
        )

        # Persist context if configured
        if self.config.context.persist_after_turn:
          self.context.save()

        return content

      # Process tool calls
      for call in tool_calls:
        tool_name = call.function.name
        tool_args = call.function.arguments

        self._emit(
          ToolCallEvent(
            type=EventType.TOOL_CALL,
            tool_name=tool_name,
            arguments=tool_args,
          )
        )

        logger.info(f"Tool call: {tool_name}({tool_args})")

        try:
          result = self.tools[tool_name](**tool_args)
          success = True
        except KeyError:
          result = f"Error: Unknown tool '{tool_name}'"
          success = False
        except Exception as e:
          result = f"Error executing tool: {e}"
          success = False

        logger.info(f"Tool result: {result[:100]}...")

        self._emit(
          ToolResultEvent(
            type=EventType.TOOL_RESULT,
            tool_name=tool_name,
            result=str(result),
            success=success,
          )
        )

        # Add tool result to context
        self.context.add_tool_result(
          tool_name=tool_name,
          tool_id=call.id,
          result=str(result),
          success=success,
        )

  def begin_session(self) -> None:
    """Begin an agent session.

    Emits SESSION_START event with session metadata.
    Saves context to persist session state.
    Call this before processing messages.
    """
    # Save context to ensure session_start record is written
    self.context.save()

    self._emit(
      SessionStartEvent(
        type=EventType.SESSION_START,
        model=self.model,
        thinking_enabled=self.thinking_enabled,
      )
    )

  def end_session(self, reason: str = "quit") -> None:
    """End an agent session.

    Emits SESSION_END event.
    Closes context to ensure all data is persisted.
    Call this when done processing messages.

    Args:
      reason: Reason for ending the session (e.g., "quit", "error", "interrupt").
    """
    # Close context to write session_end record
    self.context.close()

    self._emit(
      SessionEndEvent(
        type=EventType.SESSION_END,
        reason=reason,
      )
    )
