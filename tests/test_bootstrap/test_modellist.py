"""Tests for :mod:`yoker.bootstrap.modellist` (MBI-002 task 2.4).

Pure-logic tests covering the single-source-of-truth guarantee
(:func:`default_model_id`) and the UX-critical guarantee that the default
entry is first in :func:`curated_models`. Also covers the note-derivation
convention (cloud vs local) introduced by the round-1 review fix.
"""

from yoker.bootstrap.modellist import _note_for, curated_models, default_model_id
from yoker.config import Config


class TestDefaultModelId:
  """``default_model_id`` is the runtime expression of task 2.0."""

  def test_returns_config_ollama_model(self) -> None:
    """``default_model_id()`` reads ``Config().backend.ollama.model``."""
    config = Config()
    assert default_model_id(config) == config.backend.ollama.model

  def test_default_config_matches_no_arg_call(self) -> None:
    """Calling with ``None`` builds the same default ``Config``."""
    assert default_model_id() == Config().backend.ollama.model


class TestCuratedModels:
  """``curated_models`` places the default first and is non-empty."""

  def test_returns_non_empty_list(self) -> None:
    """The curated list is never empty."""
    assert len(curated_models()) > 0

  def test_default_entry_is_first(self) -> None:
    """The first entry's ``model_id`` equals :func:`default_model_id`."""
    models = curated_models()
    assert models[0].model_id == default_model_id()


class TestNoteDerivation:
  """Note convention: cloud vs local, derived from the model id."""

  def test_cloud_note_for_cloud_id(self) -> None:
    """Ids ending in ``:cloud`` get the cloud note."""
    assert "cloud" in _note_for("gemini-3-flash-preview:cloud")

  def test_local_note_for_non_cloud_id(self) -> None:
    """Other ids get the local note."""
    assert _note_for("llama3.1:8b") == "local model"

  def test_default_entry_note_matches_convention(self) -> None:
    """The default entry's note is consistent with the default id."""
    default_id = default_model_id()
    default_entry = curated_models()[0]
    if default_id.endswith(":cloud"):
      assert "cloud" in default_entry.note
    else:
      assert default_entry.note == "local model"
