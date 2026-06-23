"""
yoker - A Python agent harness with configurable tools and guardrails.

One who yokes - the agent noun from "yoke" (PIE *yeug-* meaning "to join").
Pairs with "clitic" (both are joining tools).
"""

from structlog import get_logger

from yoker.agent import Agent
from yoker.agent.thinking import ThinkingMode
from yoker.agents import AgentDefinition, load_agent_definition
from yoker.builtin import __YOKER_MANIFEST__
from yoker.config import Config
from yoker.context import (
  BasicContextManager,
  ContextManager,
  ContextStatistics,
  PersistenceContextManager,
)
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
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
from yoker.logging import LoggingContext, configure_logging, log_timing

__version__ = "0.4.0"
__author__ = "Christophe VG"

__all__ = [
  # Version
  "__version__",
  "__author__",
  # Core classes
  "Agent",
  # Built-in plugin
  "__YOKER_MANIFEST__",
  # Agents
  "AgentDefinition",
  "load_agent_definition",
  # Thinking
  "ThinkingMode",
  # Configuration
  "Config",
  # Events
  "Event",
  "EventType",
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
