#!/usr/bin/env python3
"""Analyze recorded Claude Code session from JSONL proxy logs.

Usage:
    python scripts/analyze_session.py <recording.jsonl>

This script parses the JSONL recording and extracts:
- Request/response patterns
- Tool definitions
- Message history growth
- System prompts
- Context management patterns
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RequestInfo:
  """Information about a single request."""
  turn: int
  timestamp: str | None = None
  method: str | None = None
  body_size: int = 0
  model: str | None = None
  message_count: int = 0
  system_count: int = 0
  tool_count: int = 0
  has_tools: bool = False
  tool_names: list[str] = field(default_factory=list)
  messages: list[dict] = field(default_factory=list)
  system_prompts: list[dict] = field(default_factory=list)
  tools: list[dict] = field(default_factory=list)


@dataclass
class SessionAnalysis:
  """Analysis of the entire session."""
  requests: list[RequestInfo] = field(default_factory=list)
  total_turns: int = 0
  tools_loaded: list[str] = field(default_factory=list)
  context_growth: list[tuple[int, int]] = field(default_factory=list)  # (turn, message_count)
  max_body_size: int = 0


def parse_jsonl(filepath: Path) -> list[dict]:
  """Parse JSONL file into list of records."""
  records = []
  with open(filepath) as f:
    for line in f:
      if line.strip():
        records.append(json.loads(line))
  return records


def analyze_session(records: list[dict]) -> SessionAnalysis:
  """Analyze session from parsed records."""
  analysis = SessionAnalysis()
  turn = 0
  current_turn_requests: list[dict] = []

  for record in records:
    if record.get("type") == "request":
      # New turn starts with a request
      if current_turn_requests:
        # Process previous turn
        req_info = extract_turn_info(current_turn_requests, turn)
        analysis.requests.append(req_info)
        if req_info.tool_names and not analysis.tools_loaded:
          analysis.tools_loaded = req_info.tool_names
        analysis.context_growth.append((turn, req_info.message_count))
        if req_info.body_size > analysis.max_body_size:
          analysis.max_body_size = req_info.body_size
      turn += 1
      current_turn_requests = [record]
    elif record.get("type") == "request_body":
      current_turn_requests.append(record)
    elif record.get("type") == "response":
      current_turn_requests.append(record)
    elif record.get("type") == "response_body":
      current_turn_requests.append(record)

  # Process last turn
  if current_turn_requests:
    req_info = extract_turn_info(current_turn_requests, turn)
    analysis.requests.append(req_info)
    analysis.context_growth.append((turn, req_info.message_count))

  analysis.total_turns = turn
  return analysis


def extract_turn_info(records: list[dict], turn: int) -> RequestInfo:
  """Extract request info from turn records."""
  info = RequestInfo(turn=turn)

  # Find the last request_body (most complete)
  request_body = None
  for record in reversed(records):
    if record.get("type") == "request_body":
      request_body = record.get("body", {})
      break

  # Find request metadata
  for record in records:
    if record.get("type") == "request":
      info.timestamp = record.get("timestamp")
      info.method = record.get("method")
      info.body_size = record.get("body_size", 0)
      break

  if request_body:
    info.model = request_body.get("model")
    messages = request_body.get("messages", [])
    info.message_count = len(messages)
    info.messages = messages

    system = request_body.get("system", [])
    info.system_count = len(system)
    info.system_prompts = system

    tools = request_body.get("tools", [])
    info.tool_count = len(tools)
    info.has_tools = info.tool_count > 0
    info.tool_names = [t.get("name") for t in tools if t.get("name")]
    info.tools = tools

  return info


def print_summary(analysis: SessionAnalysis) -> None:
  """Print session summary."""
  print("=" * 70)
  print("SESSION ANALYSIS SUMMARY")
  print("=" * 70)
  print(f"\nTotal turns: {analysis.total_turns}")
  print(f"Max body size: {analysis.max_body_size:,} bytes")
  print(f"Tools loaded: {len(analysis.tools_loaded)}")

  if analysis.tools_loaded:
    print("\nTools:")
    for i, name in enumerate(analysis.tools_loaded, 1):
      print(f"  {i:2}. {name}")

  print("\nCONTEXT GROWTH:")
  print("-" * 70)
  print(f"{'Turn':>4} | {'Messages':>8} | {'Tools':>6} | {'Body Size':>12}")
  print("-" * 70)

  for req in analysis.requests:
    print(f"{req.turn:4} | {req.message_count:8} | {req.tool_count:6} | {req.body_size:12,}")


def print_system_prompts(analysis: SessionAnalysis, turn: int = 1) -> None:
  """Print system prompts from a specific turn."""
  if turn < 1 or turn > len(analysis.requests):
    print(f"Invalid turn {turn}. Valid range: 1-{len(analysis.requests)}")
    return

  req = analysis.requests[turn - 1]
  print(f"\nSYSTEM PROMPTS (Turn {turn}):")
  print("=" * 70)

  for i, prompt in enumerate(req.system_prompts, 1):
    text = prompt.get("text", "")
    print(f"\n[{i}] Length: {len(text):,} chars")
    print("-" * 70)
    # Print first 500 chars
    if len(text) > 500:
      print(text[:500] + "...\n[truncated]")
    else:
      print(text)


def print_tool_definitions(analysis: SessionAnalysis, tool_name: str | None = None) -> None:
  """Print tool definitions from the session."""
  # Find first turn with tools
  for req in analysis.requests:
    if req.tools:
      print(f"\nTOOL DEFINITIONS (Turn {req.turn}):")
      print("=" * 70)

      for tool in req.tools:
        name = tool.get("name", "")
        if tool_name and name != tool_name:
          continue

        print(f"\nTool: {name}")
        print("-" * 70)

        description = tool.get("description", "")
        if description:
          print(f"Description: {description[:200]}..." if len(description) > 200 else f"Description: {description}")

        input_schema = tool.get("input_schema", {})
        if input_schema:
          props = input_schema.get("properties", {})
          required = input_schema.get("required", [])
          print(f"Parameters: {len(props)}")
          for prop_name, prop_def in props.items():
            req_marker = "*" if prop_name in required else " "
            prop_type = prop_def.get("type", "unknown")
            desc = prop_def.get("description", "")[:50]
            print(f"  {req_marker} {prop_name}: {prop_type} - {desc}")

        if not tool_name:
          print()  # Add spacing between tools

      if not tool_name:
        break  # Only show first turn with tools


def print_messages(analysis: SessionAnalysis, turn: int) -> None:
  """Print messages from a specific turn."""
  if turn < 1 or turn > len(analysis.requests):
    print(f"Invalid turn {turn}. Valid range: 1-{len(analysis.requests)}")
    return

  req = analysis.requests[turn - 1]
  print(f"\nMESSAGES (Turn {turn}):")
  print("=" * 70)

  for i, msg in enumerate(req.messages, 1):
    role = msg.get("role", "unknown")
    content = msg.get("content", [])

    print(f"\n[{i}] Role: {role}")

    if isinstance(content, str):
      print(f"Content (text): {content[:200]}..." if len(content) > 200 else f"Content (text): {content}")
    elif isinstance(content, list):
      for j, block in enumerate(content):
        block_type = block.get("type", "unknown")
        if block_type == "text":
          text = block.get("text", "")
          print(f"  Block {j}: {block_type}")
          print(f"    {text[:200]}..." if len(text) > 200 else f"    {text}")
        elif block_type == "tool_result":
          tool_use_id = block.get("tool_use_id", "unknown")
          print(f"  Block {j}: {block_type} (id: {tool_use_id})")
          # content of tool_result is often large


def main():
  if len(sys.argv) < 2:
    print(__doc__)
    print("\nError: Please provide a JSONL file path")
    sys.exit(1)

  filepath = Path(sys.argv[1])
  if not filepath.exists():
    print(f"Error: File not found: {filepath}")
    sys.exit(1)

  print(f"Parsing {filepath}...")
  records = parse_jsonl(filepath)
  print(f"Found {len(records)} records\n")

  analysis = analyze_session(records)
  print_summary(analysis)

  # Check for additional commands
  if len(sys.argv) > 2:
    command = sys.argv[2]
    if command == "tools":
      tool_name = sys.argv[3] if len(sys.argv) > 3 else None
      print_tool_definitions(analysis, tool_name)
    elif command == "system":
      turn = int(sys.argv[3]) if len(sys.argv) > 3 else 1
      print_system_prompts(analysis, turn)
    elif command == "messages":
      turn = int(sys.argv[3]) if len(sys.argv) > 3 else 1
      print_messages(analysis, turn)


if __name__ == "__main__":
  main()