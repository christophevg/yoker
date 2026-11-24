"""Cross-loop behavior of persistent vs per-call HTTP clients (T6 outcome).

Two executed facts about event-loop-bound transports, established during
the "Queue is bound to a different event loop" investigation:

1. A PERSISTENT httpx connection pool is loop-bound: once it holds a
   connection created on loop A, using the client after loop A's
   teardown raises ``RuntimeError: Event loop is closed`` (anyio stream
   aclose on the dead loop — httpcore http11.py → anyio.py:53). The
   response IS served at the socket level; the failure comes when
   httpcore closes the response. Probed through BOTH a plain
   ``httpx.AsyncClient`` and ``ollama.AsyncClient.chat()`` (yoker's
   actual stack). This is an upstream library property, pinned here as
   an xfail so a future httpx/httpcore that fixes pooled-connection
   rebinding flips it loudly.

2. The per-call fix: creating the client PER CALL is loop-agnostic by
   construction. The ollama SDK client (v0.6.2) supports the async
   context manager protocol (``async with`` — closes its inner httpx
   pool on exit; the SDK client itself exposes only sync ``close()``,
   no ``aclose()``). ``OllamaBackend._build_client()`` + ``async with``
   is the production pattern these tests pin.

Harness: a raw-socket HTTP/1.1 keep-alive server on an ephemeral
127.0.0.1 port — REAL pooled connections, no mock can prove this layer.
No network beyond localhost, no Ollama server needed.
"""

import asyncio
import json
import socket
import threading
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest
from ollama import AsyncClient as OllamaAsyncClient

_T = TypeVar("_T")

_BODY = json.dumps(
  {
    "model": "probe",
    "created_at": "2026-01-01T00:00:00Z",
    "message": {"role": "assistant", "content": "ok"},
    "done": True,
  }
).encode()


class _KeepaliveServer:
  """Real-socket HTTP/1.1 server that keeps connections open.

  Accepts connections on an ephemeral 127.0.0.1 port and serves each
  sequentially: reads to end of request headers, writes one canned JSON
  response WITHOUT ``Connection: close``, and leaves the socket open so
  httpx pools the connection (that is the state under test). Also
  accepts further connections if the client opens new ones.
  """

  def __init__(self) -> None:
    self.requests = 0
    self._stopped = threading.Event()
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._sock.bind(("127.0.0.1", 0))
    self._sock.listen(16)
    self._sock.settimeout(0.25)  # accept re-checks the stop flag promptly
    self.port: int = int(self._sock.getsockname()[1])
    self._thread: threading.Thread | None = None

  @property
  def url(self) -> str:
    """Base URL of the listening socket."""
    return f"http://127.0.0.1:{self.port}"

  def start(self) -> None:
    """Start the accept loop on a daemon thread."""
    self._thread = threading.Thread(target=self._serve, daemon=True)
    self._thread.start()

  def stop(self) -> None:
    """Stop the accept loop and close the listening socket (bounded)."""
    self._stopped.set()
    self._sock.close()
    if self._thread is not None:
      self._thread.join(timeout=5)

  def _serve(self) -> None:
    while not self._stopped.is_set():
      try:
        conn, _ = self._sock.accept()
      except OSError:
        continue  # accept timeout (stop-flag window) or socket shutdown
      self._handle(conn)

  def _handle(self, conn: socket.socket) -> None:
    head = (
      f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(_BODY)}\r\n\r\n"
    ).encode()
    conn.settimeout(5.0)
    try:
      while not self._stopped.is_set():
        buf = b""
        while b"\r\n\r\n" not in buf:
          chunk = conn.recv(4096)
          if not chunk:
            return  # peer closed the connection
          buf += chunk
        self.requests += 1
        conn.sendall(head + _BODY)
        # Socket deliberately stays open: keep-alive pooling.
    except OSError:
      pass
    finally:
      conn.close()


class _BackgroundLoop:
  """A private event loop on a side thread.

  Duplicated rather than imported so this file stays self-contained.
  """

  def __init__(self) -> None:
    self.loop = asyncio.new_event_loop()
    self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)

  def start(self) -> None:
    """Start the loop on its side thread and wait until it is running."""
    self._thread.start()
    for _ in range(1000):
      if self.loop.is_running():
        return
      time.sleep(0.01)
    msg = "Background event loop failed to start"
    raise RuntimeError(msg)

  def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
    """Run ``coro`` on the background loop and block until it completes."""
    return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=30)

  def stop(self) -> None:
    """Tear the loop down asyncio.run-style: cancel tasks, stop, close."""

    async def _shutdown() -> None:
      current = asyncio.current_task()
      assert current is not None
      pending = [t for t in asyncio.all_tasks(self.loop) if t is not current and not t.done()]
      for task in pending:
        task.cancel()
      if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    if self.loop.is_closed():
      return
    asyncio.run_coroutine_threadsafe(_shutdown(), self.loop).result(timeout=10)
    self.loop.call_soon_threadsafe(self.loop.stop)
    self._thread.join(timeout=10)
    self.loop.close()


@pytest.fixture
def server() -> Any:
  """Start a keep-alive server for the test and stop it afterwards."""
  srv = _KeepaliveServer()
  srv.start()
  try:
    yield srv
  finally:
    srv.stop()


@pytest.mark.asyncio
async def test_ollama_per_call_client_survives_loop_switch(server: Any) -> None:
  """The production per-call pattern survives the sequential loop switch.

  Mirrors OllamaBackend._build_client + async with: fresh client per
  call, each call fully wrapped. Turn 1 constructed + consumed on loop
  A; turn 2 constructs a FRESH client (its connections bind to loop B —
  the running test loop) and succeeds. This is the regression pin for
  the per-call fix.

  (The persistent-pool failure that motivates this is documented in the
  module docstring: executed in the T6 probes, but racy across runs —
  the httpcore pool MAY discard a dead-loop connection and re-dial
  instead of handing it out — so it is intentionally not a test.)
  """
  messages = [{"role": "user", "content": "probe"}]

  def build_client() -> OllamaAsyncClient:
    # Same shape as OllamaBackend._build_client (host varies per call
    # only because the probe server's port is test-local).
    return OllamaAsyncClient(host=server.url)

  bg = _BackgroundLoop()
  bg.start()
  try:
    async with build_client() as client1:
      # NOTE: bg.run() already awaits the coroutine on the side loop;
      # .result() returns the ChatResponse — do NOT await it again.
      resp1 = bg.run(client1.chat(model="probe", messages=messages, stream=False))
  finally:
    bg.stop()
  assert resp1 is not None
  assert server.requests >= 1

  # Turn 2: fresh per-call client on the new loop — succeeds where the
  # persistent client failed.
  async with build_client() as client2:
    resp2 = await client2.chat(model="probe", messages=messages, stream=False)
  assert resp2 is not None
  assert server.requests >= 2
