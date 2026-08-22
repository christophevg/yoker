"""UI module for Yoker.

This module provides the UI layer abstraction, separating agent logic from
user interface concerns. It includes:

- UIHandler: Protocol defining the UI interface
- UIBridge: Event dispatcher bridging events to UI methods
- InteractiveUIHandler: Interactive terminal UI using prompt_toolkit and Rich
- BatchUIHandler: Non-interactive UI using stdin/stdout/stderr
- formatting: Shared tool output formatting (argument rendering, content preview)
"""

from yoker.ui.agent_display import AgentDisplay
from yoker.ui.batch import BatchUIHandler
from yoker.ui.bridge import UIBridge
from yoker.ui.formatting import format_tool_args, truncate_content_preview
from yoker.ui.handler import UIHandler
from yoker.ui.interactive import InteractiveUIHandler

__all__ = [
  "AgentDisplay",
  "UIHandler",
  "UIBridge",
  "InteractiveUIHandler",
  "BatchUIHandler",
  "format_tool_args",
  "truncate_content_preview",
]
