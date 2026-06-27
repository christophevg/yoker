"""Bootstrap package for Yoker.

Holds the first-run bootstrap logic triggered when no user configuration is
found:

  - :func:`config_provided` (task 2.1) — boolean detection.
  - :class:`BootstrapWizard` and :class:`BootstrapResult` (tasks 2.2-2.5) —
    the interactive wizard. Pure IO through :class:`UIHandler`; not unit
    tested (user-driven testing per owner PR #34 point 3).
  - :mod:`yoker.bootstrap.modellist` — curated model list (task 2.4).

The config writer (task 2.5) lives in the config module
(:mod:`yoker.config.writer`) and is called by the wizard; it is not owned
by this package.
"""

from yoker.bootstrap.detect import config_provided
from yoker.bootstrap.wizard import BootstrapResult, BootstrapWizard

__all__ = ["BootstrapResult", "BootstrapWizard", "config_provided"]
