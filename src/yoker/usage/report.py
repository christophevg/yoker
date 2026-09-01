"""Token usage reporting: aggregate JSONL usage records and compute costs.

Pure logic — no file I/O for pricing (the pricing dict is passed in) and no
CLI concerns. Kept Python 3.10 compatible (``timezone.utc``, not ``datetime.UTC``).
"""

import json
from pathlib import Path
from typing import Any

CACHED_INPUT_NOTE = (
  "Note: cached-input pricing exists but usage logs do not record a cached-token\n"
  "breakdown; cost is computed at full input price (conservative upper bound)."
)


def load_usage(path: str | Path) -> tuple[list[dict[str, Any]], int]:
  """Read a usage JSONL file.

  Returns:
    Tuple of (parsed records, skipped-line count). Blank and malformed
    lines are skipped and counted.
  """
  records: list[dict[str, Any]] = []
  skipped = 0
  with open(path, encoding="utf-8") as f:
    for line in f:
      if not line.strip():
        continue
      try:
        record = json.loads(line)
      except json.JSONDecodeError:
        skipped += 1
        continue
      if isinstance(record, dict):
        records.append(record)
      else:
        skipped += 1
  return records, skipped


def match_model(name: str, pricing: dict[str, Any]) -> str | None:
  """Map a logged model name to a pricing key, or None.

  1. Exact key match.
  2. Strip a trailing ``:cloud``/``:latest`` tag, retry exact.
  3. Prefix match: pricing key ``k`` matches when ``name.startswith(k + ":")`` —
     keeps ``gpt-oss:120b`` matching itself while mapping ``glm-5.3-flash:xyz``
     to ``glm-5.3-flash``.
  """
  models: dict[str, Any] = pricing.get("models", {})
  if name in models:
    return name
  base = name.split(":")[0]
  for tag in ("cloud", "latest"):
    if base and name == f"{base}:{tag}" and base in models:
      return base
  for key in models:
    if name.startswith(key + ":"):
      return key
  return None


def calibration_ratio(records: list[dict[str, Any]]) -> float | None:
  """Chars-per-token ratio calibrated from thinking-OFF calls.

  Uses records where ``thinking_chars == 0``, ``content_chars > 0`` and
  ``output_tokens > 0``: ratio = sum(content_chars) / sum(output_tokens).
  Token-weighted (more robust than the mean of per-call ratios) because it
  derives the ratio from real billed data. Returns None when no qualifying
  records exist.

  Note: the ratio is chars DIVIDED BY tokens (chars per token), so the
  estimate ``chars / ratio`` yields tokens. The spec text wrote the division
  inverted (tokens/chars) while naming and using it as chars-per-token; the
  coherent reading is implemented here.
  """
  output_tokens = 0
  content_chars = 0
  for record in records:
    if (record.get("thinking_chars") or 0) != 0:
      continue
    content = record.get("content_chars") or 0
    tokens = record.get("output_tokens") or 0
    if content > 0 and tokens > 0:
      content_chars += content
      output_tokens += tokens
  if output_tokens == 0:
    return None
  return content_chars / output_tokens


def aggregate(records: list[dict[str, Any]], pricing: dict[str, Any]) -> dict[str, Any]:
  """Aggregate records per model and compute costs.

  Models are keyed by their matched pricing name, in order of first
  appearance. Unknown models (no pricing entry) accumulate tokens under
  ``unknown_models`` and contribute $0. Records missing input/output keys
  count as 0 for that field. ``cached_input`` pricing is NOT applied —
  the usage log has no cached-token breakdown.

  Client-side char counts are aggregated per bucket. When a calibration
  ratio is available (see :func:`calibration_ratio`), estimated thinking /
  content token counts and a thinking-cost upper bound are computed —
  these are estimates, distinct from the reported token counts.
  """
  ratio = calibration_ratio(records)
  sessions: set[str] = set()
  first_ts: str | None = None
  last_ts: str | None = None
  models: dict[str, dict[str, Any]] = {}
  unknown_models: dict[str, dict[str, Any]] = {}
  total_input = 0
  total_output = 0
  total_cost = 0.0
  total_thinking_chars = 0
  total_content_chars = 0

  for record in records:
    input_tokens = record.get("input_tokens") or 0
    output_tokens = record.get("output_tokens") or 0
    thinking_chars = record.get("thinking_chars") or 0
    content_chars = record.get("content_chars") or 0
    session_id = record.get("session_id")
    if session_id is not None:
      sessions.add(str(session_id))
    ts = record.get("ts")
    if ts is not None:
      if first_ts is None:
        first_ts = ts
      last_ts = ts

    logged_name = record.get("model") or "unknown"
    price_key = match_model(logged_name, pricing)
    price = pricing.get("models", {}).get(price_key) if price_key else None

    if price_key is not None and price is not None:
      bucket = models.setdefault(
        price_key,
        {
          "calls": 0,
          "input_tokens": 0,
          "output_tokens": 0,
          "cost": 0.0,
          "thinking_chars": 0,
          "content_chars": 0,
          "est_content_tokens": 0,
          "est_thinking_tokens": 0,
          "est_thinking_cost": 0.0,
          "implied_thinking_in_output": 0,
        },
      )
      cost = input_tokens * price["input"] / 1_000_000 + output_tokens * price["output"] / 1_000_000
      bucket["cost"] += cost
      total_cost += cost
    else:
      bucket = unknown_models.setdefault(
        logged_name,
        {
          "calls": 0,
          "input_tokens": 0,
          "output_tokens": 0,
          "thinking_chars": 0,
          "content_chars": 0,
          "est_content_tokens": 0,
          "est_thinking_tokens": 0,
          "implied_thinking_in_output": 0,
        },
      )

    bucket["calls"] += 1
    bucket["input_tokens"] += input_tokens
    bucket["output_tokens"] += output_tokens
    bucket["thinking_chars"] += thinking_chars
    bucket["content_chars"] += content_chars
    total_input += input_tokens
    total_output += output_tokens
    total_thinking_chars += thinking_chars
    total_content_chars += content_chars

  # Estimates — computed per bucket after summation. ``implied_thinking_in_output``
  # can go negative: near 0 suggests eval_count already includes thinking tokens;
  # near est_thinking_tokens suggests it does not.
  all_buckets: list[tuple[dict[str, Any], float | None]] = [
    (bucket, pricing["models"][key]["output"]) for key, bucket in models.items()
  ] + [(bucket, None) for bucket in unknown_models.values()]
  total_est_thinking_cost = 0.0
  for bucket, output_price in all_buckets:
    if ratio is None:
      continue
    bucket["est_content_tokens"] = round(bucket["content_chars"] / ratio)
    bucket["est_thinking_tokens"] = round(bucket["thinking_chars"] / ratio)
    bucket["implied_thinking_in_output"] = bucket["output_tokens"] - bucket["est_content_tokens"]
    if output_price is not None:
      bucket["est_thinking_cost"] = bucket["est_thinking_tokens"] * output_price / 1_000_000
      total_est_thinking_cost += bucket["est_thinking_cost"]

  total_est_content = round(total_content_chars / ratio) if ratio else 0
  total_est_thinking = round(total_thinking_chars / ratio) if ratio else 0

  return {
    "calls": len(records),
    "sessions": len(sessions),
    "first_ts": first_ts,
    "last_ts": last_ts,
    "models": models,
    "unknown_models": unknown_models,
    "total_input_tokens": total_input,
    "total_output_tokens": total_output,
    "total_cost": total_cost,
    "total_thinking_chars": total_thinking_chars,
    "total_content_chars": total_content_chars,
    "est_content_tokens": total_est_content,
    "est_thinking_tokens": total_est_thinking,
    "est_thinking_cost": 0.0 if ratio is None else total_est_thinking_cost,
    "implied_thinking_in_output": total_output - total_est_content,
    "ratio": ratio,
  }


def format_report(agg: dict[str, Any], currency: str = "USD") -> str:
  """Render an aggregate as a human-readable aligned plain-text report."""
  if agg["calls"] == 0:
    return "No usage records."

  lines: list[str] = []
  if agg["first_ts"] is not None:
    lines.append(f"Usage report  {agg['first_ts']} → {agg['last_ts']}")
  else:
    lines.append("Usage report")
  lines.append(f"Sessions: {agg['sessions']}    Calls: {agg['calls']}")
  lines.append("")

  header = f"{'Model':<18}{'Calls':>6}{'Input tokens':>15}{'Output tokens':>15}{'Cost':>15}"
  lines.append(header)

  def model_row(name: str, entry: dict[str, Any]) -> str:
    cost = f"${entry.get('cost', 0.0):.6f}" if "cost" in entry else "—"
    return (
      f"{name:<18}{entry['calls']:>6}{entry['input_tokens']:>15}"
      f"{entry['output_tokens']:>15}{cost:>15}"
    )

  for name, entry in agg["models"].items():
    lines.append(model_row(name, entry))
  total_cost = f"${agg['total_cost']:.6f}"
  lines.append(
    f"{'Total':<18}{agg['calls']:>6}{agg['total_input_tokens']:>15}"
    f"{agg['total_output_tokens']:>15}{total_cost:>15}"
  )

  if agg["unknown_models"]:
    lines.append("")
    lines.append("Unpriced models:")
    for name, entry in agg["unknown_models"].items():
      lines.append(
        f"  {name}: {entry['calls']} calls, {entry['input_tokens']} in, "
        f"{entry['output_tokens']} out (no pricing entry)"
      )

  ratio = agg.get("ratio")
  if agg.get("total_thinking_chars", 0) > 0:
    if ratio is None:
      lines.append("")
      lines.append(
        "Thinking estimate: unavailable (no thinking-off calls yet to calibrate chars/token ratio)."
      )
    else:
      lines.append("")
      lines.append(
        f"Thinking estimate (client-side chars; ratio {ratio:.2f} chars/token "
        "calibrated from thinking-off calls):"
      )
      named: dict[str, dict[str, Any]] = dict(agg["models"])
      named.update(agg["unknown_models"])
      for name, entry in named.items():
        if entry.get("thinking_chars", 0) == 0:
          continue
        implied = entry.get("implied_thinking_in_output", 0)
        cost = f" (~${entry['est_thinking_cost']:.6f})" if "est_thinking_cost" in entry else ""
        lines.append(
          f"  {name}: est thinking {entry['est_thinking_tokens']} tok{cost} | "
          f"unexplained in reported output: {implied:+d} tok"
        )
      upper_bound = agg["total_cost"] + agg["est_thinking_cost"]
      lines.append(f"Estimated total cost incl. thinking (upper bound): ${upper_bound:.6f}")

  lines.append("")
  lines.append(CACHED_INPUT_NOTE)
  return "\n".join(lines)


__all__ = [
  "CACHED_INPUT_NOTE",
  "aggregate",
  "calibration_ratio",
  "format_report",
  "load_usage",
  "match_model",
]
