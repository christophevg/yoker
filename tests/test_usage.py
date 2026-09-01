"""Tests for token usage logging (yoker.usage)."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from yoker.config import Config, UsageConfig
from yoker.usage import UsageLogger, UsageRecord, log_call_usage


def _record(**overrides: Any) -> UsageRecord:
  """Standard record for logging tests."""
  fields: dict[str, Any] = {
    "ts": "2026-09-01T12:00:00+00:00",
    "session_id": "sess-1",
    "model": "glm-5.3-flash:cloud",
    "agent": "main",
    "input_tokens": 120,
    "output_tokens": 45,
    "duration_ms": 800,
  }
  fields.update(overrides)
  return UsageRecord(**fields)


def _agent(tmp_path: Any, *, enabled: bool = True, path: str | None = None) -> SimpleNamespace:
  """Minimal agent stand-in matching the attributes log_call_usage touches."""
  path = path or str(tmp_path / "usage.jsonl")
  return SimpleNamespace(
    config=SimpleNamespace(usage=UsageConfig(enabled=enabled, path=path)),
    context=SimpleNamespace(get_session_id=lambda: "sess-42"),
    model="glm-5.3-flash:cloud",
    definition=SimpleNamespace(name="main"),
  )


def _read_lines(path: Any) -> list[dict[str, Any]]:
  lines = path.read_text().splitlines()
  return [json.loads(line) for line in lines]


class TestUsageLogger:
  """Tests for UsageLogger JSONL appends."""

  def test_log_writes_valid_jsonl_with_all_fields(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    logger = UsageLogger(str(path))

    logger.log(_record())

    records = _read_lines(path)
    assert len(records) == 1
    assert records[0] == {
      "ts": "2026-09-01T12:00:00+00:00",
      "session_id": "sess-1",
      "model": "glm-5.3-flash:cloud",
      "agent": "main",
      "input_tokens": 120,
      "output_tokens": 45,
      "duration_ms": 800,
      "thinking_chars": 0,
      "content_chars": 0,
    }

  def test_log_round_trips_nonzero_char_counts(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    logger = UsageLogger(str(path))

    logger.log(_record(thinking_chars=3000, content_chars=500))

    (record,) = _read_lines(path)
    assert record["thinking_chars"] == 3000
    assert record["content_chars"] == 500

  def test_log_appends_multiple_records_as_separate_lines(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    logger = UsageLogger(str(path))

    logger.log(_record(session_id="a"))
    logger.log(_record(session_id="b"))

    records = _read_lines(path)
    assert len(records) == 2
    assert [r["session_id"] for r in records] == ["a", "b"]

  def test_log_expands_home_directory(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows expanduser source.
    logger = UsageLogger("~/.yoker/usage.jsonl")

    logger.log(_record())

    assert (tmp_path / ".yoker" / "usage.jsonl").exists()

  @pytest.mark.skipif(sys.platform == "win32", reason="O_APPEND atomicity is POSIX-only")
  def test_log_concurrent_writes_never_interleave(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    threads = 8
    writes_per_thread = 25
    logger = UsageLogger(str(path))

    def write_many(worker: int) -> None:
      for i in range(writes_per_thread):
        logger.log(_record(session_id=f"worker-{worker}", input_tokens=i))

    with ThreadPoolExecutor(max_workers=threads) as pool:
      list(pool.map(write_many, range(threads)))

    records = _read_lines(path)
    assert len(records) == threads * writes_per_thread
    assert all(r["input_tokens"] == i for r in records for i in [r["input_tokens"]])

  def test_log_never_raises_on_unwritable_path(self, tmp_path: Any) -> None:
    # A path component that exists as a file makes mkdir/os.open fail.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    logger = UsageLogger(str(blocker / "usage.jsonl"))

    logger.log(_record())  # Must not raise.

  @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes not reported on Windows")
  def test_log_sets_owner_only_permissions(self, tmp_path: Any) -> None:
    import os
    import stat

    path = tmp_path / "usage.jsonl"
    UsageLogger(str(path)).log(_record())

    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


class TestLogCallUsage:
  """Tests for the processing-loop convenience function."""

  def test_ollama_style_stats_are_normalized(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # bypass pytest guard
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_call_usage(agent, {"prompt_eval_count": 100, "eval_count": 30, "total_duration_ms": 500})

    (record,) = _read_lines(path)
    assert record["input_tokens"] == 100
    assert record["output_tokens"] == 30
    assert record["duration_ms"] == 500
    assert record["model"] == "glm-5.3-flash:cloud"
    assert record["agent"] == "main"
    assert record["session_id"] == "sess-42"

  def test_litellm_style_stats_are_logged(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # bypass pytest guard
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_call_usage(
      agent,
      {
        "input_tokens": 200,
        "output_tokens": 80,
        "total_duration_ms": 1200,
        "thinking_chars": 2500,
        "content_chars": 900,
      },
    )

    (record,) = _read_lines(path)
    assert record["input_tokens"] == 200
    assert record["output_tokens"] == 80
    assert record["thinking_chars"] == 2500
    assert record["content_chars"] == 900

  def test_skips_when_both_token_counts_are_zero(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # bypass pytest guard
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_call_usage(agent, {"prompt_eval_count": 0, "eval_count": 0, "total_duration_ms": 100})

    assert not path.exists()

  def test_skips_when_disabled(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # bypass pytest guard
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path, enabled=False)

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})

    assert not path.exists()

  def test_session_id_falls_back_to_unknown(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # bypass pytest guard
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)
    agent.context = SimpleNamespace(get_session_id=lambda: 1 / 0)  # type: ignore[assignment]

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})

    (record,) = _read_lines(path)
    assert record["session_id"] == "unknown"

  def test_skips_under_pytest(self, tmp_path: Any, monkeypatch: Any) -> None:
    # The pytest guard must suppress logging (mock stats polluting the real
    # log) — restore the env var and verify nothing is written.
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x.py::test_y")
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})

    assert not path.exists()


class TestUsageConfig:
  """Tests for UsageConfig defaults and root Config wiring."""

  def test_defaults(self) -> None:
    config = UsageConfig()
    assert config.enabled is True
    assert config.path == "~/.yoker/usage.jsonl"

  def test_root_config_has_usage_field(self) -> None:
    config = Config(enabled=True)
    assert isinstance(config.usage, UsageConfig)
    assert config.usage.enabled is True
