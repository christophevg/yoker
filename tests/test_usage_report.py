"""Tests for token usage reporting (yoker.usage.report)."""

import json
import math
from typing import Any

import pytest

from yoker.usage.report import (
  CACHED_INPUT_NOTE,
  aggregate,
  calibration_ratio,
  format_report,
  load_usage,
  match_model,
)

# Pricing subset mirroring scripts/ollama_pricing.json (test-local, no file I/O).
PRICING: dict[str, Any] = {
  "models": {
    "glm-5.3-flash": {"input": 0.15, "cached_input": 0.03, "output": 0.50},
    "gpt-oss:120b": {"input": 0.15, "cached_input": 0.014, "output": 0.60},
    "kimi-k3": {"input": 3.00, "cached_input": 0.30, "output": 15.00},
    "qwen3.5": {"input": 0.60, "cached_input": 0.60, "output": 3.60},
  }
}


def _record(**overrides: Any) -> dict[str, Any]:
  fields: dict[str, Any] = {
    "ts": "2026-09-01T12:00:00+00:00",
    "session_id": "sess-1",
    "model": "glm-5.3-flash",
    "agent": "main",
    "input_tokens": 1000,
    "output_tokens": 100,
    "duration_ms": 500,
    "thinking_chars": 0,
    "content_chars": 0,
  }
  fields.update(overrides)
  return fields


class TestLoadUsage:
  """Tests for JSONL loading."""

  def test_parses_valid_jsonl(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    path.write_text(json.dumps(_record()) + "\n" + json.dumps(_record(model="gpt-oss:120b")) + "\n")

    records, skipped = load_usage(path)

    assert skipped == 0
    assert len(records) == 2
    assert records[0]["model"] == "glm-5.3-flash"
    assert records[1]["model"] == "gpt-oss:120b"

  def test_skips_malformed_and_blank_lines(self, tmp_path: Any) -> None:
    path = tmp_path / "usage.jsonl"
    lines = [
      json.dumps(_record()),
      "not json at all",
      "",
      json.dumps(_record(input_tokens=5)),
      "[1, 2, 3]",  # valid JSON but not an object
    ]
    path.write_text("\n".join(lines) + "\n")

    records, skipped = load_usage(path)

    assert len(records) == 2
    assert skipped == 2  # malformed text line + non-object JSON line

  def test_missing_file_raises(self, tmp_path: Any) -> None:
    with pytest.raises(FileNotFoundError):
      load_usage(tmp_path / "nope.jsonl")


class TestMatchModel:
  """Tests for logged-name → pricing-key mapping."""

  def test_exact_match(self) -> None:
    assert match_model("glm-5.3-flash", PRICING) == "glm-5.3-flash"

  def test_strips_cloud_tag(self) -> None:
    assert match_model("glm-5.3-flash:cloud", PRICING) == "glm-5.3-flash"

  def test_strips_latest_tag(self) -> None:
    assert match_model("kimi-k3:latest", PRICING) == "kimi-k3"

  def test_colon_model_matches_itself(self) -> None:
    # Regression: 'gpt-oss:120b' contains a colon tag itself.
    assert match_model("gpt-oss:120b", PRICING) == "gpt-oss:120b"

  def test_no_match_returns_none(self) -> None:
    assert match_model("totally-unknown-model", PRICING) is None

  def test_prefix_match_with_other_tag(self) -> None:
    assert match_model("glm-5.3-flash:xyz", PRICING) == "glm-5.3-flash"

  def test_qwen_cloud_tag_maps_to_base(self) -> None:
    # Ollama names the cloud deployment 'qwen3.5:cloud'; the pricing entry
    # (for qwen3.5:397b) is keyed as bare 'qwen3.5' so the tag-strip rule
    # bridges the naming deviation.
    assert match_model("qwen3.5:cloud", PRICING) == "qwen3.5"

  def test_real_pricing_file_is_valid_and_covers_logged_models(self) -> None:
    # The shipped pricing file must parse and every model entry needs
    # input/output prices (cost math reads them unconditionally).
    import json
    from pathlib import Path

    pricing_path = Path(__file__).parent.parent / "scripts" / "ollama_pricing.json"
    pricing = json.loads(pricing_path.read_text())

    assert pricing["currency"] == "USD"
    assert pricing["unit"] == "per_million_tokens"
    for name, entry in pricing["models"].items():
      assert isinstance(entry["input"], (int, float)), f"{name}: missing input price"
      assert isinstance(entry["output"], float | int), f"{name}: missing output price"

    # Live-observed logged names must resolve against the real table.
    assert match_model("glm-5.3-flash:cloud", pricing) == "glm-5.3-flash"
    assert match_model("qwen3.5:cloud", pricing) == "qwen3.5"


class TestAggregate:
  """Tests for aggregation and cost math."""

  def test_mixed_models_cost_math(self) -> None:
    records = [
      # glm-5.3-flash: 89806*0.15/1e6 + 1685*0.5/1e6 = 0.0134709 + 0.0008425 = 0.0143134
      # content_chars=400 on the first record calibrates ratio 4.0 (400 chars / 100 tok).
      _record(model="glm-5.3-flash", input_tokens=89806, output_tokens=1685, content_chars=400),
      # kimi-k3: 2000*3/1e6 + 500*15/1e6 = 0.006 + 0.0075 = 0.0135
      _record(model="kimi-k3", input_tokens=2000, output_tokens=500),
      # gpt-oss:120b: 1000*0.15/1e6 + 200*0.6/1e6 = 0.00015 + 0.00012 = 0.00027
      _record(model="gpt-oss:120b", input_tokens=1000, output_tokens=200),
      # cloud-tagged variant aggregates under the same pricing key
      _record(model="glm-5.3-flash:cloud", input_tokens=1000, output_tokens=100),
    ]

    agg = aggregate(records, PRICING)

    assert agg["calls"] == 4
    assert agg["sessions"] == 1
    flash = agg["models"]["glm-5.3-flash"]
    assert flash["calls"] == 2
    assert flash["input_tokens"] == 90806
    assert flash["output_tokens"] == 1785
    assert math.isclose(
      flash["cost"], 89806 * 0.15 / 1e6 + 1685 * 0.5 / 1e6 + 1000 * 0.15 / 1e6 + 100 * 0.5 / 1e6
    )
    assert math.isclose(agg["models"]["kimi-k3"]["cost"], 2000 * 3.0 / 1e6 + 500 * 15.0 / 1e6)
    assert math.isclose(agg["total_cost"], flash["cost"] + 0.0135 + 0.00027)
    assert agg["total_input_tokens"] == 89806 + 2000 + 1000 + 1000
    assert agg["total_output_tokens"] == 1685 + 500 + 200 + 100

  def test_sessions_counts_distinct(self) -> None:
    records = [
      _record(session_id="a"),
      _record(session_id="a"),
      _record(session_id="b"),
    ]

    agg = aggregate(records, PRICING)

    assert agg["sessions"] == 2
    assert agg["calls"] == 3

  def test_first_last_ts(self) -> None:
    # ts strings are ISO 8601 (lexicographically sortable); the report shows
    # first/last seen in file order, so records arrive out of order here.
    records = [
      _record(ts="2026-09-01T12:00:00+00:00"),
      _record(ts="2026-09-01T10:00:00+00:00"),
      _record(ts="2026-09-01T11:00:00+00:00"),
    ]

    agg = aggregate(records, PRICING)

    assert agg["first_ts"] == "2026-09-01T12:00:00+00:00"
    assert agg["last_ts"] == "2026-09-01T11:00:00+00:00"

  def test_unknown_model_gathers_tokens_zero_cost(self) -> None:
    records = [
      _record(model="mystery-model", input_tokens=500, output_tokens=50, content_chars=300)
    ]

    agg = aggregate(records, PRICING)

    assert "mystery-model" in agg["unknown_models"]
    # Single thinking-off record also calibrates: ratio = 300 chars / 50 tok = 6.0.
    assert agg["unknown_models"]["mystery-model"] == {
      "calls": 1,
      "input_tokens": 500,
      "output_tokens": 50,
      "thinking_chars": 0,
      "content_chars": 300,
      "est_content_tokens": 50,
      "est_thinking_tokens": 0,
      "implied_thinking_in_output": 0,
    }
    assert agg["total_cost"] == 0.0
    assert agg["total_input_tokens"] == 500

  def test_missing_token_keys_treated_as_zero(self) -> None:
    records = [_record(model="glm-5.3-flash", input_tokens=None, output_tokens=None)]

    agg = aggregate(records, PRICING)

    assert agg["models"]["glm-5.3-flash"]["input_tokens"] == 0
    assert agg["models"]["glm-5.3-flash"]["output_tokens"] == 0
    assert agg["total_cost"] == 0.0

  def test_char_counts_accumulate(self) -> None:
    records = [
      _record(model="glm-5.3-flash", thinking_chars=3000, content_chars=500),
      _record(model="glm-5.3-flash", thinking_chars=1000, content_chars=200),
      _record(model="mystery-model", thinking_chars=500, content_chars=100),
    ]

    agg = aggregate(records, PRICING)

    assert agg["models"]["glm-5.3-flash"]["thinking_chars"] == 4000
    assert agg["models"]["glm-5.3-flash"]["content_chars"] == 700
    assert agg["unknown_models"]["mystery-model"]["thinking_chars"] == 500
    assert agg["total_thinking_chars"] == 4500
    assert agg["total_content_chars"] == 800

  def test_missing_char_keys_treated_as_zero(self) -> None:
    record = _record(model="glm-5.3-flash")
    del record["thinking_chars"]
    del record["content_chars"]

    agg = aggregate([record], PRICING)

    assert agg["models"]["glm-5.3-flash"]["thinking_chars"] == 0
    assert agg["models"]["glm-5.3-flash"]["content_chars"] == 0

  def test_zero_records_empty_structure(self) -> None:
    agg = aggregate([], PRICING)

    assert agg == {
      "calls": 0,
      "sessions": 0,
      "first_ts": None,
      "last_ts": None,
      "models": {},
      "unknown_models": {},
      "total_input_tokens": 0,
      "total_output_tokens": 0,
      "total_cost": 0.0,
      "total_thinking_chars": 0,
      "total_content_chars": 0,
      "est_content_tokens": 0,
      "est_thinking_tokens": 0,
      "est_thinking_cost": 0.0,
      "implied_thinking_in_output": 0,
      "ratio": None,
    }


class TestCalibrationRatio:
  """Tests for the chars-per-token calibration."""

  def test_none_with_no_qualifying_records(self) -> None:
    assert calibration_ratio([]) is None
    # thinking-on records and zero-content records never qualify.
    assert (
      calibration_ratio([_record(thinking_chars=100, content_chars=200, output_tokens=50)]) is None
    )
    assert calibration_ratio([_record(content_chars=0, output_tokens=50)]) is None
    # content but no tokens doesn't qualify either.
    assert calibration_ratio([_record(content_chars=400, output_tokens=0)]) is None

  def test_token_weighted_math(self) -> None:
    records = [
      _record(output_tokens=100, content_chars=400),  # thinking-off
      _record(output_tokens=200, content_chars=500),  # thinking-off
      _record(thinking_chars=999, content_chars=999, output_tokens=999),  # ignored: thinking-on
    ]

    ratio = calibration_ratio(records)

    assert ratio is not None
    assert math.isclose(ratio, 900 / 300)

  def test_ignores_zero_content_records(self) -> None:
    records = [
      _record(output_tokens=100, content_chars=0),  # excluded
      _record(output_tokens=150, content_chars=300),
    ]

    ratio = calibration_ratio(records)

    assert ratio is not None
    assert math.isclose(ratio, 300 / 150)


class TestEstimates:
  """Tests for calibrated token/cost estimates in aggregate()."""

  def test_estimates_hand_computed(self) -> None:
    # Calibration: one thinking-off call, 400 chars / 100 tok → ratio 4.0 chars/token.
    # Thinking-on record: 3000 thinking_chars, 500 content_chars, output_tokens=922.
    records = [
      _record(model="glm-5.3-flash", output_tokens=100, content_chars=400),
      _record(
        model="glm-5.3-flash",
        output_tokens=922,
        thinking_chars=3000,
        content_chars=500,
      ),
    ]

    agg = aggregate(records, PRICING)

    assert agg["ratio"] is not None
    assert math.isclose(agg["ratio"], 4.0)
    flash = agg["models"]["glm-5.3-flash"]
    # Bucket sums include the calibration record's own chars: content 400+500=900
    # → est_content 225 tok; thinking 3000 → est_thinking 750 tok.
    assert flash["est_content_tokens"] == 225
    assert flash["est_thinking_tokens"] == 750
    # implied = (100+922) reported − 225 est content.
    assert flash["implied_thinking_in_output"] == 1022 - 225
    assert math.isclose(flash["est_thinking_cost"], 750 * 0.5 / 1e6)
    assert agg["est_thinking_tokens"] == 750
    assert agg["est_content_tokens"] == 225
    assert math.isclose(agg["est_thinking_cost"], 750 * 0.5 / 1e6)
    assert agg["implied_thinking_in_output"] == 1022 - 225

  def test_no_calibration_records_zero_estimates(self) -> None:
    records = [_record(model="glm-5.3-flash", thinking_chars=3000, content_chars=500)]

    agg = aggregate(records, PRICING)

    assert agg["ratio"] is None
    assert agg["models"]["glm-5.3-flash"]["est_content_tokens"] == 0
    assert agg["models"]["glm-5.3-flash"]["est_thinking_tokens"] == 0
    assert agg["models"]["glm-5.3-flash"]["est_thinking_cost"] == 0.0
    assert agg["est_thinking_cost"] == 0.0

  def test_unknown_model_has_no_thinking_cost(self) -> None:
    records = [
      _record(model="glm-5.3-flash", output_tokens=100, content_chars=400),  # calibrates ratio
      _record(model="mystery-model", thinking_chars=1000, content_chars=100),
    ]

    agg = aggregate(records, PRICING)

    unknown = agg["unknown_models"]["mystery-model"]
    assert unknown["est_thinking_tokens"] == round(1000 / agg["ratio"])
    assert "est_thinking_cost" not in unknown


class TestFormatReport:
  """Tests for the text rendering."""

  def _agg(self, records: list[dict[str, Any]]) -> dict[str, Any]:
    return aggregate(records, PRICING)

  def test_contains_model_total_and_note(self) -> None:
    records = [_record(model="glm-5.3-flash", input_tokens=89806, output_tokens=1685)]
    report = format_report(self._agg(records))

    assert "glm-5.3-flash" in report
    assert "Total" in report
    assert "$0.014313" in report  # 89806*0.15/1e6 + 1685*0.5/1e6 = 0.0143134
    assert "cached-token" in report

  def test_zero_records_message(self) -> None:
    assert format_report(self._agg([])) == "No usage records."

  def test_omits_range_line_without_ts(self) -> None:
    records = [_record(ts=None)]
    report = format_report(self._agg(records))

    assert "Usage report" in report
    assert "→" not in report


class TestIntegrationPricingFile:
  """Integration: real pricing file + tmp usage file, same path the script takes."""

  def test_script_path_end_to_end(self, tmp_path: Any) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps(PRICING))
    pricing = json.loads(pricing_path.read_text())

    usage_path = tmp_path / "usage.jsonl"
    usage_path.write_text(
      "\n".join(
        [
          json.dumps(
            _record(
              model="glm-5.3-flash:cloud", input_tokens=44903, output_tokens=842, session_id="s1"
            )
          ),
          json.dumps(
            _record(
              model="glm-5.3-flash:cloud", input_tokens=44903, output_tokens=843, session_id="s1"
            )
          ),
          json.dumps(
            _record(model="some-unknown-model", input_tokens=100, output_tokens=10, session_id="s2")
          ),
        ]
      )
      + "\n"
    )
    records, skipped = load_usage(usage_path)
    agg = aggregate(records, pricing)

    assert skipped == 0
    assert agg["calls"] == 3
    assert agg["sessions"] == 2
    assert agg["models"]["glm-5.3-flash"]["calls"] == 2
    expected_flash_cost = (44903 + 44903) * 0.15 / 1e6 + (842 + 843) * 0.5 / 1e6
    assert math.isclose(agg["total_cost"], expected_flash_cost)
    assert agg["unknown_models"]["some-unknown-model"]["calls"] == 1

    report = format_report(agg)
    assert "some-unknown-model" in report
    assert "Unpriced models:" in report
    # No thinking chars anywhere in this fixture → no estimate block.
    assert "Thinking estimate" not in report

  def test_script_path_with_chars_end_to_end(self, tmp_path: Any) -> None:
    # Adds char counts: one thinking-off calibration record + thinking-on records.
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps(PRICING))
    pricing = json.loads(pricing_path.read_text())

    usage_path = tmp_path / "usage.jsonl"
    usage_path.write_text(
      "\n".join(
        [
          # thinking-off calibration call: 400 chars / 100 tok → ratio 4.0
          json.dumps(
            _record(model="glm-5.3-flash", output_tokens=100, content_chars=400, session_id="s1")
          ),
          json.dumps(
            _record(
              model="glm-5.3-flash:cloud",
              output_tokens=922,
              thinking_chars=3000,
              content_chars=500,
              session_id="s1",
            )
          ),
        ]
      )
      + "\n"
    )
    records, skipped = load_usage(usage_path)
    agg = aggregate(records, pricing)

    assert skipped == 0
    assert math.isclose(agg["ratio"], 4.0)
    assert agg["est_thinking_tokens"] == 750

    report = format_report(agg)
    assert "Thinking estimate (client-side chars; ratio 4.00 chars/token" in report
    assert "Estimated total cost incl. thinking (upper bound):" in report


class TestFormatReportEstimates:
  """Tests for the thinking-estimate block in the text report."""

  def test_estimate_block_with_ratio_and_upper_bound(self) -> None:
    records = [
      _record(model="glm-5.3-flash", output_tokens=100, content_chars=400),  # calibrates
      _record(model="glm-5.3-flash", output_tokens=922, thinking_chars=3000, content_chars=500),
    ]

    report = format_report(aggregate(records, PRICING))

    assert "Thinking estimate (client-side chars; ratio 4.00 chars/token" in report
    assert (
      "glm-5.3-flash: est thinking 750 tok (~$0.000375) | unexplained in reported output: +797 tok"
    )
    assert "Estimated total cost incl. thinking (upper bound): $0.001186" in report
    assert "est" in report

  def test_unavailable_line_when_no_calibration(self) -> None:
    records = [_record(model="glm-5.3-flash", thinking_chars=3000, content_chars=500)]

    report = format_report(aggregate(records, PRICING))

    assert (
      "Thinking estimate: unavailable (no thinking-off calls yet to calibrate chars/token ratio)."
      in report
    )
    assert "Estimated total cost" not in report

  def test_nothing_when_no_thinking_chars(self) -> None:
    records = [_record(model="glm-5.3-flash", output_tokens=100, content_chars=400)]

    report = format_report(aggregate(records, PRICING))

    assert "Thinking estimate" not in report
    assert "Estimated total cost" not in report

  def test_sample_report_full_text(self) -> None:
    # Pinned full-text regression: 2 thinking-on + 1 calibration + 1 unknown.
    records = [
      _record(  # thinking-off calibration: 400 chars / 100 tok → ratio 4.0
        model="glm-5.3-flash",
        input_tokens=1000,
        output_tokens=100,
        content_chars=400,
        session_id="s1",
        ts="2026-09-01T12:00:00+00:00",
      ),
      _record(
        model="glm-5.3-flash",
        input_tokens=2000,
        output_tokens=922,
        thinking_chars=3000,
        content_chars=500,
        session_id="s1",
        ts="2026-09-01T12:00:10+00:00",
      ),
      _record(
        model="glm-5.3-flash",
        input_tokens=2000,
        output_tokens=922,
        thinking_chars=3000,
        content_chars=500,
        session_id="s1",
        ts="2026-09-01T12:00:20+00:00",
      ),
      _record(
        model="some-model",
        input_tokens=500,
        output_tokens=60,
        thinking_chars=1500,
        content_chars=250,
        session_id="s2",
        ts="2026-09-01T12:00:30+00:00",
      ),
    ]

    report = format_report(aggregate(records, PRICING))

    assert report == "\n".join(
      [
        "Usage report  2026-09-01T12:00:00+00:00 → 2026-09-01T12:00:30+00:00",
        "Sessions: 2    Calls: 4",
        "",
        "Model              Calls   Input tokens  Output tokens           Cost",
        "glm-5.3-flash          3           5000           1944      $0.001722",
        "Total                  4           5500           2004      $0.001722",
        "",
        "Unpriced models:",
        "  some-model: 1 calls, 500 in, 60 out (no pricing entry)",
        "",
        "Thinking estimate (client-side chars; ratio 4.00 chars/token calibrated from thinking-off calls):",
        "  glm-5.3-flash: est thinking 1500 tok (~$0.000750) | unexplained in reported output: +1594 tok",
        "  some-model: est thinking 375 tok | unexplained in reported output: -2 tok",
        "Estimated total cost incl. thinking (upper bound): $0.002472",
        "",
        "Note: cached-input pricing exists but usage logs do not record a cached-token",
        "breakdown; cost is computed at full input price (conservative upper bound).",
      ]
    )


class TestCachedNoteConstant:
  """The note text is part of the report contract."""

  def test_note_mentions_conservative_bound(self) -> None:
    assert "conservative upper bound" in CACHED_INPUT_NOTE
