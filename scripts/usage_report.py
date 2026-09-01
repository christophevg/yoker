#!/usr/bin/env python3
"""CLI for token usage reporting. Thin wrapper — all logic in yoker.usage.report.

Usage: uv run python scripts/usage_report.py [usage_file] [--pricing PATH] [--json]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from yoker.usage.report import aggregate, format_report, load_usage

DEFAULT_USAGE_FILE = "~/.yoker/usage.jsonl"
PRICING_FILENAME = "ollama_pricing.json"


def _fail(message: str) -> NoReturn:
  print(message, file=sys.stderr)
  sys.exit(2)


def main() -> None:
  parser = argparse.ArgumentParser(description="Report token usage and cost from a usage JSONL file.")
  parser.add_argument("usage_file", nargs="?", default=DEFAULT_USAGE_FILE, help="usage JSONL file (default: %(default)s)")
  parser.add_argument(
    "--pricing",
    type=Path,
    default=Path(__file__).resolve().parent / PRICING_FILENAME,
    help="pricing JSON file (default: ollama_pricing.json next to this script)",
  )
  parser.add_argument("--json", action="store_true", help="print aggregate as JSON instead of text")
  args = parser.parse_args()

  try:
    with open(args.pricing, encoding="utf-8") as f:
      pricing = json.load(f)
  except FileNotFoundError:
    _fail(f"pricing file not found: {args.pricing}")
  except json.JSONDecodeError as e:
    _fail(f"pricing file is not valid JSON: {args.pricing} ({e})")
  except OSError as e:
    _fail(f"cannot read pricing file: {args.pricing} ({e})")

  try:
    records, skipped = load_usage(Path(args.usage_file).expanduser())
  except FileNotFoundError:
    _fail(f"usage file not found: {args.usage_file}")
  except OSError as e:
    _fail(f"cannot read usage file: {args.usage_file} ({e})")

  if skipped > 0:
    print(f"warning: skipped {skipped} malformed line(s) in {args.usage_file}", file=sys.stderr)

  agg = aggregate(records, pricing)

  if args.json:
    print(
      json.dumps(
        {
          "aggregates": agg,
          "pricing_meta": {
            key: pricing[key] for key in ("source", "captured", "currency", "unit") if key in pricing
          },
        },
        indent=2,
      )
    )
  else:
    print(format_report(agg, currency=pricing.get("currency", "USD")))


if __name__ == "__main__":
  main()