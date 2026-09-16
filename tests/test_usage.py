"""Tests for token usage logging (yoker.usage)."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from yoker.config import Config, UsageConfig
from yoker.usage import (
  KIND_RELEASE,
  KIND_SPAWN,
  UsageLogger,
  UsageRecord,
  log_call_usage,
  log_compaction_usage,
  log_error_usage,
  log_session_usage,
  log_tool_call_usage,
  log_turn_usage,
)


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
      # R1 fields: identity attribution + record kind + tool/bytes detail.
      "agent_id": None,
      "parent_agent_id": None,
      "kind": "llm_call",
      "tool": None,
      "success": None,
      "cached_tokens": None,
      "bytes_in": None,
      "bytes_out": None,
      "detail": None,
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


class TestAgentIdentityAttribution:
  """R1/R4: records carry the agent's session-assigned id + parent linkage."""

  def test_llm_call_carries_agent_ids(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)
    agent._agent_id = "code-reviewer-1"
    agent._parent_agent_id = "primary"

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})

    (record,) = _read_lines(path)
    assert record["agent_id"] == "code-reviewer-1"
    assert record["parent_agent_id"] == "primary"
    assert record["kind"] == "llm_call"

  def test_standalone_agent_ids_default_to_none(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)  # no _agent_id attributes set

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})

    (record,) = _read_lines(path)
    assert record["agent_id"] is None
    assert record["parent_agent_id"] is None


class TestTelemetryRecordKinds:
  """R1: lifecycle/tool records join the llm_call records in the same log."""

  def test_tool_call_record(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)
    agent._agent_id = "primary"

    log_tool_call_usage(
      agent,
      "yoker__read",
      success=True,
      duration_ms=42,
      bytes_in=57,
      bytes_out=1204,
    )

    (record,) = _read_lines(path)
    assert record["kind"] == "tool_call"
    assert record["tool"] == "yoker__read"
    assert record["success"] is True
    assert record["duration_ms"] == 42
    assert record["bytes_in"] == 57
    assert record["bytes_out"] == 1204
    assert record["agent_id"] == "primary"
    # Token counts stay exclusive to llm_call records (no double-count).
    assert record["input_tokens"] == 0
    assert record["output_tokens"] == 0

  def test_tool_failure_is_a_tool_call_record_with_success_false(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_tool_call_usage(
      agent, "yoker__write", success=False, duration_ms=3, bytes_in=20, bytes_out=88
    )

    (record,) = _read_lines(path)
    assert record["kind"] == "tool_call"
    assert record["success"] is False

  def test_turn_record_has_wall_clock_and_counts_no_tokens(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_turn_usage(agent, duration_ms=5400, tool_calls_count=3, llm_calls=4)

    (record,) = _read_lines(path)
    assert record["kind"] == "turn"
    assert record["duration_ms"] == 5400
    assert record["detail"] == {"tool_calls_count": 3, "llm_calls": 4}
    assert record["input_tokens"] == 0
    assert record["output_tokens"] == 0

  def test_compaction_record_carries_run_report(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    run = {"run_id": "run-1", "dropped_count": 5, "stages": [{"stage": "prune_tool_results"}]}
    log_compaction_usage(agent, run)

    (record,) = _read_lines(path)
    assert record["kind"] == "compaction"
    assert record["detail"]["run"] == run

  def test_error_record(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_error_usage(
      agent,
      source="idle_watchdog",
      message="LLM stream idle for 90.0s",
      detail={"idle_seconds": 90.0},
    )

    (record,) = _read_lines(path)
    assert record["kind"] == "error"
    assert record["tool"] == "idle_watchdog"
    assert record["success"] is False
    assert record["detail"]["message"] == "LLM stream idle for 90.0s"

  def test_session_lifecycle_records(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"

    log_session_usage(
      UsageConfig(enabled=True, path=path),
      session_id="sess-9",
      kind=KIND_SPAWN,
      agent="researcher",
      agent_id="researcher-1",
      parent_agent_id="primary",
      model="glm-5.3-flash:cloud",
      detail={"requester": "primary"},
    )
    log_session_usage(
      UsageConfig(enabled=True, path=path),
      session_id="sess-9",
      kind=KIND_RELEASE,
      agent="researcher",
      agent_id="researcher-1",
      parent_agent_id="primary",
      model="glm-5.3-flash:cloud",
    )

    records = _read_lines(path)
    assert [r["kind"] for r in records] == ["spawn", "release"]
    assert all(r["agent_id"] == "researcher-1" for r in records)
    assert all(r["parent_agent_id"] == "primary" for r in records)
    assert records[0]["detail"] == {"requester": "primary"}

  def test_token_sum_invariant_llm_call_exclusive(self, tmp_path: Any, monkeypatch: Any) -> None:
    """Mixed-kind log: only llm_call rows carry tokens — summing the log's
    token columns equals summing llm_call rows (no double-count)."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_call_usage(agent, {"input_tokens": 100, "output_tokens": 50})
    log_tool_call_usage(
      agent, "yoker__read", success=True, duration_ms=10, bytes_in=8, bytes_out=100
    )
    log_turn_usage(agent, duration_ms=900, tool_calls_count=1, llm_calls=1)

    records = _read_lines(path)
    llm_rows = [r for r in records if r["kind"] == "llm_call"]
    assert len(llm_rows) == 1
    assert sum(r["input_tokens"] for r in records) == sum(r["input_tokens"] for r in llm_rows)
    assert sum(r["output_tokens"] for r in records) == sum(r["output_tokens"] for r in llm_rows)

  def test_disabled_config_silences_all_kinds(self, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path, enabled=False)

    log_tool_call_usage(agent, "t", success=True, duration_ms=1, bytes_in=0, bytes_out=0)
    log_turn_usage(agent, duration_ms=1, tool_calls_count=0, llm_calls=0)
    log_error_usage(agent, source="s", message="m")

    assert not path.exists()

  def test_log_never_raises_on_pathological_detail(self, tmp_path: Any) -> None:
    """N1 regression: log() must never raise — even when a detail object
    raises during serialization (json.dumps with default=str)."""

    class Exploding:
      def __str__(self) -> str:
        raise RuntimeError("str() bomb")

    path = tmp_path / "usage.jsonl"
    logger = UsageLogger(str(path))

    logger.log(_record(detail={"boom": Exploding()}))  # Must not raise.
    assert not path.exists()  # Nothing written, no exception.

  def test_shared_gate_suppresses_all_writers_under_pytest(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    """Test gap 3: log_usage_record's PYTEST guard applies to every
    writer, not just log_call_usage (guards restored via monkeypatch)."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x.py::test_y")
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    log_tool_call_usage(agent, "t", success=True, duration_ms=1, bytes_in=0, bytes_out=0)
    log_turn_usage(agent, duration_ms=1, tool_calls_count=0, llm_calls=0)
    log_error_usage(agent, source="s", message="m")
    log_compaction_usage(agent, {"run_id": "r"})
    log_session_usage(
      UsageConfig(enabled=True, path=path), session_id="s", kind=KIND_SPAWN, agent="a", agent_id="i"
    )

    assert not path.exists()

  def test_hook_path_overflow_writes_no_compaction_record(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    """Test gap 4: a hook-attended overflow performs no record_compaction
    and therefore no telemetry compaction record either (mirrors the
    existing suppression in _manage_context_overflow)."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    path = tmp_path / "usage.jsonl"
    agent = _agent(tmp_path, path=path)

    # Mirrors the hook_path guard: the writer is only invoked when
    # record_compaction runs — a hook-path overflow skips both.
    hook_path = True
    run_report: dict[str, Any] = {"run_id": "run-1"}
    if not hook_path:
      log_compaction_usage(agent, run_report)

    assert not path.exists()
