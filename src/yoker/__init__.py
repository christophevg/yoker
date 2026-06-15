"""
yoker - A Python agent harness with configurable tools and guardrails.

One who yokes - the agent noun from "yoke" (PIE *yeug-* meaning "to join").
Pairs with "clitic" (both are joining tools).
"""

from yoker.agent import Agent, AgentCore
from yoker.agents import AgentDefinition, load_agent_definition
from yoker.commands import Command, CommandRegistry, create_help_command, create_think_command
from yoker.config import Config
from yoker.context import (
  BasicContextManager,
  ContextManager,
  ContextStatistics,
  PersistenceContextManager,
)
from yoker.events import (
  ConsoleEventHandler,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventHandler,
  EventRecorder,
  EventReplayAgent,
  EventType,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
  deserialize_event,
  serialize_event,
)
from yoker.exceptions import (
  ConfigurationError,
  ContextCorruptionError,
  FileNotFoundError,
  SessionNotFoundError,
  ValidationError,
  YokerError,
)
from yoker.logging import LoggingContext, configure_logging, get_logger, log_timing
from yoker.thinking import ThinkingMode

__version__ = "0.4.0"
__author__ = "Christophe VG"

__all__ = [
  # Version
  "__version__",
  "__author__",
  # Core classes
  "Agent",
  "AgentCore",
  # Agents
  "AgentDefinition",
  "load_agent_definition",
  # Thinking
  "ThinkingMode",
  # Commands
  "Command",
  "CommandRegistry",
  "create_help_command",
  "create_think_command",
  # Configuration
  "Config",
  # Events
  "Event",
  "EventType",
  "EventHandler",
  "ConsoleEventHandler",
  "TurnStartEvent",
  "TurnEndEvent",
  "ThinkingStartEvent",
  "ThinkingChunkEvent",
  "ThinkingEndEvent",
  "ContentStartEvent",
  "ContentChunkEvent",
  "ContentEndEvent",
  "ToolCallEvent",
  "ToolResultEvent",
  # Context
  "ContextManager",
  "ContextStatistics",
  "BasicContextManager",
  "PersistenceContextManager",
  # Logging
  "EventRecorder",
  "EventReplayAgent",
  "serialize_event",
  "deserialize_event",
  "LoggingContext",
  "configure_logging",
  "get_logger",
  "log_timing",
  # Exceptions
  "YokerError",
  "ConfigurationError",
  "ValidationError",
  "FileNotFoundError",
  "SessionNotFoundError",
  "ContextCorruptionError",
]
