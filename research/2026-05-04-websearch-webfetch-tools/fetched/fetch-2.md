# DDGS Technical Details

**Source**: https://github.com/deedy5/ddgs
**Fetched**: 2026-05-04T00:00:00Z

---

## Installation

```bash
pip install -U ddgs              # Base install
pip install -U ddgs[api]         # API server (FastAPI)
pip install -U ddgs[mcp]         # MCP server (stdio)
pip install -U ddgs[dht]         # DHT network support
```

## Core Features

- Metasearch library aggregating results from multiple web search services
- Supports text, images, videos, news, and books search
- Content extraction from URLs
- CLI, API server, MCP server, and DHT network modes

## Search Engines by Function

| Function | Available Backends |
|----------|-------------------|
| `text()` | bing, brave, duckduckgo, google, grokipedia, mojeek, yandex, yahoo, wikipedia |
| `images()` | bing, duckduckgo |
| `videos()` | duckduckgo |
| `news()` | bing, duckduckgo, yahoo |
| `books()` | annasarchive |

## DDGS Class Initialization

```python
from ddgs import DDGS
# Args: proxy (str), timeout (int, default 5), verify (bool|str, default True)
results = DDGS().text("python programming", max_results=5)
```

## API Methods

**1. text()**
```python
def text(query: str, region: str = "us-en", safesearch: str = "moderate",
         timelimit: str | None = None, max_results: int | None = 10,
         page: int = 1, backend: str = "auto") -> list[dict[str, str]]
```
- timelimit options: d, w, m, y
- Returns: list of dicts with title, href, body

**2. images()**
```python
def images(query: str, region: str = "us-en", safesearch: str = "moderate",
           timelimit: str | None = None, max_results: int | None = 10,
           page: int = 1, backend: str = "auto", size: str | None = None,
           color: str | None = None, type_image: str | None = None,
           layout: str | None = None, license_image: str | None = None)
```
- size: Small, Medium, Large, Wallpaper
- color: Monochrome, Red, Orange, Yellow, Green, Blue, Purple, Pink, Brown, Black, Gray, Teal, White
- type_image: photo, clipart, gif, transparent, line
- layout: Square, Tall, Wide
- license_image: any, Public, Share, ShareCommercially, Modify, ModifyCommercially

**3. videos()**
```python
def videos(query: str, region: str = "us-en", safesearch: str = "moderate",
           timelimit: str | None = None, max_results: int | None = 10,
           page: int = 1, backend: str = "auto", resolution: str | None = None,
           duration: str | None = None, license_videos: str | None = None)
```
- resolution: high, standart
- duration: short, medium, long
- license_videos: creativeCommon, youtube

**4. news()**
```python
def news(query: str, region: str = "us-en", safesearch: str = "moderate",
         timelimit: str | None = None, max_results: int | None = 10,
         page: int = 1, backend: str = "auto")
```
- timelimit: d, w, m

**5. books()**
```python
def books(query: str, max_results: int | None = 10, page: int = 1,
          backend: str = "auto")
```

**6. extract()**
```python
def extract(url: str, fmt: str = "text_markdown") -> dict[str, str | bytes]
```
- fmt options: text_markdown, text_plain, text_rich, text, content

## API Server

```bash
ddgs api                           # Start server in foreground
ddgs api -d                        # Start in detached mode
ddgs api -s                        # Stop detached server
ddgs api --host 127.0.0.1 --port 4479   # Default port 4479
ddgs api -pr socks5h://127.0.0.1:9150  # With proxy
```

**Endpoints:** `/search/text`, `/search/images`, `/search/news`, `/search/videos`, `/search/books`, `/extract`, `/health`, `/docs`, `/redoc`

## MCP Server

```bash
ddgs mcp                           # Start MCP server (stdio transport)
ddgs mcp -pr socks5h://127.0.0.1:9150  # With proxy
```

**Tools:** search_text, search_images, search_news, search_videos, search_books, extract_content

## DHT Network (Beta)

- Peer-to-peer distributed cache for sharing search results
- "90% faster repeated queries (50ms instead of 1-2s)"
- Platform support: Linux and macOS only (Windows not supported due to libp2p dependencies)
- Network performance improves with more nodes (>200 nodes = "Excellent")

## Proxy Support

Supports http/https/socks5 protocols
```python
DDGS(proxy="http://user:pass@example.com:3128")
```

## Known Limitations

- DHT not supported on Windows
- Beta network needs >50 nodes for reliable performance
- Results use eventual consistency (1-5 min propagation)
- Python >= 3.10 required