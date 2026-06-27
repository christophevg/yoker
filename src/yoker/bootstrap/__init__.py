"""Bootstrap package for Yoker.

Holds the wizard-side code triggered when no user configuration is found.
The detection function :func:`config_provided` lives here; the interactive
wizard (tasks 2.2-2.4) and the config writer (task 2.5, in the config module)
are upcoming additions.
"""

from yoker.bootstrap.detect import config_provided

__all__ = ["config_provided"]
