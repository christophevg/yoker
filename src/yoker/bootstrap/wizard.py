"""BootstrapWizard — the interactive first-run flow (MBI-002 tasks 2.2-2.5).

The wizard is async (yoker is async-first) and consumes a
:class:`yoker.ui.handler.UIHandler` for all IO. It performs no direct
``print()``. In batch / non-interactive mode the wizard is **not**
instantiated; :mod:`yoker.__main__` emits the approved warning and exits.

Flow (see ``analysis/bootstrap-wizard-design.md``):

  Step 0  welcome            — explain yoker
  Step 1  offer guided/manual
  Step 2  backend intro      — Ollama, free tier (no fake choice)
  Step 3  account check      — no -> open docs URL + wait, resume
  Step 4  connection method — ollama app (no key) vs API key (masked)
  Step 5  model selection    — curated list / default / free text
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
  WizardAbort,
  step_account_check,
  step_backend_intro,
  step_confirm,
  step_connection_method,
  step_manual,
  step_model_selection,
  step_offer_guided_manual,
  step_welcome,
)
from yoker.config import Config
from yoker.config.writer import write_config
from yoker.ui.handler import UIHandler


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
      # Step 1 — explain yoker.
      await step_welcome(self._ui)

      # Step 2 — report no config found; offer guided vs manual vs abort.
      choice = await step_offer_guided_manual(self._ui)
      if choice == "manual":
        await step_manual(self._ui, self._config, self._config_path)
        return BootstrapResult.MANUAL

      # Step 3 — backend intro (Ollama, free tier; no choice).
      await step_backend_intro(self._ui)

      # Step 4 — ollama account check (may open a browser, then resume).
      await step_account_check(self._ui)

      # Step 5 — connection method (app vs API key vs abort).
      connection = await step_connection_method(self._ui)

      # Step 6 — model selection (curated list / default / free text).
      model = await step_model_selection(self._ui, self._config)

      # Step 7 — render ~/.yoker.toml with the collected overrides and write it.
      overrides: dict[str, Any] = {"backend.ollama.model": model}
      if connection.use_api_key and connection.api_key:
        # API key is stored ONLY in ~/.yoker.toml; writer sets chmod 600.
        overrides["backend.ollama.api_key"] = connection.api_key
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

      await step_confirm(self._ui, self._config_path)
      return BootstrapResult.WRITTEN
    except (WizardAbort, KeyboardInterrupt):
      # Clean abort: never a silent fall-through to manual setup. No file is
      # written; __main__ exits cleanly.
      self._ui.output_info("Aborted. No configuration written.\n")
      return BootstrapResult.ABORTED


__all__ = ["BootstrapResult", "BootstrapWizard"]
