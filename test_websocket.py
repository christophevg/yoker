#!/usr/bin/env python3
"""Test WebSocket connection to Yoker webapp."""

import asyncio
import json

import websockets


async def test_websocket():
  """Test WebSocket chat endpoint."""
  uri = "ws://localhost:8000/ws/chat"

  print(f"Connecting to {uri}...")

  try:
    async with websockets.connect(uri) as websocket:
      print("✓ Connected!")

      # Send a test message
      message = {"type": "message", "content": "Hello from test script!"}
      print(f"\n→ Sending: {json.dumps(message)}")
      await websocket.send(json.dumps(message))

      # Receive response (timeout after 5 seconds)
      print("\n← Waiting for response...")
      try:
        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        print(f"✓ Received: {response}")
      except asyncio.TimeoutError:
        print("⚠ No response received (timeout after 5s)")
        print("Note: The webapp is in echo mode until Agent integration (task 7.7)")

      # Send another message
      message2 = {"type": "message", "content": "Testing WebSocket!"}
      print(f"\n→ Sending: {json.dumps(message2)}")
      await websocket.send(json.dumps(message2))

      try:
        response2 = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        print(f"✓ Received: {response2}")
      except asyncio.TimeoutError:
        print("⚠ No response received (timeout after 5s)")

  except Exception as e:
    print(f"✗ Error: {e}")


if __name__ == "__main__":
  print("=" * 60)
  print("Yoker WebSocket Test")
  print("=" * 60)
  asyncio.run(test_websocket())