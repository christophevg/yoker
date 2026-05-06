"""Index route for Yoker webapp.

Provides a simple HTML page for testing WebSocket connectivity.
"""

from quart import Blueprint
from quart_cors import cors_exempt

index_bp = Blueprint("index", __name__)


@index_bp.route("/", methods=["GET"])
@cors_exempt
async def index() -> str:
  """Index page with WebSocket test UI.

  Returns:
    HTML page with WebSocket test interface.
  """
  html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Yoker Webapp - WebSocket Test</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      max-width: 800px;
      margin: 50px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .container {
      background: white;
      border-radius: 8px;
      padding: 30px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 {
      color: #333;
      margin-top: 0;
    }
    .status {
      padding: 10px 15px;
      border-radius: 4px;
      margin: 20px 0;
      font-weight: 500;
    }
    .status.disconnected {
      background: #fee;
      color: #c00;
    }
    .status.connected {
      background: #efe;
      color: #0a0;
    }
    .status.error {
      background: #fee;
      color: #c00;
    }
    .controls {
      margin: 20px 0;
    }
    button {
      background: #0070f3;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      margin-right: 10px;
    }
    button:hover {
      background: #0051a8;
    }
    button:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
    input[type="text"] {
      width: calc(100% - 120px);
      padding: 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      font-family: 'Monaco', 'Menlo', monospace;
    }
    #output {
      background: #f8f8f8;
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 15px;
      margin-top: 20px;
      height: 400px;
      overflow-y: auto;
      font-family: 'Monaco', 'Menlo', monospace;
      font-size: 13px;
      line-height: 1.6;
    }
    .message {
      margin: 5px 0;
      padding: 5px 0;
      border-bottom: 1px solid #eee;
    }
    .message.sent {
      color: #0066cc;
    }
    .message.received {
      color: #008800;
    }
    .message.error {
      color: #cc0000;
    }
    .message.system {
      color: #666;
      font-style: italic;
    }
    .info {
      background: #f0f8ff;
      border-left: 4px solid #0070f3;
      padding: 15px;
      margin: 20px 0;
      font-size: 14px;
      line-height: 1.6;
    }
    .info code {
      background: #e8e8e8;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: 'Monaco', 'Menlo', monospace;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>🚀 Yoker Webapp - WebSocket Test</h1>

    <div class="info">
      <strong>WebSocket Endpoint:</strong> <code>ws://localhost:8000/ws/chat</code><br>
      <strong>Health Check:</strong> <a href="/health" target="_blank">/health</a><br>
      <strong>Note:</strong> This is a test interface. The webapp runs in echo mode until Agent integration (task 7.7).
    </div>

    <div id="status" class="status disconnected">Disconnected</div>

    <div class="controls">
      <button id="connectBtn" onclick="connect()">Connect</button>
      <button id="disconnectBtn" onclick="disconnect()" disabled>Disconnect</button>
    </div>

    <div class="controls">
      <input type="text" id="messageInput" placeholder='{"type": "message", "content": "Hello!"}' onkeypress="handleKeyPress(event)">
      <button id="sendBtn" onclick="sendMessage()" disabled>Send</button>
    </div>

    <div id="output"></div>
  </div>

  <script>
    let ws = null;
    const statusEl = document.getElementById('status');
    const outputEl = document.getElementById('output');
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');
    const sendBtn = document.getElementById('sendBtn');
    const messageInput = document.getElementById('messageInput');

    function log(message, type = 'system') {
      const msgEl = document.createElement('div');
      msgEl.className = `message ${type}`;
      msgEl.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
      outputEl.appendChild(msgEl);
      outputEl.scrollTop = outputEl.scrollHeight;
    }

    function updateStatus(text, className) {
      statusEl.textContent = text;
      statusEl.className = `status ${className}`;
    }

    function connect() {
      if (ws) {
        ws.close();
      }

      const wsUrl = `ws://${window.location.host}/ws/chat`;
      log(`Connecting to ${wsUrl}...`, 'system');

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        log('✓ Connected to WebSocket', 'received');
        updateStatus('Connected', 'connected');
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          log(`← ${JSON.stringify(data, null, 2)}`, 'received');
        } catch (e) {
          log(`← ${event.data}`, 'received');
        }
      };

      ws.onerror = (error) => {
        log(`✗ WebSocket error: ${error}`, 'error');
        updateStatus('Error', 'error');
      };

      ws.onclose = (event) => {
        log(`Connection closed (code: ${event.code}, reason: ${event.reason})`, 'system');
        updateStatus('Disconnected', 'disconnected');
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
        sendBtn.disabled = true;
        ws = null;
      };
    }

    function disconnect() {
      if (ws) {
        ws.close();
        ws = null;
      }
    }

    function sendMessage() {
      const message = messageInput.value.trim();
      if (!message || !ws) return;

      try {
        // Try to parse as JSON
        const parsed = JSON.parse(message);
        log(`→ ${JSON.stringify(parsed)}`, 'sent');
        ws.send(JSON.stringify(parsed));
      } catch (e) {
        // If not valid JSON, wrap it
        const wrapped = { type: 'message', content: message };
        log(`→ ${JSON.stringify(wrapped)}`, 'sent');
        ws.send(JSON.stringify(wrapped));
      }

      messageInput.value = '';
      messageInput.focus();
    }

    function handleKeyPress(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    }

    // Auto-connect on page load
    // window.onload = connect;
  </script>
</body>
</html>"""

  return html