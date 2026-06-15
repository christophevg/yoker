"""Compatibility shim for LiveDisplay.

The LiveDisplay implementation has moved to the UI layer (yoker.ui.spinner).
This module re-exports the symbols for backward compatibility during the
UI separation migration. It will be removed in Phase 7.
"""

from yoker.ui.spinner import DEFAULT_REFRESH_RATE, LiveDisplay, live_display

__all__ = [
  "LiveDisplay",
  "live_display",
  "DEFAULT_REFRESH_RATE",
]
