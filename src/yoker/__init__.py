"""

Yoker - A Python agent harness with configurable tools, guardrails, and multi-provider LLM backend integration.

One who yokes - the agent noun from "yoke" (PIE *yeug-* meaning "to join").
"""

from yoker.agents import AgentDefinition, load_agent_definition
from yoker.api import (
  ThinkingLiteral,
  agent,
  do,
  process,
  run_sync,
  session,
)
from yoker.builtin import __YOKER_MANIFEST__  # noqa: F401 — required by plugin loader
from yoker.config import Config
from yoker.context import (
  ContextManager,
  Persisted,
  SimpleContextManager,
)
from yoker.core import Agent
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
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
from yoker.session import Session

__version__ = "0.8.0"
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
  "ThinkingLiteral",
  # Agents
  "AgentDefinition",
  "load_agent_definition",
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
  "Persisted",
  "SimpleContextManager",
  # Exceptions
  "YokerError",
  "ConfigurationError",
  "ValidationError",
  "FileNotFoundError",
  "SessionNotFoundError",
  "ContextCorruptionError",
]
