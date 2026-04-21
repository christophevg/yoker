"""
yoker - A Python agent harness with configurable tools and guardrails.

One who yokes - the agent noun from "yoke" (PIE *yeug-* meaning "to join").
Pairs with "clitic" (both are joining tools).
"""

from yoker.agent import Agent
from yoker.commands import Command, CommandRegistry, create_help_command, create_think_command
from yoker.config import (
  Config,
  load_config,
  load_config_with_defaults,
  validate_config,
)
from yoker.context import BasicPersistenceContextManager, ContextManager, ContextStatistics
from yoker.events import (
  ConsoleEventHandler,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ErrorEvent,
  Event,
  EventHandler,
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
from yoker.exceptions import (
  ConfigurationError,
  ContextCorruptionError,
  FileNotFoundError,
  SessionNotFoundError,
  ValidationError,
  YokerError,
)

__version__ = "0.1.0"
__author__ = "Christophe VG"

__all__ = [
  # Version
  "__version__",
  "__author__",
  # Core classes
  "Agent",
  # Commands
  "Command",
  "CommandRegistry",
  "create_help_command",
  "create_think_command",
  # Configuration
  "Config",
  "load_config",
  "load_config_with_defaults",
  "validate_config",
  # Events
  "Event",
  "EventType",
  "EventHandler",
  "ConsoleEventHandler",
  "SessionStartEvent",
  "SessionEndEvent",
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
  "ErrorEvent",
  # Context
  "ContextManager",
  "ContextStatistics",
  "BasicPersistenceContextManager",
  # Exceptions
  "YokerError",
  "ConfigurationError",
  "ValidationError",
  "FileNotFoundError",
  "SessionNotFoundError",
  "ContextCorruptionError",
]
