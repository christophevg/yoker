# Ollama Web Search & Web Fetch API Technical Details

**Source**: https://docs.ollama.com/capabilities/web-search
**Fetched**: 2026-05-04T00:00:00Z

---

## Authentication

- Requires API key from https://ollama.com/settings/keys (free Ollama account needed)
- Set `OLLAMA_API_KEY` environment variable or pass in Authorization header

---

## Web Search API

**Endpoint:** `POST https://ollama.com/api/web_search`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query string |
| `max_results` | integer | No | Max results (default 5, max 10) |

**Response:** Object with `results` array, each containing `title`, `url`, `content` (snippet)

**Example (cURL):**
```bash
curl https://ollama.com/api/web_search \
  --header "Authorization: Bearer $OLLAMA_API_KEY" \
  -d '{"query":"what is ollama?"}'
```

**Python:**
```python
import ollama
response = ollama.web_search("What is Ollama?")
```

**JavaScript:**
```javascript
import { Ollama } from "ollama";
const client = new Ollama();
const results = await client.webSearch("what is ollama?");
```

---

## Web Fetch API

**Endpoint:** `POST https://ollama.com/api/web_fetch`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL to fetch |

**Response:** Object with `title`, `content` (main page content), `links` (array of links)

**Python:**
```python
from ollama import web_fetch
result = web_fetch('https://ollama.com')
```

**JavaScript:**
```javascript
const fetchResult = await client.webFetch("https://ollama.com");
```

---

## Building Search Agents

- Use with `tools=[web_search, web_fetch]` parameter in chat
- Recommend context length of ~32,000 tokens minimum
- Cloud models run at full context length

---

## MCP Server Integration

Python MCP server available at: `github.com/ollama/ollama-python/blob/main/examples/web-search-mcp.py`

**Configuration example (Cline):**
```json
{
  "mcpServers": {
    "web_search_and_fetch": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "path/to/web-search-mcp.py"],
      "env": { "OLLAMA_API_KEY": "your_api_key_here" }
    }
  }
}
```

**Codex config** (`~/.codex/config.toml`):
```toml
[mcp_servers.web_search]
command = "uv"
args = ["run", "path/to/web-search-mcp.py"]
env = { "OLLAMA_API_KEY" = "your_api_key_here" }
```