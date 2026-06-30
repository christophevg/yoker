"""Individual wizard step functions (MBI-002 tasks 2.2, 2.3, 2.4).

Each step is a small async coroutine that performs pure IO through a
:class:`yoker.ui.handler.UIHandler`. Per the owner's PR #34 directive, these
are **not** unit-tested — they are pure user interaction; testing is
user-driven.

UX refinements applied (PR #34 follow-up):
  - The wizard appears ONLY because no yoker config was found. That reason is
    stated in the first step, which also asks IF the user wants to configure
    yoker now and offers a documentation link.
  - The "Step N of M: Title" line is rendered through
    :meth:`UIHandler.output_step_title`, which interactive handlers render
    with visual emphasis (bold + underline) and which emits a leading blank
    line for every step after the first so the flow feels lighter.
  - The wizard never forces a browser open. Whenever it wants to send the
    user to a documentation page, it shows the URL, proposes opening it, and
    only calls :func:`webbrowser.open` after an explicit yes from the user.
    It then waits for the user to return before resuming.

Multi-Provider Flow (6 steps in the guided path):

  Step 1 of 6  opening         — explain yoker, state no config found, ask
                                  guided / manual / visit docs (Ctrl+C to
                                  interrupt at any time)
  Step 2 of 6  provider        — select provider (Ollama, OpenAI, Anthropic, Gemini)
  Step 3 of 6  account_check   — "do you have a <provider> account?"; no proposes
                                  to open the docs guide URL (no force), then
                                  resumes; the wizard never aborts here
  Step 4 of 6  authentication  — provider-specific auth (API key vs app)
  Step 5 of 6  model_select    — curated list / accept default / free text
  Step 6 of 6  confirm         — written confirmation that config was created
                                  and yoker is continuing into the session

Other UX rules (carried over from the first iteration):
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

from yoker.bootstrap.modellist import curated_models_for_provider, default_model_for_provider
from yoker.bootstrap.providers import (
  PROVIDER_ORDER,
  ProviderInfo,
  get_default_provider,
  get_provider_info,
)
from yoker.config import Config
from yoker.config.writer import render_config_toml
from yoker.ui.handler import UIHandler

# Docs guide URL (legacy, kept for backward compatibility).
DOCS_GUIDE_URL = "https://yoker.readthedocs.io/en/latest/guides/getting-started-with-ollama.html"
DOCS_GUIDE_ACCOUNT_URL = f"{DOCS_GUIDE_URL}#account"
DOCS_GUIDE_API_KEY_URL = f"{DOCS_GUIDE_URL}#api-key"
# End-user getting-started page (authored at
# docs/guides/getting-started-with-yoker.md). The wizard deep-links here from
# the opening step and the manual-setup path so first-time users land on a
# page that describes Yoker for end-users (not the bare readthedocs landing).
DOCS_HOME_URL = "https://yoker.readthedocs.io/en/latest/guides/getting-started-with-yoker.html"

# Total number of steps in the guided path. Used for the progress indicator
# ("Step N of TOTAL_STEPS"). The manual path exits at step 1.
TOTAL_STEPS = 6


class WizardAbort(Exception):
  """Raised by a step when the user interrupts the wizard (Ctrl+C / EOF).

  The wizard catches this and exits cleanly with no file written, after
  emitting a brief abort message. It is never raised as a silent fall-through
  to manual setup.
  """


@dataclass(frozen=True)
class ConnectionChoice:
  """Result of the Step 4 authentication choice.

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


async def _open_docs_confirmed(ui: UIHandler, url: str, *, blurb: str = "") -> None:
  """Propose opening a documentation URL; only open it after the user confirms.

  Never forces a browser open. Shows the URL (and an optional one-line blurb
  describing what the page covers), asks the user whether to open it in their
  browser (default yes), opens it on yes, then waits for the user to return
  (press Enter). On EOF/Ctrl+C while waiting, raises :class:`WizardAbort`.

  The "Press Enter to continue" pause is only shown when the browser was
  actually opened (the user confirmed). When the user declines ("n"), the
  wizard proceeds straight to the next prompt — the pause is redundant when
  the very next interaction is itself a question (e.g. "Paste your ollama
  API key:").

  Args:
    ui: The UI handler used for all IO.
    url: The documentation URL to (propose to) open.
    blurb: Optional one-line description of what the page covers.
  """
  lines = [f"  {url}"]
  if blurb:
    lines.append(blurb)
  lines.append("")
  ui.output_info("\n".join(lines))
  open_it = await _ask_yes_no(ui, "Open this in your browser?", default=True)
  if not open_it:
    # User declined: no browser was opened, so there is nothing to come back
    # from. Skip the "Press Enter" wait and proceed straight to the next
    # prompt.
    return
  try:
    webbrowser.open(url)
  except webbrowser.Error:
    # Could not launch a browser; the URL is already shown above.
    ui.output_info("Could not launch a browser; open the URL above manually.\n")
  cont = await ui.get_input("Press Enter when you're ready to continue... ")
  if cont is None:
    # EOF / Ctrl+C while waiting: explicit abort.
    raise WizardAbort


async def step_opening(ui: UIHandler) -> str:
  """Step 1: explain yoker, state that no config was found, and ask what to do.

  The wizard only appears because no yoker configuration was found at
  ``~/.yoker.toml`` — that reason is stated here, alongside a link to the
  documentation so users who want to read first can visit it. The user is then
  asked whether they want to configure yoker now.

  Returns:
    ``"guided"`` or ``"manual"``.

  Raises:
    WizardAbort: When the user sends EOF/Ctrl+C (the wizard no longer offers
      an explicit abort option; Ctrl+C interrupts at any time), or sends
      EOF/Ctrl+C while waiting to return from the docs.
  """
  await ui.output_step_title(1, TOTAL_STEPS, "Welcome")
  ui.output_info(
    "Welcome to yoker — a provider-neutral AI backend for running agentic "
    "workflows.\nyoker connects to model providers and gives "
    "your tools, skills,\nand agents a single place to run.\n\n"
    "No yoker configuration was found at ~/.yoker.toml — that's why this "
    "wizard is showing.\n"
    f"Docs: {DOCS_HOME_URL}\n\n"
    "Would you like to configure yoker now?\n"
    "  1) Guided setup (recommended) — I'll ask a few questions and write "
    "the config for you.\n"
    "  2) Manual setup — I'll print a config skeleton and a docs link, and "
    "you author ~/.yoker.toml yourself.\n"
    "  3) Visit the documentation first — I'll open the docs in your "
    "browser, then come back here.\n\n"
    "Ctrl+c interrupts the setup at any time, without writing anything.\n"
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
      # Propose opening the docs, wait for the user to return, then re-ask.
      await _open_docs_confirmed(
        ui,
        DOCS_HOME_URL,
        blurb="The docs cover getting started with yoker and configuring providers.",
      )
      # Loop back and re-ask the opening question.
      continue
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


async def step_provider_selection(ui: UIHandler) -> ProviderInfo:
  """Step 2: Select provider from available options.

  Shows a list of available providers and lets the user select one.
  Default is Ollama (option 1) for backward compatibility.

  Returns:
    ProviderInfo for the selected provider.

  Raises:
    WizardAbort: When the user sends EOF/Ctrl+C.
  """
  await ui.output_step_title(2, TOTAL_STEPS, "Select Provider")
  lines = ["Choose your preferred LLM provider:\n"]
  for idx, provider_id in enumerate(PROVIDER_ORDER, start=1):
    provider = get_provider_info(provider_id)
    lines.append(f"  {idx}) {provider.display_name} — {provider.description}")
  lines.append("\nCtrl+c interrupts the setup at any time, without writing anything.\n")
  ui.output_info("\n".join(lines))

  default_provider = get_default_provider()
  while True:
    raw = await ui.get_input(
      f"Choose [1-{len(PROVIDER_ORDER)}] (Enter = 1 {default_provider.display_name}): "
    )
    if raw is None:
      raise WizardAbort
    answer = raw.strip()
    if answer == "":
      return default_provider
    if answer.isdigit():
      n = int(answer)
      if 1 <= n <= len(PROVIDER_ORDER):
        return get_provider_info(PROVIDER_ORDER[n - 1])
    ui.output_info(f"Invalid choice. Enter a number from 1 to {len(PROVIDER_ORDER)}.\n")


async def step_account_check_provider(ui: UIHandler, provider: ProviderInfo) -> None:
  """Step 3: Check if user has an account for the selected provider.

  No -> PROPOSE opening the getting-started guide in the browser (the user
  confirms; nothing is forced), wait for the user to return, then resume.
  The wizard does not abort on "no" — it helps the user get set up. EOF /
  Ctrl+C at the yes/no or the "press Enter to continue" prompt is an explicit
  abort.

  The default is "no" since the wizard targets first-time users who typically
  do not yet have an account; pressing Enter proposes to open the
  getting-started guide.

  Args:
    ui: The UI handler.
    provider: The selected provider info.
  """
  has_account = await _ask_yes_no(
    ui, f"Do you have a {provider.display_name} account?", default=False
  )
  if has_account:
    return
  await _open_docs_confirmed(
    ui,
    provider.account_url,
    blurb=f"The guide covers creating a {provider.display_name} account.",
  )


async def step_authentication(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Step 4: Collect authentication credentials for the provider.

  For Ollama: offer app vs API key choice.
  For others (OpenAI/Anthropic/Gemini): collect API key only.

  Args:
    ui: The UI handler.
    provider: The selected provider info.

  Returns:
    ConnectionChoice with auth details.

  Raises:
    WizardAbort: When the user sends EOF/Ctrl+C.
  """
  if provider.has_local_app:
    # Ollama: offer app vs API key choice
    return await _collect_ollama_auth(ui, provider)
  else:
    # OpenAI/Anthropic/Gemini: collect API key only
    return await _collect_api_key(ui, provider)


async def _collect_ollama_auth(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Collect Ollama authentication (app or API key)."""
  await ui.output_step_title(4, TOTAL_STEPS, "Connection Method")
  ui.output_info(
    "Connect via:\n"
    "  1) The Ollama app running locally (recommended — no key needed)\n"
    "  2) An Ollama API key\n\n"
    "Ctrl+c interrupts the setup at any time, without writing anything.\n"
  )

  while True:
    raw = await ui.get_input("Choose [1/2] (Enter = 1 app): ")
    if raw is None:
      raise WizardAbort
    answer = raw.strip()
    if answer == "" or answer == "1":
      return ConnectionChoice(use_api_key=False)
    if answer == "2":
      break
    ui.output_info("Invalid choice. Enter 1 or 2 (or press Enter for the app).\n")

  # API-key path: propose opening the key-creation guide (no force), wait,
  # then prompt for the key.
  if provider.api_key_url:
    await _open_docs_confirmed(
      ui,
      provider.api_key_url,
      blurb=f"The guide walks through creating a {provider.display_name} API key.",
    )
  key = await ui.get_secret_input("Paste your Ollama API key: ")
  api_key = key.strip() if key else None
  if not api_key:
    ui.output_info("No key entered. Falling back to the Ollama app path.\n")
    return ConnectionChoice(use_api_key=False)
  return ConnectionChoice(use_api_key=True, api_key=api_key)


async def _collect_api_key(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Collect API key for providers that require it."""
  await ui.output_step_title(4, TOTAL_STEPS, "API Key")

  # Check if user has an API key
  has_key = await _ask_yes_no(ui, f"Do you have a {provider.display_name} API key?", default=False)

  if not has_key and provider.api_key_url:
    await _open_docs_confirmed(
      ui,
      provider.api_key_url,
      blurb=f"The guide walks through creating a {provider.display_name} API key.",
    )

  # Collect the key
  key = await ui.get_secret_input(f"Paste your {provider.display_name} API key: ")
  api_key = key.strip() if key else None

  if not api_key:
    ui.output_info("No key entered. You can set the API key later in your config.\n")
    return ConnectionChoice(use_api_key=False)

  return ConnectionChoice(use_api_key=True, api_key=api_key)


async def step_model_selection_provider(ui: UIHandler, provider: ProviderInfo) -> str:
  """Step 5: Select a model from the provider's curated list.

  Args:
    ui: The UI handler.
    provider: The selected provider info.

  Returns:
    The chosen model id (never empty — falls back to the default).

  Raises:
    WizardAbort: When the user sends EOF/Ctrl+C at the main choice prompt.
  """
  models = curated_models_for_provider(provider.id)
  default_id = default_model_for_provider(provider.id)

  await ui.output_step_title(5, TOTAL_STEPS, "Model Selection")
  lines = ["Pick a model, or accept the default:"]
  for idx, model in enumerate(models, start=1):
    lines.append(f"  {idx}) {model.label} — {model.note}")
  lines.append(f"  {len(models) + 1}) Enter a model id by hand")
  lines.append("")
  ui.output_info("\n".join(lines))

  while True:
    raw = await ui.get_input(f"Choose [1-{len(models) + 1}] (Enter = default): ")
    if raw is None:
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
          raise WizardAbort
        if custom.strip():
          return custom.strip()
        ui.output_info("No model entered; using default.\n")
        return default_id
    ui.output_info("Invalid choice.\n")


async def step_confirm_provider(
  ui: UIHandler, provider: ProviderInfo, model: str, config_path: Path
) -> None:
  """Step 6: Confirm config was created."""
  await ui.output_step_title(6, TOTAL_STEPS, "Configuration Created")
  ui.output_info(
    f"Configuration written to {config_path} (chmod 600).\n"
    f"Provider: {provider.display_name}\n"
    f"Model: {model}\n"
    "yoker is continuing into the normal session now.\n"
  )


# Legacy functions for backward compatibility


async def step_backend_intro(ui: UIHandler) -> None:
  """Step 2 (legacy): short informational panel about the backend (no choice).

  DEPRECATED: Use step_provider_selection instead.
  """
  await ui.output_step_title(2, TOTAL_STEPS, "Backend")
  ui.output_info(
    "Today yoker supports Ollama as the model-neutral provider. Ollama has a "
    "free tier you can use to explore yoker and agentic workflows at no "
    "cost.\nOther backends will be added in the future.\n"
  )


async def step_account_check(ui: UIHandler) -> None:
  """Step 3 (legacy): 'Do you have an ollama account?'

  DEPRECATED: Use step_account_check_provider instead.
  """
  has_account = await _ask_yes_no(ui, "Do you have an ollama account?", default=False)
  if has_account:
    return
  await _open_docs_confirmed(
    ui,
    DOCS_GUIDE_ACCOUNT_URL,
    blurb=("The guide covers creating an ollama account and installing the local app/proxy."),
  )


async def step_connection_method(ui: UIHandler) -> ConnectionChoice:
  """Step 4 (legacy): split choice — ollama app (no key) vs API key vs abort.

  DEPRECATED: Use step_authentication instead.
  """
  await ui.output_step_title(4, TOTAL_STEPS, "Connection Method")
  ui.output_info(
    "Connect via:\n"
    "  1) The ollama app running locally (recommended — no key needed)\n"
    "  2) An ollama API key\n\n"
    "Ctrl+c interrupts the setup at any time, without writing anything.\n"
  )
  while True:
    raw = await ui.get_input("Choose [1/2] (Enter = 1 app): ")
    if raw is None:
      raise WizardAbort
    answer = raw.strip()
    if answer == "":
      return ConnectionChoice(use_api_key=False)
    if answer == "1":
      return ConnectionChoice(use_api_key=False)
    if answer == "2":
      break
    ui.output_info("Invalid choice. Enter 1 or 2 (or press Enter for the app).\n")
  await _open_docs_confirmed(
    ui,
    DOCS_GUIDE_API_KEY_URL,
    blurb="The guide walks through creating an ollama API key from your account.",
  )
  key = await ui.get_secret_input("Paste your ollama API key: ")
  api_key = key.strip() if key else None
  if not api_key:
    ui.output_info("No key entered. Falling back to the ollama app path.\n")
    return ConnectionChoice(use_api_key=False)
  return ConnectionChoice(use_api_key=True, api_key=api_key)


async def step_model_selection(ui: UIHandler, config: Config) -> str:
  """Step 5 (legacy): pick a model from the curated list, accept the default, or free text.

  DEPRECATED: Use step_model_selection_provider instead.
  """
  from yoker.bootstrap.modellist import curated_models, default_model_id

  models = curated_models(config)
  default_id = default_model_id(config)
  await ui.output_step_title(5, TOTAL_STEPS, "Model Selection")
  lines = ["Pick a model, or accept the default:"]
  for idx, model in enumerate(models, start=1):
    lines.append(f"  {idx}) {model.label} — {model.note}")
  lines.append(f"  {len(models) + 1}) Enter a model id by hand")
  lines.append("")
  ui.output_info("\n".join(lines))

  while True:
    raw = await ui.get_input(f"Choose [1-{len(models) + 1}] (Enter = default): ")
    if raw is None:
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
          raise WizardAbort
        if custom.strip():
          return custom.strip()
        ui.output_info("No model entered; using default.\n")
        return default_id
    ui.output_info("Invalid choice.\n")


async def step_confirm(ui: UIHandler, config_path: Path) -> None:
  """Step 6 (legacy): confirm that config was created and yoker is continuing.

  DEPRECATED: Use step_confirm_provider instead.
  """
  await ui.output_step_title(6, TOTAL_STEPS, "Configuration Created")
  ui.output_info(
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
  # New multi-provider steps
  "step_opening",
  "step_manual",
  "step_provider_selection",
  "step_account_check_provider",
  "step_authentication",
  "step_model_selection_provider",
  "step_confirm_provider",
  # Legacy steps (deprecated but kept for backward compatibility)
  "step_backend_intro",
  "step_account_check",
  "step_connection_method",
  "step_model_selection",
  "step_confirm",
]
