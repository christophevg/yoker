"""BootstrapWizard — the interactive first-run flow (MBI-002 tasks 2.2-2.5).

The wizard is async (yoker is async-first) and consumes a
:class:`yoker.ui.handler.UIHandler` for all IO. It performs no direct
``print()``. In batch / non-interactive mode the wizard is **not**
instantiated; :mod:`yoker.__main__` emits the approved warning and exits.

Multi-Provider Flow (see ``analysis/bootstrap-multi-provider-design.md``):

  Step 1  opening            — explain yoker, state no config found, ask
                                guided / manual / visit docs / abort
  Step 2  provider selection — select from available providers
  Step 3  account check      — provider-specific account check
  Step 4  authentication     — provider-specific auth (API key vs app)
  Step 5  model selection    — provider-specific curated models
  Step 6  generate ~/.yoker.toml (chmod 600) and return so __main__ continues

The wizard returns a :class:`BootstrapResult` so ``__main__.py`` can decide
whether to continue into the normal Agent session (``WRITTEN``) or exit
cleanly (``MANUAL``, no file written).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from yoker.bootstrap.steps import (
  ConnectionChoice,
  WizardAbort,
  step_account_check_provider,
  step_authentication,
  step_confirm_provider,
  step_manual,
  step_model_selection_provider,
  step_opening,
  step_provider_selection,
)
from yoker.config import Config
from yoker.config.writer import write_config
from yoker.ui.handler import UIHandler

# Ollama's cloud API endpoint. When the user selects the API-key connection
# method (Step 4, option 2) they are explicitly choosing to connect to
# Ollama's cloud-hosted models without running the local app/proxy, so the
# wizard overrides ``base_url`` away from ``http://localhost:11434`` and
# points the client straight at the cloud API. This is the documented
# endpoint for Ollama's cloud-hosted API; if it changes, update it here
# (and only here).
OLLAMA_CLOUD_BASE_URL = "https://api.ollama.com"


def build_bootstrap_overrides(
  provider: str,
  model: str,
  connection: ConnectionChoice | None = None,
) -> dict[str, Any]:
  """Build the override dict passed to :func:`write_config` from wizard choices.

  This is a pure function (no IO) so it can be unit-tested independently of
  the wizard's UI flow.

  Args:
    provider: The provider identifier ('ollama', 'openai', 'anthropic', 'gemini').
    model: The chosen model id.
    connection: The authentication result (may have API key).

  Returns:
    A flat dotted-key override dict. Always sets ``backend.provider`` and
    ``backend.<provider>.model``. When an API key is provided, also sets
    ``backend.<provider>.api_key``. For Ollama API-key path, also sets
    ``backend.ollama.base_url`` to the cloud endpoint.
  """
  overrides: dict[str, Any] = {
    "backend.provider": provider,
    f"backend.{provider}.model": model,
  }

  if connection and connection.use_api_key and connection.api_key:
    # Store API key in config
    overrides[f"backend.{provider}.api_key"] = connection.api_key

    # For Ollama API-key path: point base_url to cloud endpoint
    if provider == "ollama":
      overrides["backend.ollama.base_url"] = OLLAMA_CLOUD_BASE_URL

  return overrides


class BootstrapResult(Enum):
  """Outcome of running the wizard.

  Attributes:
    WRITTEN: Config was written to ``~/.yoker.toml``; ``__main__`` should
      continue into the normal Agent session using the fresh config.
    MANUAL: The user chose manual setup; a skeleton was printed but no file
      was written. ``__main__`` should exit cleanly.
    ABORTED: The user chose to abort (Ctrl+C / EOF / explicit "abort"). No
      file was written; ``__main__`` should exit cleanly.
  """

  WRITTEN = "written"
  MANUAL = "manual"
  ABORTED = "aborted"


class BootstrapWizard:
  """Interactive first-run configuration wizard.

  All IO goes through the provided :class:`UIHandler`. The wizard never
  prints directly or exits the process. It writes ``~/.yoker.toml`` (chmod
  600) when guided setup completes, then returns ``BootstrapResult.WRITTEN``
  so the caller can continue into the normal session.
  """

  def __init__(
    self,
    ui: UIHandler,
    *,
    config: Config | None = None,
    config_path: Path | None = None,
  ) -> None:
    """Initialize the wizard.

    Args:
      ui: UI handler used for all input/output.
      config: Base config rendered into the TOML file. Defaults to
        :class:`Config()` (full defaults). The default model is read from
        this config so there is a single source of truth.
      config_path: Destination path. Defaults to ``~/.yoker.toml``.
    """
    self._ui = ui
    self._config = config if config is not None else Config()
    self._config_path = config_path if config_path is not None else Path.home() / ".yoker.toml"

  async def run(self) -> BootstrapResult:
    """Run the full wizard flow and return the outcome.

    Returns:
      :attr:`BootstrapResult.WRITTEN` if a config file was written
      (guided path completed); :attr:`BootstrapResult.MANUAL` if the user
      chose manual setup (no file written); :attr:`BootstrapResult.ABORTED`
      if the user chose to abort (Ctrl+C / EOF / explicit "abort"), in which
      case no file is written.
    """
    try:
      # Step 1 — explain yoker, state no config found, ask what to do.
      choice = await step_opening(self._ui)
      if choice == "manual":
        await step_manual(self._ui, self._config, self._config_path)
        return BootstrapResult.MANUAL

      # Step 2 — provider selection (Ollama, OpenAI, Anthropic, Gemini)
      provider = await step_provider_selection(self._ui)

      # Step 3 — provider-specific account check
      await step_account_check_provider(self._ui, provider)

      # Step 4 — provider-specific authentication
      connection = await step_authentication(self._ui, provider)

      # Step 5 — model selection from provider's curated list
      model = await step_model_selection_provider(self._ui, provider)

      # Step 6 — render ~/.yoker.toml with the collected overrides and write it.
      overrides = build_bootstrap_overrides(provider.id, model, connection)
      try:
        write_config(self._config, self._config_path, overrides=overrides)
      except OSError as e:
        self._ui.output_error(e)
        self._ui.output_info(
          f"Could not write {self._config_path}: {e}.\n"
          "Fix the issue (e.g. create the parent directory or adjust "
          "permissions) and re-run `yoker`.\n"
        )
        return BootstrapResult.MANUAL

      await step_confirm_provider(self._ui, provider, model, self._config_path)
      return BootstrapResult.WRITTEN
    except (WizardAbort, KeyboardInterrupt):
      # Clean abort: never a silent fall-through to manual setup. No file is
      # written; __main__ exits cleanly.
      self._ui.output_info("Aborted. No configuration written.\n")
      return BootstrapResult.ABORTED


__all__ = [
  "OLLAMA_CLOUD_BASE_URL",
  "BootstrapResult",
  "BootstrapWizard",
  "build_bootstrap_overrides",
]
