"""Curated model list for the bootstrap wizard (MBI-002 task 2.4).

This module holds a **curated list** of recommended models presented by the
wizard's Step 5, plus a free-text entry option. It makes **no network call**:
live fetch from the local ollama proxy was considered and rejected for the
first-install UX (typically nothing pulled yet). See
``analysis/bootstrap-wizard-design.md`` (Resolved Q5).

The default model is read from :class:`yoker.config.Config` so this module
never hardcodes the default literal — there is exactly one source of truth
(``OllamaConfig.model``).

For multi-provider support, this module also provides provider-specific model
lists from the ProviderInfo registry.
"""

from __future__ import annotations

from yoker.bootstrap.providers import CuratedModel, get_curated_models, get_default_model
from yoker.config import Config


def default_model_id(config: Config | None = None) -> str:
  """Return the default model id from the Config (single source of truth).

  Args:
    config: Optional config to read from. When ``None``, a default
      :class:`Config` is constructed. Passing a config avoids rebuilding it.

  Returns:
    The default model id (e.g. ``"llama3.2:3b"``).
  """
  cfg = config if config is not None else Config()
  return cfg.backend.ollama.model


def _note_for(model_id: str) -> str:
  """Derive a short helper note from the model id convention.

  Local Ollama models require pulling before use. This keeps the curated-list
  note consistent with the actual default without a separate config field.

  Args:
    model_id: The ollama model id to describe.

  Returns:
    ``"local model, requires `ollama pull <model>`"`` for all models.
  """
  return f"local model, requires `ollama pull {model_id}`"


def curated_models(config: Config | None = None) -> list[CuratedModel]:
  """Return the curated list of recommended models.

  The first entry is always the default model read from ``Config`` so that
  accepting the default is a single keystroke. The list includes popular
  local models. The caller also offers a free-text entry option
  (handled in the wizard step, not here).

  Args:
    config: Optional config to source the default model id from.

  Returns:
    A list of :class:`CuratedModel` entries, default first.
  """
  default_id = default_model_id(config)
  return [
    CuratedModel(
      model_id=default_id,
      label=f"{default_id} (default)",
      note=_note_for(default_id),
    ),
    CuratedModel(
      model_id="llama3.1:8b",
      label="llama3.1:8b",
      note="local model, requires `ollama pull llama3.1:8b`",
    ),
    CuratedModel(
      model_id="qwen2.5:7b",
      label="qwen2.5:7b",
      note="local model, requires `ollama pull qwen2.5:7b`",
    ),
    CuratedModel(
      model_id="gemma2:9b",
      label="gemma2:9b",
      note="local model, requires `ollama pull gemma2:9b`",
    ),
  ]


def curated_models_for_provider(provider_id: str) -> list[CuratedModel]:
  """Return curated models for a specific provider.

  Converts provider CuratedModel entries to the legacy CuratedModel type
  for backward compatibility with the wizard.

  Args:
    provider_id: Provider identifier ('ollama', 'openai', etc.)

  Returns:
    List of CuratedModel entries for the provider.
  """
  provider_models = get_curated_models(provider_id)
  return [
    CuratedModel(
      model_id=m.model_id,
      label=m.label,
      note=m.note,
    )
    for m in provider_models
  ]


def default_model_for_provider(provider_id: str) -> str:
  """Return the default model for a specific provider.

  Args:
    provider_id: Provider identifier.

  Returns:
    Default model id for the provider.
  """
  return get_default_model(provider_id)


__all__ = [
  "CuratedModel",
  "curated_models",
  "default_model_id",
  "curated_models_for_provider",
  "default_model_for_provider",
]

