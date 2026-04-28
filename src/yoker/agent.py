"""Minimal Agent implementation for Yoker prototype."""

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
from yoker.logging import get_logger, log_timing
from yoker.thinking import ThinkingMode
from yoker.tools import Tool, ToolRegistry
from yoker.tools.list import ListTool
from yoker.tools.read import ReadTool
from yoker.tools.update import UpdateTool
from yoker.tools.write import WriteTool

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.context import ContextManager

log = get_logger(__name__)

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
    thinking_mode: Current thinking mode (on/off/silent).
    agent_definition: Loaded agent definition (if provided).
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
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
      thinking_mode: Thinking mode (on/off/silent, default: ON).
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

    # Validate configuration
    from yoker.config.validator import validate_config

    warnings = validate_config(self.config)
    for warning in warnings:
      log.warning("config_validation_warning", warning=warning)

    # Initialize client
    self.client = Client(host=self.config.backend.ollama.base_url)

    # Use provided model or config model
    self.model = model if model is not None else self.config.backend.ollama.model

    # Thinking mode state
    self.thinking_mode = thinking_mode

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

    # Initialize path guardrail for filesystem tool validation
    from yoker.tools.path_guardrail import PathGuardrail

    self._guardrail = PathGuardrail(self.config)

    # Build tool registry filtered by agent definition
    self.tool_registry = self._build_tool_registry()

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

    log.info(
      "agent_initialized",
      model=self.model,
      thinking_mode=self.thinking_mode.value,
      has_agent_definition=self.agent_definition is not None,
      available_tools=self.tool_registry.names,
    )

  def _build_tool_registry(self) -> ToolRegistry:
    """Build a tool registry filtered by agent definition.

    If an agent definition is loaded, only registers tools listed in
    the agent's tools field. Otherwise, registers all default tools.

    All filesystem tools are created with the agent's guardrail injected
    for defense-in-depth validation.

    Returns:
      ToolRegistry with available tools for this agent.
    """
    registry = ToolRegistry()

    # Create tools with guardrail injected for defense-in-depth
    tools: list[Tool] = [
      ReadTool(guardrail=self._guardrail),
      ListTool(guardrail=self._guardrail),
      WriteTool(guardrail=self._guardrail),
      UpdateTool(guardrail=self._guardrail),
    ]

    if self.agent_definition is not None:
      allowed_tools = {t.lower() for t in self.agent_definition.tools}
      for tool in tools:
        if tool.name.lower() in allowed_tools:
          registry.register(tool)
    else:
      for tool in tools:
        registry.register(tool)
    return registry

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
    log.info("turn_started", message_preview=message[:50])
    self._emit(TurnStartEvent(type=EventType.TURN_START, message=message))
    self.context.start_turn(message)

    # Process with model, handling tool calls in a loop
    while True:
      # Use streaming for better UX
      stream = self.client.chat(
        model=self.model,
        messages=self.context.get_context(),
        tools=self.tool_registry.get_schemas(),
        think=self.thinking_mode.is_enabled,
        stream=True,
      )

      # Accumulate partial fields
      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False
      in_content = False

      # Track stats from last chunk
      prompt_eval_count = 0
      eval_count = 0
      total_duration_ms = 0

      for chunk in stream:
        # Capture stats from done chunk
        if chunk.done:
          prompt_eval_count = chunk.prompt_eval_count or 0
          eval_count = chunk.eval_count or 0
          total_duration_ms = (chunk.total_duration or 0) // 1_000_000  # ns to ms

        # Handle thinking output
        if chunk.message.thinking:
          if not in_thinking and self.thinking_mode.is_visible:
            in_thinking = True
            self._emit(ThinkingStartEvent(type=EventType.THINKING_START))
          thinking += chunk.message.thinking
          if self.thinking_mode.is_visible:
            self._emit(
              ThinkingChunkEvent(
                type=EventType.THINKING_CHUNK,
                text=chunk.message.thinking,
              )
            )

        # Handle content output
        if chunk.message.content:
          if in_thinking and self.thinking_mode.is_visible:
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
      elif in_thinking and self.thinking_mode.is_visible:
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
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            total_duration_ms=total_duration_ms,
          )
        )

        log.info(
          "turn_completed",
          response_length=len(content),
          tool_calls_count=len(tool_calls),
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

        log.debug("tool_call", tool=tool_name, args=tool_args)

        tool = self.tool_registry.get(tool_name)
        if tool is None:
          result = f"Error: Unknown tool '{tool_name}'"
          success = False
          log.warning("tool_not_found", tool=tool_name)
        else:
          # Validate tool parameters through guardrail
          validation = self._guardrail.validate(tool_name, tool_args)
          if not validation.valid:
            log.info("guardrail_blocked", tool=tool_name, reason=validation.reason)
            result = f"Error: {validation.reason}"
            success = False
          else:
            if self.config.logging.include_permission_checks:
              log.info(
                "guardrail_allowed",
                tool=tool_name,
                path=tool_args.get("path"),
              )
            try:
              with log_timing("tool_execution", tool=tool_name):
                tool_result = tool.execute(**tool_args)
              success = tool_result.success
              result = tool_result.result if success else f"Error: {tool_result.error}"
            except Exception as e:
              result = f"Error executing tool: {e}"
              success = False
              log.error("tool_error", tool=tool_name, error=str(e))

        log.debug("tool_result", tool=tool_name, success=success)

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
          tool_id=getattr(call, "id", tool_name),
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

    log.info(
      "session_started",
      model=self.model,
      session_id=self.context.get_session_id(),
      thinking_mode=self.thinking_mode.value,
    )

    self._emit(
      SessionStartEvent(
        type=EventType.SESSION_START,
        model=self.model,
        thinking_enabled=self.thinking_mode.is_enabled,
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

    log.info("session_ended", reason=reason)

    self._emit(
      SessionEndEvent(
        type=EventType.SESSION_END,
        reason=reason,
      )
    )
