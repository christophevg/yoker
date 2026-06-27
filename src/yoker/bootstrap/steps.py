"""Individual wizard step functions (MBI-002 tasks 2.2, 2.3, 2.4).

Each step is a small async coroutine that performs pure IO through a
:class:`yoker.ui.handler.UIHandler`. Per the owner's PR #34 directive, these
are **not** unit-tested — they are pure user interaction; testing is
user-driven.

The steps are intentionally lean (least-possible steps principle). The flow
(seven steps in the guided path):

  Step 1 of 7  welcome          — explain what yoker is
  Step 2 of 7  offer_guided     — guided (recommended) vs manual vs abort;
                                  manual prints a skeleton + docs link and
                                  signals "no write"
  Step 3 of 7  backend_intro    — single supported backend today (Ollama, free tier)
  Step 4 of 7  account_check    — "do you have an ollama account?"; no opens the
                                  docs guide URL in the browser and waits, then
                                  resumes; the wizard never aborts here
  Step 5 of 7  connection       — split: ollama app (no key) vs API key (masked)
                                  vs abort
  Step 6 of 7  model_select     — curated list / accept default / free text
  Step 7 of 7  confirm          — written confirmation that config was created
                                  and yoker is continuing into the session

UX refinements (PR #34 feedback):
  - Each step emits a title with a progress indicator ("Step N of 7: Title").
  - The recommended/default option is pre-selected so Enter accepts it.
  - Invalid input re-prompts with feedback instead of silently falling through.
  - Ctrl+C / EOF (``get_input`` returns None) is an explicit, clean abort —
    never a silent fall-through to manual setup. Steps raise :class:`WizardAbort`
    on abort; the wizard catches it and exits cleanly with no file written.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path

from yoker.bootstrap.modellist import curated_models, default_model_id
from yoker.config import Config
from yoker.config.writer import render_config_toml
from yoker.ui.handler import UIHandler

# Docs guide URL. The dedicated guide is authored on the docs site (task 2.7);
# the wizard deep-links to its anchors. The path follows the readthedocs
# convention used elsewhere in the project.
DOCS_GUIDE_URL = "https://yoker.readthedocs.io/en/latest/guides/getting-started-with-ollama.html"
DOCS_GUIDE_ACCOUNT_URL = f"{DOCS_GUIDE_URL}#account"
DOCS_GUIDE_API_KEY_URL = f"{DOCS_GUIDE_URL}#api-key"
DOCS_HOME_URL = "https://yoker.readthedocs.io/"

# Total number of steps in the guided path. Used for the progress indicator
# ("Step N of TOTAL_STEPS"). The manual path exits at step 2.
TOTAL_STEPS = 7


class WizardAbort(Exception):
  """Raised by a step when the user chooses to abort (Ctrl+C / EOF / "abort").

  The wizard catches this and exits cleanly with no file written, after
  emitting a brief abort message. It is never raised as a silent fall-through
  to manual setup.
  """


def _title(n: int, title: str) -> str:
  """Build a step title line with a progress indicator."""
  return f"Step {n} of {TOTAL_STEPS}: {title}"


@dataclass(frozen=True)
class ConnectionChoice:
  """Result of the Step 5 connection-method choice.

  Attributes:
    use_api_key: Whether the user chose the API-key path.
    api_key: The collected API key (only set when ``use_api_key`` is True).
      Never echoed or logged by the caller beyond this struct.
  """

  use_api_key: bool
  api_key: str | None = None


async def _ask_yes_no(ui: UIHandler, prompt: str, *, default: bool = False) -> bool:
  """Ask a yes/no question via ``ui`` and return ``True`` for yes.

  Accepts y/yes (any case) as yes and n/no as no. Empty input (Enter) accepts
  the ``default``. Re-prompts on unrecognized (non-empty) input. ``None``
  (EOF) raises :class:`WizardAbort` so the user can abort cleanly.
  """
  default_hint = "Y" if default else "N"
  while True:
    raw = await ui.get_input(f"{prompt} [y/n] (Enter = {default_hint}): ")
    if raw is None:
      # EOF: treat as an explicit abort, not a silent default.
      raise WizardAbort
    answer = raw.strip().lower()
    if answer == "":
      return default
    if answer in ("y", "yes"):
      return True
    if answer in ("n", "no"):
      return False
    ui.output_info("Please answer 'y' or 'n' (or press Enter for the default).\n")


async def step_welcome(ui: UIHandler) -> None:
  """Step 1: explain what yoker is (2-3 lines)."""
  ui.output_info(
    f"{_title(1, 'Welcome')}\n"
    "Welcome to yoker — a provider-neutral AI backend for running agentic "
    "workflows.\nyoker connects to model providers (today: Ollama) and gives "
    "your tools, skills,\nand agents a single place to run.\n"
  )


async def step_offer_guided_manual(ui: UIHandler) -> str:
  """Step 2: report no config found and offer guided vs manual vs abort.

  Returns:
    ``"guided"`` or ``"manual"``.

  Raises:
    WizardAbort: When the user chooses abort (option 3) or sends EOF/Ctrl+C.
  """
  ui.output_info(
    f"{_title(2, 'Setup')}\n"
    "No yoker configuration was found at ~/.yoker.toml.\n"
    "You can set things up two ways:\n"
    "  1) Guided setup (recommended) — I'll ask a few questions and write "
    "the config for you.\n"
    "  2) Manual setup — I'll print a config skeleton and a docs link, and "
    "you author ~/.yoker.toml yourself.\n"
    "  3) Abort — exit now without writing anything.\n"
  )
  while True:
    raw = await ui.get_input("Choose [1/2/3] (Enter = 1 guided): ")
    if raw is None:
      # EOF / Ctrl+C: explicit abort, never a silent fall-through to manual.
      raise WizardAbort
    answer = raw.strip()
    if answer == "":
      # Enter accepts the recommended default (guided).
      return "guided"
    if answer == "1":
      return "guided"
    if answer == "2":
      return "manual"
    if answer == "3":
      raise WizardAbort
    ui.output_info("Invalid choice. Enter 1, 2, or 3 (or press Enter for guided).\n")


async def step_manual(ui: UIHandler, config: Config, config_path: Path) -> None:
  """Manual path: print a config skeleton + docs link, write nothing."""
  skeleton = render_config_toml(config)
  ui.output_info(
    f"Manual setup selected. Write the following to {config_path} "
    f"(or ./yoker.toml for a project-level config):\n"
    f"----- begin {config_path.name} -----\n"
    f"{skeleton}"
    f"----- end {config_path.name} -----\n"
    f"Docs: {DOCS_HOME_URL}\n"
    f"No file was written. Re-run `yoker` once you've authored your config.\n"
  )


async def step_backend_intro(ui: UIHandler) -> None:
  """Step 3: short informational panel about the backend (no choice)."""
  ui.output_info(
    f"{_title(3, 'Backend')}\n"
    "Today yoker supports Ollama as the model-neutral provider. Ollama has a "
    "free tier you can use to explore yoker and agentic workflows at no "
    "cost.\nOther backends will be added in the future.\n"
  )


async def step_account_check(ui: UIHandler) -> None:
  """Step 4: 'Do you have an ollama account?'

  No -> open the docs guide URL in the browser, offer to wait, then resume.
  The wizard does not abort on "no" — it helps the user get set up. EOF /
  Ctrl+C at the yes/no or the "press Enter to continue" prompt is an explicit
  abort.

  The default is "no" since the wizard targets first-time users who typically
  do not yet have an ollama account; pressing Enter opens the getting-started
  guide.
  """
  has_account = await _ask_yes_no(ui, "Do you have an ollama account?", default=False)
  if has_account:
    return
  ui.output_info(
    f"Opening the getting-started guide in your browser:\n  {DOCS_GUIDE_ACCOUNT_URL}\n"
    "The page covers creating an ollama account and installing the local "
    "app/proxy.\nWhen you're ready, come back here and we'll continue.\n"
  )
  try:
    webbrowser.open(DOCS_GUIDE_ACCOUNT_URL)
  except webbrowser.Error:
    # Could not launch a browser; the URL is already shown above.
    ui.output_info("Could not launch a browser; open the URL above manually.\n")
  cont = await ui.get_input("Press Enter when you're ready to continue... ")
  if cont is None:
    # EOF / Ctrl+C while waiting: explicit abort.
    raise WizardAbort


async def step_connection_method(ui: UIHandler) -> ConnectionChoice:
  """Step 5: split choice — ollama app (no key) vs API key vs abort.

  Uses the locked wording from the design doc (app-first, key-second). The
  recommended option 1 (ollama app) is the default — Enter accepts it.

  Raises:
    WizardAbort: When the user chooses abort (option 3) or sends EOF/Ctrl+C.
  """
  ui.output_info(
    f"{_title(5, 'Connection Method')}\n"
    "Connect via:\n"
    "  1) The ollama app running locally (recommended — no key needed)\n"
    "  2) An ollama API key\n"
    "  3) Abort — exit now without writing anything.\n"
  )
  while True:
    raw = await ui.get_input("Choose [1/2/3] (Enter = 1 app): ")
    if raw is None:
      # EOF / Ctrl+C: explicit abort, never a silent fall-through to the app.
      raise WizardAbort
    answer = raw.strip()
    if answer == "":
      # Enter accepts the recommended default (ollama app).
      return ConnectionChoice(use_api_key=False)
    if answer == "1":
      return ConnectionChoice(use_api_key=False)
    if answer == "2":
      break
    if answer == "3":
      raise WizardAbort
    ui.output_info("Invalid choice. Enter 1, 2, or 3 (or press Enter for the app).\n")
  ui.output_info(
    f"You can create an API key from your ollama account; see:\n  {DOCS_GUIDE_API_KEY_URL}\n"
  )
  key = await ui.get_secret_input("Paste your ollama API key: ")
  api_key = key.strip() if key else None
  if not api_key:
    ui.output_info("No key entered. Falling back to the ollama app path.\n")
    return ConnectionChoice(use_api_key=False)
  return ConnectionChoice(use_api_key=True, api_key=api_key)


async def step_model_selection(ui: UIHandler, config: Config) -> str:
  """Step 6: pick a model from the curated list, accept the default, or free text.

  Returns:
    The chosen model id (never empty — falls back to the default).

  Raises:
    WizardAbort: When the user sends EOF/Ctrl+C at the main choice prompt.
  """
  models = curated_models(config)
  default_id = default_model_id(config)
  lines = [_title(6, "Model Selection"), "Pick a model, or accept the default:"]
  for idx, model in enumerate(models, start=1):
    lines.append(f"  {idx}) {model.label} — {model.note}")
  lines.append(f"  {len(models) + 1}) Enter a model id by hand")
  lines.append("")
  ui.output_info("\n".join(lines))

  while True:
    raw = await ui.get_input(f"Choose [1-{len(models) + 1}] (Enter = default): ")
    if raw is None:
      # EOF / Ctrl+C: explicit abort.
      raise WizardAbort
    answer = raw.strip()
    if answer == "":
      ui.output_info("No model entered; using default.\n")
      return default_id
    if answer.isdigit():
      n = int(answer)
      if 1 <= n <= len(models):
        return models[n - 1].model_id
      if n == len(models) + 1:
        custom = await ui.get_input("Model id: ")
        if custom is None:
          # EOF at the free-text prompt: abort rather than silently default.
          raise WizardAbort
        if custom.strip():
          return custom.strip()
        ui.output_info("No model entered; using default.\n")
        return default_id
    ui.output_info("Invalid choice.\n")
    # Unrecognized: re-ask.


async def step_confirm(ui: UIHandler, config_path: Path) -> None:
  """Step 7: confirm that config was created and yoker is continuing."""
  ui.output_info(
    f"{_title(7, 'Configuration Created')}\n"
    f"Configuration written to {config_path} (chmod 600).\n"
    "yoker is continuing into the normal session now — you don't need to "
    "re-run anything.\n"
  )


__all__ = [
  "ConnectionChoice",
  "DOCS_GUIDE_URL",
  "DOCS_GUIDE_ACCOUNT_URL",
  "DOCS_GUIDE_API_KEY_URL",
  "DOCS_HOME_URL",
  "TOTAL_STEPS",
  "WizardAbort",
  "step_welcome",
  "step_offer_guided_manual",
  "step_manual",
  "step_backend_intro",
  "step_account_check",
  "step_connection_method",
  "step_model_selection",
  "step_confirm",
]
