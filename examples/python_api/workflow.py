"""Example 4 — Agentic workflow intermixed with Python code (the showcase).

Run with:

    python examples/python_api/workflow.py

This is the example that defines Yoker's USP: agentic calls interleave with
ordinary Python — file IO, data processing, loops, conditionals — as if the
agentic steps were just function calls.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import yoker


async def _extract_json(agent: yoker.Agent, result: str) -> list[Any]:
  """Parse a JSON array from the agent's response with one retry.

  LLMs occasionally wrap JSON in prose or forget the array. When the first
  parse fails, ask the agent to return only the JSON array and try once more.
  Falls back to an empty list so the workflow never crashes on a bad model
  reply.
  """
  try:
    return cast(list[Any], json.loads(result))
  except json.JSONDecodeError:
    pass
  retry = await agent.process(
    "The previous response was not valid JSON. Return only the JSON array."
  )
  try:
    return cast(list[Any], json.loads(retry))
  except json.JSONDecodeError:
    print(f"warning: could not parse JSON from agent; skipping. Reply: {retry[:120]}")
    return []


async def main() -> None:
  analyst = yoker.agent(
    model="qwen3.5:cloud",
    system_prompt="You are a security analyst. Be specific and cite file:line.",
    tools=["read", "search", "list"],
  )

  # Python: gather the list of files to audit.
  src_files = sorted(Path("src/yoker").rglob("*.py"))
  findings: list[dict] = []

  # Agentic: analyze each file. The await sits inside a normal for-loop,
  # between Path.rglob and json.loads — the agent is just another tool.
  for path in src_files:
    result = await analyst.process(
      f"Analyze {path} for security issues. "
      "Return a JSON array of {{file, line, severity, issue}}. "
      "If the file is clean, return an empty array."
    )
    file_findings = await _extract_json(analyst, result)
    findings.extend(file_findings)

  # Python: post-process and write the report.
  report = {
    "audited_files": len(src_files),
    "total_findings": len(findings),
    "by_severity": {
      sev: sum(1 for f in findings if f["severity"] == sev)
      for sev in {"critical", "high", "medium", "low"}
    },
    "findings": findings,
  }
  Path("security-report.json").write_text(json.dumps(report, indent=2))
  print(f"Wrote security-report.json ({len(findings)} findings)")


if __name__ == "__main__":
  asyncio.run(main())
