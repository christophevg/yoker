"""

Yoker - A Python agent harness with configurable tools, guardrails, and multi-provider LLM backend integration.

One who yokes - the agent noun from "yoke" (PIE *yeug-* meaning "to join").
"""

from structlog import get_logger

from yoker.agents import AgentDefinition, load_agent_definition
from yoker.api import (
  agent,
  do,
  process,
  run_sync,
  session,
)
from yoker.builtin import __YOKER_MANIFEST__
from yoker.config import Config
from yoker.context import (
  BaseContextManager,
  ContextManager,
  ContextManagerWrapper,
  ContextStatistics,
  Persisted,
  SimpleContextManager,
)
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
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
from yoker.session import Session

__version__ = "0.6.0"
__author__ = "Christophe VG"

__all__ = [
  # Version
  "__version__",
  "__author__",
  # Core classes
  "Agent",
  "Session",
  # Pythonic utility API (MBI-003)
  "process",
  "do",
  "run_sync",
  "agent",
  "session",
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
  "BaseContextManager",
  "ContextManagerWrapper",
  "Persisted",
  "ContextStatistics",
  "SimpleContextManager",
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
