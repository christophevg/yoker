# Multi-Provider Bootstrap Wizard Design

**Date**: 2026-06-30
**Task**: Extend bootstrap wizard to support multiple providers (OpenAI, Anthropic, Gemini, Ollama)
**Author**: Functional Analyst
**Related**: `analysis/bootstrap-wizard-design.md` (original single-provider design), `src/yoker/config/providers.py`

## Purpose

This document specifies how to extend the existing bootstrap wizard from Ollama-only support to a multi-provider system supporting Ollama, OpenAI, Anthropic, and Gemini. The design maintains the simplicity and user-friendliness of the existing wizard while accommodating provider-specific authentication flows and model selection.

## Design Goals

1. **Simplicity First**: Maintain the lean, guided flow established in the original wizard
2. **Provider Agnostic**: Abstract provider-specific logic into a dataclass-based metadata system
3. **Extensibility**: Make adding new providers straightforward (dataclass + curated models)
4. **User-Friendly**: Provide helpful guidance for each provider's authentication flow
5. **Security**: Properly handle API keys and sensitive credentials per provider

## Current State vs. Target State

### Current State (Ollama-only)

```
Step 1: Welcome
Step 2: Backend (informational only - "Today yoker supports Ollama")
Step 3: Account check (Ollama-specific)
Step 4: Connection method (Ollama app vs API key)
Step 5: Model selection (Ollama models)
Step 6: Confirm
```

### Target State (Multi-Provider)

```
Step 1: Welcome
Step 2: Provider Selection
Step 3: Provider-Specific Setup
   - Account check (provider-specific)
   - Authentication (provider-specific)
Step 4: Model Selection (provider-specific models)
Step 5: Confirm
```

**Key Insight**: The number of steps varies by provider:
- Ollama: 5 steps (can use app without API key)
- OpenAI/Anthropic/Gemini: 5 steps (API key required)

## ProviderInfo Dataclass

Centralize all provider metadata in a single dataclass for easy maintenance and extensibility.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ProviderInfo:
  """Metadata for a single LLM provider.

  Attributes:
    provider_id: Internal provider identifier (e.g., 'ollama', 'openai').
    display_name: Human-readable name shown in the wizard (e.g., 'Ollama').
    description: One-line description for provider selection step.
    requires_api_key: Whether an API key is required (False for Ollama app path).
    api_key_env_var: Environment variable name for the API key (e.g., 'OPENAI_API_KEY').
    account_setup_url: URL to create an account (deep-link to docs).
    api_key_creation_url: URL to create an API key (deep-link to docs).
    auth_method: Authentication method ('api_key', 'app_or_key').
    curated_models: List of recommended models for this provider.
    default_model: Default model id from the provider config.
  """

  provider_id: str
  display_name: str
  description: str
  requires_api_key: bool
  api_key_env_var: str | None
  account_setup_url: str
  api_key_creation_url: str | None
  auth_method: Literal["api_key", "app_or_key"]
  curated_models: list[CuratedModel]
  default_model: str
```

### Provider-Specific Metadata

#### Ollama Provider

```python
ProviderInfo(
  provider_id="ollama",
  display_name="Ollama",
  description="Local inference server with free cloud tier",
  requires_api_key=False,  # Can use app without key
  api_key_env_var=None,
  account_setup_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-ollama.html#account",
  api_key_creation_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-ollama.html#api-key",
  auth_method="app_or_key",
  curated_models=[
    CuratedModel("gemini-3-flash-preview:cloud", "Cloud model", "no local download needed"),
    CuratedModel("llama3.1:8b", "Llama 3.1 8B", "local model, requires pull"),
    CuratedModel("qwen2.5:7b", "Qwen 2.5 7B", "local model, requires pull"),
  ],
  default_model="gemini-3-flash-preview:cloud",
)
```

#### OpenAI Provider

```python
ProviderInfo(
  provider_id="openai",
  display_name="OpenAI",
  description="GPT models via OpenAI API",
  requires_api_key=True,
  api_key_env_var="OPENAI_API_KEY",
  account_setup_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-openai.html#account",
  api_key_creation_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-openai.html#api-key",
  auth_method="api_key",
  curated_models=[
    CuratedModel("gpt-4o-mini", "GPT-4o Mini", "fast and affordable"),
    CuratedModel("gpt-4o", "GPT-4o", "latest flagship model"),
    CuratedModel("gpt-4-turbo", "GPT-4 Turbo", "high performance"),
    CuratedModel("o1-preview", "O1 Preview", "reasoning model"),
  ],
  default_model="gpt-4o-mini",
)
```

#### Anthropic Provider

```python
ProviderInfo(
  provider_id="anthropic",
  display_name="Anthropic",
  description="Claude models via Anthropic API",
  requires_api_key=True,
  api_key_env_var="ANTHROPIC_API_KEY",
  account_setup_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-anthropic.html#account",
  api_key_creation_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-anthropic.html#api-key",
  auth_method="api_key",
  curated_models=[
    CuratedModel("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet", "balanced performance"),
    CuratedModel("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "fast and efficient"),
    CuratedModel("claude-3-opus-20240229", "Claude 3 Opus", "highest capability"),
  ],
  default_model="claude-3-5-sonnet-20241022",
)
```

#### Gemini Provider

```python
ProviderInfo(
  provider_id="gemini",
  display_name="Google Gemini",
  description="Gemini models via Google AI API",
  requires_api_key=True,
  api_key_env_var="GEMINI_API_KEY",  # or GOOGLE_API_KEY
  account_setup_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-gemini.html#account",
  api_key_creation_url="https://yoker.readthedocs.io/en/latest/guides/getting-started-with-gemini.html#api-key",
  auth_method="api_key",
  curated_models=[
    CuratedModel("gemini-1.5-flash", "Gemini 1.5 Flash", "fast and efficient"),
    CuratedModel("gemini-1.5-pro", "Gemini 1.5 Pro", "balanced performance"),
    CuratedModel("gemini-2.0-flash-exp", "Gemini 2.0 Flash", "experimental"),
  ],
  default_model="gemini-1.5-flash",
)
```

## Curated Models Per Provider

### CuratedModel Dataclass

```python
@dataclass(frozen=True)
class CuratedModel:
  """A single curated model entry.

  Attributes:
    model_id: The model identifier (e.g., 'gpt-4o-mini', 'claude-3-5-sonnet-20241022').
    label: Human-readable label shown in the wizard.
    note: Short helper note (e.g., 'fast and affordable').
  """

  model_id: str
  label: str
  note: str
```

### Model Selection Principles

1. **Default model** is always first in the list (single keystroke to accept)
2. **Mix of capabilities**: include fast/cheap and powerful options
3. **Include latest models**: surface the most recent stable releases
4. **Avoid overwhelming**: 3-4 models per provider (plus free-text entry)
5. **Notes help users choose**: brief guidance on use cases

## Provider-Specific Authentication Flows

### Ollama (App or Key)

**Step 3: Account Check**

```
Do you have an Ollama account? [y/n] (Enter = n):
```

If **no**: Open docs URL (account creation guide), wait for user to return.

**Step 4: Connection Method**

```
Connect via:
  1) The Ollama app running locally (recommended — no key needed)
  2) An Ollama API key

Choose [1/2] (Enter = 1):
```

- **Option 1 (App)**: No API key collected. Config uses default base URL.
- **Option 2 (Key)**: Collect API key (masked input), set `base_url` to cloud endpoint.

### OpenAI (API Key Only)

**Step 3: Account Check**

```
Do you have an OpenAI account? [y/n] (Enter = n):
```

If **no**: Open docs URL (account creation guide), wait for user to return.

**Step 4: API Key Collection**

```
Paste your OpenAI API key (masked):
```

If user has no key: Open docs URL (API key creation guide), wait, then prompt.

### Anthropic (API Key Only)

**Step 3: Account Check**

```
Do you have an Anthropic account? [y/n] (Enter = n):
```

If **no**: Open docs URL (account creation guide), wait for user to return.

**Step 4: API Key Collection**

```
Paste your Anthropic API key (masked):
```

If user has no key: Open docs URL (API key creation guide), wait, then prompt.

### Gemini (API Key Only)

**Step 3: Account Check**

```
Do you have a Google AI Studio account? [y/n] (Enter = n):
```

If **no**: Open docs URL (account creation guide), wait for user to return.

**Step 4: API Key Collection**

```
Paste your Google AI API key (masked):
```

If user has no key: Open docs URL (API key creation guide), wait, then prompt.

## Config Generation

### Provider-Agnostic Config Structure

The wizard generates provider-specific config based on the selected provider:

```python
# Ollama (app path)
[backend]
provider = "ollama"

[backend.ollama]
model = "gemini-3-flash-preview:cloud"

# Ollama (API key path)
[backend]
provider = "ollama"

[backend.ollama]
model = "gemini-3-flash-preview:cloud"
api_key = "ollama-..."
base_url = "https://api.ollama.com"

# OpenAI
[backend]
provider = "openai"

[backend.openai]
model = "gpt-4o-mini"
api_key = "sk-..."

# Anthropic
[backend]
provider = "anthropic"

[backend.anthropic]
model = "claude-3-5-sonnet-20241022"
api_key = "sk-ant-..."

# Gemini
[backend]
provider = "gemini"

[backend.gemini]
model = "gemini-1.5-flash"
api_key = "AIza..."
```

### Config Generation Logic

```python
def build_bootstrap_overrides(
  provider: str,
  model: str,
  connection: ConnectionChoice | None = None,
) -> dict[str, Any]:
  """Build config overrides for the selected provider.

  Args:
    provider: Provider identifier ('ollama', 'openai', 'anthropic', 'gemini').
    model: Selected model id.
    connection: For Ollama only — app vs API key choice.

  Returns:
    Flat dotted-key override dict for ConfigWriter.
  """
  overrides: dict[str, Any] = {
    "backend.provider": provider,
    f"backend.{provider}.model": model,
  }

  # Provider-specific overrides
  if provider == "ollama" and connection:
    if connection.use_api_key and connection.api_key:
      overrides["backend.ollama.api_key"] = connection.api_key
      overrides["backend.ollama.base_url"] = OLLAMA_CLOUD_BASE_URL

  elif provider in ("openai", "anthropic", "gemini") and connection:
    # For these providers, connection always has an api_key
    if connection.api_key:
      overrides[f"backend.{provider}.api_key"] = connection.api_key

  return overrides
```

## New Wizard Flow

### Step 1: Welcome (unchanged)

Explain yoker, report no config found, offer guided/manual setup.

### Step 2: Provider Selection (new)

```
Step 2 of 5: Select Provider

Choose your preferred LLM provider:

  1) Ollama — Local inference server with free cloud tier
  2) OpenAI — GPT models via OpenAI API
  3) Anthropic — Claude models via Anthropic API
  4) Google Gemini — Gemini models via Google AI API

Choose [1-4] (Enter = 1 Ollama):
```

- Default: Ollama (maintains backward compatibility)
- Provider info displayed to help users choose
- User can select any supported provider

### Step 3: Account Check (provider-specific)

Based on selected provider, ask account-specific question:

```python
async def step_account_check_provider(ui: UIHandler, provider: ProviderInfo) -> None:
  """Step 3: Check if user has an account for the selected provider."""
  prompt = f"Do you have a {provider.display_name} account?"
  has_account = await _ask_yes_no(ui, prompt, default=False)

  if not has_account:
    await _open_docs_confirmed(
      ui,
      provider.account_setup_url,
      blurb=f"The guide covers creating a {provider.display_name} account.",
    )
```

### Step 4: Authentication (provider-specific)

```python
async def step_authentication(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Step 4: Collect authentication credentials for the provider."""
  if provider.auth_method == "app_or_key":
    # Ollama: offer app vs API key choice
    return await _collect_ollama_auth(ui, provider)
  else:
    # OpenAI/Anthropic/Gemini: collect API key
    return await _collect_api_key(ui, provider)
```

#### Ollama Authentication (App or Key)

```python
async def _collect_ollama_auth(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Collect Ollama authentication (app or API key)."""
  ui.output_info(
    "Connect via:\n"
    "  1) The Ollama app running locally (recommended — no key needed)\n"
    "  2) An Ollama API key\n"
  )

  while True:
    raw = await ui.get_input("Choose [1/2] (Enter = 1 app): ")
    if raw is None:
      raise WizardAbort

    answer = raw.strip()
    if answer in ("", "1"):
      return ConnectionChoice(use_api_key=False)
    if answer == "2":
      await _open_docs_confirmed(
        ui,
        provider.api_key_creation_url,
        blurb=f"The guide walks through creating a {provider.display_name} API key.",
      )
      key = await ui.get_secret_input("Paste your Ollama API key: ")
      api_key = key.strip() if key else None
      if not api_key:
        ui.output_info("No key entered. Falling back to the Ollama app path.\n")
        return ConnectionChoice(use_api_key=False)
      return ConnectionChoice(use_api_key=True, api_key=api_key)

    ui.output_info("Invalid choice. Enter 1 or 2.\n")
```

#### API Key Authentication (OpenAI/Anthropic/Gemini)

```python
async def _collect_api_key(ui: UIHandler, provider: ProviderInfo) -> ConnectionChoice:
  """Collect API key for providers that require it."""
  # Check if user has an API key
  has_key = await _ask_yes_no(
    ui,
    f"Do you have a {provider.display_name} API key?",
    default=False
  )

  if not has_key:
    await _open_docs_confirmed(
      ui,
      provider.api_key_creation_url,
      blurb=f"The guide walks through creating a {provider.display_name} API key.",
    )

  # Collect the key
  env_hint = ""
  if provider.api_key_env_var:
    env_hint = f" (or set {provider.api_key_env_var} environment variable)"

  key = await ui.get_secret_input(f"Paste your {provider.display_name} API key{env_hint}: ")
  api_key = key.strip() if key else None

  if not api_key:
    ui.output_info(f"No key entered. You can set {provider.api_key_env_var} later.\n")
    return ConnectionChoice(use_api_key=False)

  return ConnectionChoice(use_api_key=True, api_key=api_key)
```

### Step 5: Model Selection (provider-specific)

```python
async def step_model_selection_provider(
  ui: UIHandler,
  provider: ProviderInfo
) -> str:
  """Step 5: Select a model from the provider's curated list."""
  models = provider.curated_models
  default_id = provider.default_model

  ui.output_step_title(5, 5, "Model Selection")
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
```

### Step 6: Confirm (updated)

```python
async def step_confirm_provider(
  ui: UIHandler,
  provider: ProviderInfo,
  config_path: Path
) -> None:
  """Step 6: Confirm config was created."""
  await ui.output_step_title(6, 6, "Configuration Created")
  ui.output_info(
    f"Configuration written to {config_path} (chmod 600).\n"
    f"Provider: {provider.display_name}\n"
    f"Model: {provider.default_model}\n"
    "yoker is continuing into the normal session now.\n"
  )
```

## Module Layout

```
src/yoker/bootstrap/
  __init__.py           # Public API exports
  detect.py             # config_provided() (existing)
  wizard.py             # BootstrapWizard: multi-provider flow
  steps.py              # Individual step functions (updated for providers)
  providers.py          # ProviderInfo dataclass + provider registry
  modellist.py          # Curated model lists per provider (existing, extended)
```

### providers.py Structure

```python
from yoker.config import Config

@dataclass(frozen=True)
class ProviderInfo:
  ...

@dataclass(frozen=True)
class CuratedModel:
  ...

# Provider registry
PROVIDERS: dict[str, ProviderInfo] = {
  "ollama": ProviderInfo(...),
  "openai": ProviderInfo(...),
  "anthropic": ProviderInfo(...),
  "gemini": ProviderInfo(...),
}

def get_provider_info(provider_id: str) -> ProviderInfo:
  """Get provider metadata by id."""
  return PROVIDERS[provider_id]

def get_default_provider() -> ProviderInfo:
  """Get the default provider (Ollama for backward compatibility)."""
  return PROVIDERS["ollama"]
```

### modellist.py Updates

Extend the existing module to provide provider-specific curated models:

```python
def curated_models_for_provider(provider_id: str, config: Config | None = None) -> list[CuratedModel]:
  """Return curated models for a specific provider.

  Args:
    provider_id: Provider identifier ('ollama', 'openai', etc.)
    config: Optional config to source defaults from.

  Returns:
    List of CuratedModel entries for the provider.
  """
  provider = get_provider_info(provider_id)
  return provider.curated_models

def default_model_for_provider(provider_id: str, config: Config | None = None) -> str:
  """Return the default model for a specific provider.

  Args:
    provider_id: Provider identifier.
    config: Optional config to source from.

  Returns:
    Default model id for the provider.
  """
  provider = get_provider_info(provider_id)
  return provider.default_model
```

## Security Considerations

1. **API keys are masked**: All API key input uses `ui.get_secret_input()`
2. **Keys stored only in ~/.yoker.toml**: Never in project configs, env vars, or logs
3. **chmod 600**: All config files are secured immediately after write
4. **Provider-specific env vars**: Users are informed about alternative auth methods (env vars)
5. **No key validation**: Wizard does not validate keys; backend will fail on invalid keys
6. **Secure defaults**: Default provider (Ollama) can work without API keys

## Documentation Requirements

Each provider needs a dedicated getting-started guide:

1. **Ollama** (existing): `docs/guides/getting-started-with-ollama.md`
2. **OpenAI** (new): `docs/guides/getting-started-with-openai.md`
3. **Anthropic** (new): `docs/guides/getting-started-with-anthropic.md`
4. **Gemini** (new): `docs/guides/getting-started-with-gemini.md`

Each guide should cover:
- Creating an account
- Installing the provider's CLI/app (if applicable)
- Generating an API key
- Setting up the provider with yoker
- Troubleshooting common issues

## Extensibility

Adding a new provider requires:

1. **Create ProviderConfig class** in `src/yoker/config/providers.py`:
   - Define Parameters class (model generation parameters)
   - Define Config class (provider-specific config)

2. **Add provider to KNOWN_PROVIDERS** in `src/yoker/config/__init__.py`:
   - Update tuple: `KNOWN_PROVIDERS = ("ollama", "openai", "anthropic", "gemini", "newprovider")`
   - Add config attribute to BackendConfig

3. **Create ProviderInfo entry** in `src/yoker/bootstrap/providers.py`:
   - Define metadata (name, URLs, curated models)
   - Add to PROVIDERS registry

4. **Create documentation guide**:
   - `docs/guides/getting-started-with-newprovider.md`

5. **(Optional) Create backend implementation**:
   - If using litellm: no backend code needed
   - If custom: implement BackendProtocol

**No changes to wizard logic required** — the provider metadata drives the flow.

## Testing Strategy

Following the principle from PR #34: **no unit tests for wizard IO**.

| Component | Type | Unit tests? |
|-----------|------|-------------|
| ProviderInfo dataclass | Data structure | **Yes** — metadata validation |
| curated_models_for_provider() | Logic | **Yes** — returns correct models |
| build_bootstrap_overrides() | Logic | **Yes** — correct config generation |
| Wizard steps | IO / user interaction | **No** — user-driven testing |

## Migration Path

The wizard maintains **backward compatibility** with existing Ollama users:

1. Default provider selection is Ollama (same as before)
2. Ollama flow remains unchanged (app vs API key)
3. Existing configs continue to work without modification
4. Users can re-run the wizard to switch providers (future enhancement)

## Requirements Coverage

| Requirement | Covered by |
|-------------|------------|
| Provider selection | Step 2 (new) |
| Provider-specific guidance | ProviderInfo.account_setup_url, ProviderInfo.api_key_creation_url |
| API key collection | Step 4 (provider-specific) |
| Model selection | Step 5 (provider-specific curated models) |
| Config generation | build_bootstrap_overrides() with provider awareness |
| Security (key masking, chmod 600) | Existing security measures |
| Extensibility | ProviderInfo dataclass + registry pattern |

## Open Questions

| ID | Topic | Question | Status |
|----|-------|----------|--------|
| Q1 | Provider selection default | Should Ollama remain the default, or should the wizard detect available providers? | **Proposed**: Ollama default (backward compatibility) |
| Q2 | Provider auto-detection | Should the wizard detect if user has OPENAI_API_KEY set and suggest OpenAI? | **Deferred**: Keep it simple for now |
| Q3 | Model list updates | Should curated models be fetched from a remote source or hardcoded? | **Proposed**: Hardcoded (same as current Ollama approach) |
| Q4 | Provider validation | Should wizard validate API keys before writing config? | **No**: Validation happens at runtime; keeps wizard simple |

## Implementation Tasks

1. **Create ProviderInfo dataclass** in `src/yoker/bootstrap/providers.py`
2. **Extend modellist.py** with provider-specific model functions
3. **Update wizard steps** to use ProviderInfo for dynamic flows
4. **Update build_bootstrap_overrides()** for provider-aware config generation
5. **Create provider documentation guides** (OpenAI, Anthropic, Gemini)
6. **Test the wizard** with each provider (user-driven testing)
7. **Update README** to document multi-provider support

## Notes

- The design prioritizes **simplicity over flexibility** — the wizard should feel lightweight, not overwhelming
- **Provider metadata is the single source of truth** — all provider-specific logic is data-driven
- **Security is maintained** — all existing security practices apply to new providers
- **Documentation is essential** — each provider needs clear getting-started guides

## Revision History

- 2026-06-30: Initial design for multi-provider bootstrap wizard