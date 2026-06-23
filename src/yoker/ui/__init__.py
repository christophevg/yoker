"""UI module for Yoker.

This module provides the UI layer abstraction, separating agent logic from
user interface concerns. It includes:

- UIHandler: Protocol defining the UI interface
- UIBridge: Event dispatcher bridging events to UI methods
- InteractiveUIHandler: Interactive terminal UI using prompt_toolkit and Rich
- BatchUIHandler: Non-interactive UI using stdin/stdout/stderr
"""

from yoker.ui.batch import BatchUIHandler
from yoker.ui.bridge import UIBridge
from yoker.ui.handler import UIHandler
from yoker.ui.interactive import InteractiveUIHandler
from yoker.ui.spinner import LiveDisplay, live_display

__all__ = [
  "UIHandler",
  "UIBridge",
  "InteractiveUIHandler",
  "BatchUIHandler",
  "LiveDisplay",
  "live_display",
]
