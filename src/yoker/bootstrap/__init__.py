"""Bootstrap package for Yoker.

Holds the first-run bootstrap logic triggered when no user configuration is
found:

  - :func:`config_provided` (task 2.1) — boolean detection.
  - :class:`BootstrapWizard` and :class:`BootstrapResult` (tasks 2.2-2.5) —
    the interactive wizard. Pure IO through :class:`UIHandler`; not unit
    tested (user-driven testing per owner PR #34 point 3).
  - :mod:`yoker.bootstrap.modellist` — curated model list (task 2.4).
  - :mod:`yoker.bootstrap.providers` — provider metadata and registry.

The config writer (task 2.5) lives in the config module
(:mod:`yoker.config.writer`) and is called by the wizard; it is not owned
by this package.
"""

from yoker.bootstrap.detect import config_provided
from yoker.bootstrap.modellist import (
  CuratedModel,
  curated_models,
  curated_models_for_provider,
  default_model_for_provider,
  default_model_id,
)
from yoker.bootstrap.providers import (
  PROVIDER_ORDER,
  PROVIDERS,
  ProviderInfo,
  get_curated_models,
  get_default_model,
  get_default_provider,
  get_provider_info,
)
from yoker.bootstrap.wizard import BootstrapResult, BootstrapWizard, build_bootstrap_overrides

__all__ = [
  # Wizard
  "BootstrapResult",
  "BootstrapWizard",
  "build_bootstrap_overrides",
  # Detection
  "config_provided",
  # Provider metadata
  "ProviderInfo",
  "PROVIDERS",
  "PROVIDER_ORDER",
  "get_provider_info",
  "get_default_provider",
  "get_curated_models",
  "get_default_model",
  # Model lists
  "CuratedModel",
  "curated_models",
  "default_model_id",
  "curated_models_for_provider",
  "default_model_for_provider",
]
